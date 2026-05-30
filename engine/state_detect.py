# -*- coding: utf-8 -*-
"""
module_state_detect.py — 无模板状态检测引擎
=============================================
使用 Color Histogram + 轮廓检测 + OCR 混合方案
替代 cv2.matchTemplate，完全不依赖模板图片文件。

检测优先级: 比赛状态 > 导航锚点 > 赛事子菜单 > 主菜单标签

用法:
    detector = StateDetector("state_references.json")
    state = detector.detect(resized_frame)
"""

import base64
import json
import os

import cv2
import numpy as np
import pytesseract

from engine.utils import log_info, log_success, log_warning

# ========== 常量：ROI 位置 (百分比) ==========

# 主菜单标签栏 (用户标注: h19-23%, w26-74%)
TAB_BAR_Y = (0.19, 0.23)
TAB_BAR_X = (0.26, 0.74)

# 6 个标签的水平采样区域 (在标签栏 ROI 内的相对 x%)
# 标签从左到右: CAMPAIGN, CARS, MY HORIZON, ONLINE, CREATIVE HUB, STORE
TAB_ZONES = {
    "CAMPAIGN": (0.00, 0.13),
    "CARS": (0.13, 0.23),
    "MY HORIZON": (0.23, 0.42),
    "ONLINE": (0.42, 0.56),
    "CREATIVE HUB": (0.56, 0.78),
    "STORE": (0.78, 1.00),
}

# 导航页面的 OCR 检测 ROI 和关键词
NAV_PAGES = {
    "EVENTLAB_MENU": {"roi": (0.20, 0.60, 0.10, 0.50), "keywords": ["play event", "play_event", "eventlab"]},
    "FAVORITES_LIST": {"roi": (0.20, 0.50, 0.10, 0.60), "keywords": ["event", "blueprint"]},
    "RACE_READY": {"roi": (0.20, 0.50, 0.25, 0.75), "keywords": ["choose", "solo", "convoy"]},
    "CAR_SELECT": {"roi": (0.09, 0.13, 0.06, 0.16), "keywords": ["car", "select"]},
    "PRE_RACE": {"roi": (0.80, 0.95, 0.30, 0.70), "keywords": ["start race", "start_race"]},
}

# 比赛状态检测的 ROI
RACING_ROIS = {
    "RACE_END": {"roi": (0.70, 0.95, 0.20, 0.80)},
    "NEXT_SCREEN": {"roi": (0.80, 0.95, 0.35, 0.65)},
    "HUD_SPEED": {"roi": (0.75, 0.98, 0.80, 0.98)},
}

REF_FILE = "state_references.json"


def _hist_to_base64(hist):
    """将 numpy 直方图编码为 base64 字符串用于 JSON 存储。"""
    return base64.b64encode(hist.astype(np.float32).tobytes()).decode("ascii")


def _base64_to_hist(s, shape=(18, 16)):
    """从 base64 字符串解码 numpy 直方图。"""
    raw = base64.b64decode(s)
    return np.frombuffer(raw, dtype=np.float32).reshape(shape)


def compute_hist(roi_bgr, bins=(18, 16)):
    """计算 ROI 的 HSV 颜色直方图（归一化）。"""
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, list(bins), [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def compare_hists(hist1, hist2):
    """比较两个直方图，返回相关性分数 (-1 到 1)。"""
    return cv2.compareHist(hist1.astype(np.float32), hist2.astype(np.float32), cv2.HISTCMP_CORREL)


class StateDetector:
    """
    无模板视觉状态检测器。

    使用像素/颜色分析 + OCR 混合方案替代模板匹配。
    支持两种调用模式:
      - detect(resized, mode="menu")  — 完整菜单状态检测
      - detect(resized, mode="racing") — 快速比赛状态检测
    """

    def __init__(self, ref_path=None):
        self.ref_path = ref_path or REF_FILE
        self.ref_hists = {}
        self.tab_ref_brightness = {}
        self._load_references()

    def _load_references(self):
        """从 JSON 文件加载校准参考数据。"""
        if not os.path.exists(self.ref_path):
            return

        try:
            with open(self.ref_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 加载导航页面直方图
            for state, hist_b64 in data.get("nav_hists", {}).items():
                self.ref_hists[state] = _base64_to_hist(hist_b64)

            # 加载比赛状态直方图
            for state, hist_b64 in data.get("racing_hists", {}).items():
                self.ref_hists[state] = _base64_to_hist(hist_b64)

            # 加载标签亮度参考值
            self.tab_ref_brightness = data.get("tab_brightness", {})

            log_success(
                f"[StateDetector] 加载参考数据: "
                f"{len(self.ref_hists)} 个直方图, "
                f"{len(self.tab_ref_brightness)} 个标签参考"
            )
        except Exception as e:
            log_warning(f"[StateDetector] 加载参考数据失败: {e}")

    # ===================================================================
    #  主入口
    # ===================================================================

    def detect(self, resized, mode="menu"):
        """
        统一状态检测入口。

        Args:
            resized: 1600x900 的 BGR 图像
            mode: "menu" 全面检测 | "racing" 仅比赛状态(快速)

        Returns:
            状态字符串: "CARS", "PRE_RACE", "RACE_END", "PLAYING", "UNKNOWN" 等
        """
        if mode == "racing":
            return self._detect_racing(resized)
        return self._detect_menu(resized)

    # ===================================================================
    #  A. 快速比赛状态检测 (~5ms)
    # ===================================================================

    def _detect_racing(self, resized):
        """
        快速检测比赛相关状态 (RACE_END, NEXT_SCREEN, PLAYING)。
        每个检查先用亮度预检，避免不必要的 OCR 调用。
        """
        h, w = resized.shape[:2]

        # --- RACE_END: 按钮区域 OCR "Restart" ---
        if self._check_race_end(resized, h, w):
            return "RACE_END"

        # --- NEXT_SCREEN: 检测 "Next" 标题 ---
        if self._check_next_screen(resized, h, w):
            return "NEXT_SCREEN"

        # --- PLAYING: 检测 "Time" HUD ---
        if self._check_playing(resized, h, w):
            return "PLAYING"

        return None

    def _check_race_end(self, resized, h, w):
        """检测比赛结束画面：OCR 检测 h92-94%, w13-17% 灰底白字 'Restart'。"""
        end_roi = resized[int(h * 0.92) : int(h * 0.94), int(w * 0.13) : int(w * 0.17)]
        # 亮度预检：灰底白字区域亮度 40-180，全黑/全白直接跳过
        brightness = float(np.mean(end_roi))
        if brightness < 30 or brightness > 220:
            return False
        end_gray = cv2.cvtColor(end_roi, cv2.COLOR_BGR2GRAY)
        _, end_thresh = cv2.threshold(end_gray, 120, 255, cv2.THRESH_BINARY)
        end_text = pytesseract.image_to_string(end_thresh, config="--psm 7").strip().lower()
        return "restart" in end_text

    def _check_next_screen(self, resized, h, w):
        """检测 Next 结算画面：OCR 检测 h10-13%, w4-14% 的 'What's Next' 文字。"""
        next_roi = resized[int(h * 0.10) : int(h * 0.13), int(w * 0.04) : int(w * 0.14)]
        # 亮度预检
        brightness = float(np.mean(next_roi))
        if brightness < 30 or brightness > 220:
            return False
        next_gray = cv2.cvtColor(next_roi, cv2.COLOR_BGR2GRAY)
        _, next_thresh = cv2.threshold(next_gray, 120, 255, cv2.THRESH_BINARY)
        next_text = pytesseract.image_to_string(next_thresh, config="--psm 7").strip().lower()
        return "next" in next_text

    def _check_playing(self, resized, h, w):
        """
        检测自由漫游状态：
        ROI h93-96%, w10-15% 处的 "link" 文字在自由漫游时为纯白色，
        比赛中为灰色。通过亮度阈值区分。
        """
        link_roi = resized[int(h * 0.93) : int(h * 0.96), int(w * 0.10) : int(w * 0.15)]
        gray = cv2.cvtColor(link_roi, cv2.COLOR_BGR2GRAY)

        # 自由漫游: link 文字纯白 (亮度高), 比赛中: 灰色 (亮度低)
        # 用高阈值二值化提取纯白像素
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        white_ratio = float(np.sum(thresh == 255)) / thresh.size

        # 纯白像素占比 > 10% 说明有高亮白色文字 → 自由漫游
        if white_ratio < 0.10:
            return False

        # OCR 确认含 "link"
        text = pytesseract.image_to_string(thresh, config="--psm 7").strip().lower()
        return "link" in text

    # ===================================================================
    #  B. 完整菜单状态检测
    # ===================================================================

    def _detect_menu(self, resized):
        """完整菜单状态检测（含 OCR，~50-200ms）。"""
        h, w = resized.shape[:2]

        # 1. 先快速检查比赛状态
        racing = self._detect_racing(resized)
        if racing:
            return racing

        # 2. 检测导航子页面（高优先级，某些页面无主菜单标签栏）
        nav = self._detect_navigation(resized, h, w)
        if nav:
            return nav

        # 3. 标签栏亮度检查 — 判断是否在菜单界面
        tab_roi = resized[int(h * TAB_BAR_Y[0]) : int(h * TAB_BAR_Y[1]), int(w * TAB_BAR_X[0]) : int(w * TAB_BAR_X[1])]
        tab_gray = cv2.cvtColor(tab_roi, cv2.COLOR_BGR2GRAY)
        tab_brightness = float(np.mean(tab_gray))

        if tab_brightness < 30:
            # 屏幕很暗：加载中 / 过场 / 驾驶中
            return "UNKNOWN"

        # 4. 检测赛事子菜单
        submenu = self._detect_submenu(resized, h, w)
        if submenu:
            return submenu

        # 5. 检测主菜单标签
        tab = self._detect_active_tab(tab_roi, tab_gray)
        if tab:
            return tab

        return "UNKNOWN"

    # ===================================================================
    #  B1. 导航子页面检测 (OCR + 直方图)
    # ===================================================================

    def _detect_navigation(self, resized, h, w):
        """
        检测当前处于哪个导航子页面。
        使用 OCR 关键字匹配 + 直方图辅助。
        """
        # CAR_SELECT: 检测 h9-14%, w6-14% 是否含 "My Cars"
        car_title_roi = resized[int(h * 0.09) : int(h * 0.14), int(w * 0.06) : int(w * 0.14)]
        car_title_gray = cv2.cvtColor(car_title_roi, cv2.COLOR_BGR2GRAY)
        _, car_title_thresh = cv2.threshold(car_title_gray, 200, 255, cv2.THRESH_BINARY)
        car_title_text = pytesseract.image_to_string(car_title_thresh, config="--psm 7").strip().lower()
        log_info(f"[NAV] CAR_SELECT OCR: '{car_title_text}'")
        if "my" in car_title_text and "car" in car_title_text:
            return "CAR_SELECT"

        # PRE_RACE: 检测 h60-65%, w4-23% 是否含 "Start Race Event" (黑底白字)
        race_btn_roi = resized[int(h * 0.60) : int(h * 0.65), int(w * 0.04) : int(w * 0.23)]
        race_btn_gray = cv2.cvtColor(race_btn_roi, cv2.COLOR_BGR2GRAY)
        _, race_btn_thresh = cv2.threshold(race_btn_gray, 120, 255, cv2.THRESH_BINARY)
        race_btn_text = pytesseract.image_to_string(race_btn_thresh, config="--psm 7").strip().lower()
        log_info(f"[NAV] PRE_RACE OCR: '{race_btn_text}'")
        if "start" in race_btn_text and "race" in race_btn_text:
            return "PRE_RACE"

        # RACE_READY: OCR 检测按钮区域 (h49-54%, w32-68%) 是否含 "solo"
        btn_roi = resized[int(h * 0.49) : int(h * 0.54), int(w * 0.32) : int(w * 0.68)]
        btn_gray = cv2.cvtColor(btn_roi, cv2.COLOR_BGR2GRAY)
        _, btn_thresh = cv2.threshold(btn_gray, 180, 255, cv2.THRESH_BINARY)
        btn_text = pytesseract.image_to_string(btn_thresh, config="--psm 7").strip().lower()
        if "solo" in btn_text:
            return "RACE_READY"

        # 中心区域 OCR：用于 EventLab 相关页面
        center_roi = resized[int(h * 0.20) : int(h * 0.50), int(w * 0.10) : int(w * 0.50)]
        center_gray = cv2.cvtColor(center_roi, cv2.COLOR_BGR2GRAY)
        _, center_thresh = cv2.threshold(center_gray, 180, 255, cv2.THRESH_BINARY)
        center_text = pytesseract.image_to_string(center_thresh, config="--psm 6").strip().lower()

        # EVENTLAB_MENU: 含 "play event" 或 "eventlab"
        if "play" in center_text and "event" in center_text:
            return "EVENTLAB_MENU"
        if "eventlab" in center_text:
            return "EVENTLAB_MENU"

        # CREATIVE_HUB 子页面: 含 "creative" 或 "hub"
        if "creative" in center_text and "hub" in center_text:
            return "CREATIVE_HUB_PAGE"

        # EVENTS 页面（含子标签 Featured / Popular / My Favorites 等）
        # header 显示 "Events" → 检查 My Favorites 子标签是否已选中
        if "event" in car_title_text or "vents" in car_title_text:
            # 检测 My Favorites 子标签是否激活（h15-18%, w20-34%）
            fav_tab_roi = resized[int(h * 0.15) : int(h * 0.18), int(w * 0.20) : int(w * 0.34)]
            fav_gray = cv2.cvtColor(fav_tab_roi, cv2.COLOR_BGR2GRAY)
            _, fav_thresh = cv2.threshold(fav_gray, 180, 255, cv2.THRESH_BINARY)
            fav_text = pytesseract.image_to_string(fav_thresh, config="--psm 7").strip().lower()
            if "my" in fav_text and ("fav" in fav_text or "favorite" in fav_text):
                return "FAVORITES_LIST"
            return "EVENTS_SUBMENU"

        return None

    # ===================================================================
    #  B2. 赛事子菜单检测 (轮廓 + OCR)
    # ===================================================================

    def _detect_submenu(self, resized, h, w):
        """
        检测是否在 Events 子菜单界面。
        子菜单标签栏位于约 h8-12%，有多个水平排列的文字标签。
        """
        # 子菜单标签栏区域
        sub_roi = resized[int(h * 0.06) : int(h * 0.12), int(w * 0.10) : int(w * 0.90)]
        sub_gray = cv2.cvtColor(sub_roi, cv2.COLOR_BGR2GRAY)

        # 轮廓检测：寻找多个水平排列的小矩形/文字块
        _, sub_thresh = cv2.threshold(sub_gray, 180, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(sub_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 过滤：只保留合理大小的轮廓（标签文字块）
        sh, sw = sub_roi.shape[:2]
        tab_contours = []
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            if 20 < cw < sw * 0.3 and ch > sh * 0.2:
                tab_contours.append((x, y, cw, ch))

        if len(tab_contours) >= 3:
            # 多个水平排列的文字块 → 可能是子菜单
            # OCR 确认是否含子菜单关键字
            text = pytesseract.image_to_string(sub_thresh, config="--psm 6").strip().lower()
            submenu_kws = ["featured", "popular", "new", "favorite", "creator", "best", "trend", "my fav"]
            if any(kw in text for kw in submenu_kws):
                # 检查 MY_FAVORITES 是否为当前激活标签
                # 激活标签颜色更深/不同，用直方图或亮度区分
                return "EVENTS_SUBMENU"

        return None

    # ===================================================================
    #  B3. 主菜单标签检测 (像素亮度分析)
    # ===================================================================

    def _detect_active_tab(self, tab_roi, tab_gray):
        """
        检测主菜单哪个标签被选中。
        策略：选中标签的亮度/颜色与未选中不同。
              分析标签栏每个区域的直方图特征。

        使用方式:
          - 有参考数据时：比较直方图
          - 无参考数据时：分析亮度差异（选中标签通常更暗/更亮）
        """
        th, tw = tab_roi.shape[:2]

        # 为每个标签区域计算亮度
        zone_brightness = {}
        for tab_name, (x1_pct, x2_pct) in TAB_ZONES.items():
            zone = tab_gray[:, int(tw * x1_pct) : int(tw * x2_pct)]
            zone_brightness[tab_name] = float(np.mean(zone))

        # 策略：未选中标签亮度相近，选中标签亮度显著不同
        values = list(zone_brightness.values())
        median_brightness = float(np.median(values))

        # 找亮度偏差最大的标签
        max_diff = 0
        active_tab = None
        for tab_name, brightness in zone_brightness.items():
            diff = abs(brightness - median_brightness)
            if diff > max_diff:
                max_diff = diff
                active_tab = tab_name

        # 需要足够的差异才确认（阈值：至少偏差 15）
        if max_diff > 15 and active_tab:
            return active_tab

        # 如有参考数据，用直方图比较
        if self.tab_ref_brightness:
            best_tab, best_diff = None, 999
            for tab_name, ref_vals in self.tab_ref_brightness.items():
                diff = sum(abs(zone_brightness.get(k, 0) - ref_vals.get(k, 0)) for k in TAB_ZONES.keys())
                if diff < best_diff:
                    best_diff = diff
                    best_tab = tab_name
            if best_tab and best_diff < 200:
                return best_tab

        return None

    # ===================================================================
    #  E. 车辆选择检测 (OCR)
    # ===================================================================

    def detect_target_car(self, resized):
        """
        在选车界面检测当前高亮的车是否为目标车辆 (Subaru Impreza 22B-STI)。
        通过 OCR 读取左侧属性面板的品牌和等级信息。

        Returns:
            True 如果匹配目标车辆
        """
        h, w = resized.shape[:2]

        # 左侧属性面板区域 (约 w0-18%, h20-85%)
        panel_roi = resized[int(h * 0.20) : int(h * 0.85), 0 : int(w * 0.18)]
        gray = cv2.cvtColor(panel_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config="--psm 6").strip().lower()

        # 匹配 Subaru Impreza 22B-STI 的关键字
        has_brand = any(k in text for k in ["subaru", "sub"])
        has_class = "s2" in text or "889" in text
        return has_brand and has_class

    # ===================================================================
    #  MY_FAVORITES 守卫 (替代原 MY_FAVORITES 模板匹配)
    # ===================================================================

    def check_my_favorites_active(self, resized):
        """
        检查 MY FAVORITES 标签是否已激活。
        用于防止在错误的子菜单页选择赛事。

        原逻辑：检测未选中的 MY_FAVORITES 标签是否还可见（说明还没翻到该页）。
        新逻辑：OCR 子菜单标签栏，检查 "my favorites" 文字并判断是否高亮。
        """
        h, w = resized.shape[:2]
        sub_roi = resized[int(h * 0.06) : int(h * 0.12), int(w * 0.60) : int(w * 0.95)]
        gray = cv2.cvtColor(sub_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config="--psm 7").strip().lower()

        # 如果 "my favorites" 还在标签栏中可见（未选中状态），
        # 说明还没翻到该页
        if "my fav" in text or "favorites" in text:
            return False  # 未激活，还需要继续翻
        return True  # 已翻过该标签或已激活

    # ===================================================================
    #  校准辅助方法
    # ===================================================================

    def capture_reference(self, resized, state_name):
        """
        在当前界面采集参考数据，保存到参考文件。

        Args:
            resized: 当前 1600x900 截图
            state_name: 状态名称 (如 "RACE_END", "EVENTLAB_MENU" 等)
        """
        h, w = resized.shape[:2]

        data = {}
        if os.path.exists(self.ref_path):
            with open(self.ref_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        # 导航页面直方图
        if state_name in NAV_PAGES:
            roi_cfg = NAV_PAGES[state_name]["roi"]
            roi = resized[int(h * roi_cfg[0]) : int(h * roi_cfg[1]), int(w * roi_cfg[2]) : int(w * roi_cfg[3])]
            hist = compute_hist(roi)
            if "nav_hists" not in data:
                data["nav_hists"] = {}
            data["nav_hists"][state_name] = _hist_to_base64(hist)
            log_success(f"[校准] 保存导航直方图: {state_name}")

        # 比赛状态直方图
        elif state_name in RACING_ROIS:
            roi_cfg = RACING_ROIS[state_name]["roi"]
            roi = resized[int(h * roi_cfg[0]) : int(h * roi_cfg[1]), int(w * roi_cfg[2]) : int(w * roi_cfg[3])]
            hist = compute_hist(roi)
            if "racing_hists" not in data:
                data["racing_hists"] = {}
            data["racing_hists"][state_name] = _hist_to_base64(hist)
            log_success(f"[校准] 保存比赛直方图: {state_name}")

        # 主菜单标签亮度
        elif state_name.startswith("TAB_"):
            tab_roi = resized[
                int(h * TAB_BAR_Y[0]) : int(h * TAB_BAR_Y[1]), int(w * TAB_BAR_X[0]) : int(w * TAB_BAR_X[1])
            ]
            tab_gray = cv2.cvtColor(tab_roi, cv2.COLOR_BGR2GRAY)
            th, tw = tab_gray.shape[:2]
            brightness = {}
            for tab_name, (x1, x2) in TAB_ZONES.items():
                zone = tab_gray[:, int(tw * x1) : int(tw * x2)]
                brightness[tab_name] = float(np.mean(zone))
            if "tab_brightness" not in data:
                data["tab_brightness"] = {}
            data["tab_brightness"][state_name] = brightness
            log_success(f"[校准] 保存标签亮度: {state_name} -> {brightness}")

        # 全屏直方图（通用）
        else:
            hist = compute_hist(resized)
            if "nav_hists" not in data:
                data["nav_hists"] = {}
            data["nav_hists"][state_name] = _hist_to_base64(hist)
            log_success(f"[校准] 保存全屏直方图: {state_name}")

        with open(self.ref_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log_info(f"[校准] 参考数据已保存到 {self.ref_path}")


# ===================================================================
#  模块级单例：避免在热路径中反复实例化 StateDetector
# ===================================================================

_detector_instance: StateDetector | None = None


def get_detector(ref_path: str | None = None) -> StateDetector:
    """
    获取共享的 StateDetector 单例。

    StateDetector.__init__() 会从磁盘读取 JSON 并反序列化直方图数据，
    在 purchase.py 的导航循环中每帧都创建新实例会造成不必要的 I/O 开销。
    使用此函数可确保全局只创建一个实例。

    Args:
        ref_path: 可选的参考数据文件路径，仅在首次创建时生效

    Returns:
        StateDetector: 共享的检测器实例
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = StateDetector(ref_path)
    return _detector_instance
