# -*- coding: utf-8 -*-
"""
FH6_AutoBot 计算机视觉模块 (module_ocr.py)
===========================================
基于 OpenCV + Tesseract OCR 的游戏画面分析引擎，提供以下核心能力：

  1. OCR 文字识别
     - read_skill_points(): 读取技能点数字（多 PSM 投票 + 零技能点保底）
     - read_text_in_roi(): 通用 ROI 区域 OCR

  3. 颜色空间检测
     - has_green_selection_border(): 检测 Forza 高亮选中的绿色边框
     - has_green_selection_border_padded(): 带外扩的绿色边框检测
     - find_cursor_position(): 检测 UI 光标（亮黄绿色焦点框）的中心坐标
     - verify_new_target_car(): 双重校验（OCR 车名 + HSV 检测 NEW 黄色标签）
     - check_is_high_class(): 通过紫色 PI 徽章检测 S1/S2 级别车辆
     - has_cell_below(): 通过亮度/方差采样检测网格下方是否有车

所有函数的输入图像统一为 1600×900 缩放后的 BGR 格式截图。
"""

import os

import cv2
import numpy as np
import pytesseract
from colorama import Fore, Style

from engine.utils import log_error, log_success, log_warning, safe_print

# ==========================================
# 全局配置
# ==========================================

# 调试开关：设置为 True 时会在每次 OCR 调用时写入调试图片文件到当前目录
# 用于排查 OCR 识别失败时检查预处理后的图像质量
DEBUG_WRITE_FILES = False

# ==========================================
# HSV 颜色阈值常量（全局唯一真相源）
# ==========================================
# 以下阈值通过对 Forza Horizon 6 游戏 UI 的实际截图分析得出，
# 使用 HSV 色彩空间而非 RGB，因为 HSV 对亮度变化更鲁棒。
#
# 绿色边框阈值（用于检测选中状态的高亮绿色边框）
# H=35-85 覆盖从黄绿到蓝绿的范围
HSV_GREEN_BORDER_LOWER = np.array([35, 100, 40])
HSV_GREEN_BORDER_UPPER = np.array([85, 255, 255])

# 绿色光标阈值（用于检测 UI 焦点框，比边框阈值更宽松）
HSV_GREEN_CURSOR_LOWER = np.array([30, 200, 200])
HSV_GREEN_CURSOR_UPPER = np.array([45, 255, 255])

# 黄色 NEW 标签阈值（用于检测车辆卡片上的 "NEW" 标记）
# H=20-30 对应纯黄色范围
HSV_YELLOW_NEW_LOWER = np.array([20, 100, 100])
HSV_YELLOW_NEW_UPPER = np.array([30, 255, 255])

# ==========================================
# 卡片裁剪尺寸常量
# ==========================================
# 车库网格中单张车辆卡片的裁剪区域大小（以光标中心为基准）
CARD_CROP_W = 284  # 卡片裁剪宽度（像素）— 与实际高亮边框匹配
CARD_CROP_H = 217  # 卡片裁剪高度（像素）— 与实际高亮边框匹配

# ==========================================
# 目标车辆识别关键词（全局唯一真相源）
# ==========================================
# 1998 Subaru Impreza 22B-STI Version 的独特特征关键词
# "preza" 而非 "impreza"：CARD_CROP 左边缘裁切导致 OCR 读成 "apreza"/"vipreza"
# "22b" 始终稳定命中
# "1998" OCR 常误读为 "1905"/"1945"，改用 "sti" 作为第三标识
IMPREZA_22B_KEYWORDS: list[str] = ["preza", "22b", "sti"]
IMPREZA_22B_MIN_MATCH: int = 2  # 至少命中 2/3 个才算确认

# ==========================================
# 空位检测阈值
# ==========================================
EMPTY_SLOT_BRIGHTNESS_THRESHOLD: float = 50.0  # 亮度 ≤ 此值视为暗区
EMPTY_SLOT_VARIANCE_THRESHOLD: float = 5.0  # 方差 ≤ 此值视为纯色


# ==========================================
# 通用卡片裁剪
# ==========================================


def crop_card_roi(image: np.ndarray | None, cursor_x: int, cursor_y: int) -> np.ndarray | None:
    """根据光标中心坐标裁剪车辆卡片区域。

    在 1600×900 缩放画面中，以 (cursor_x, cursor_y) 为中心，
    裁剪 CARD_CROP_W × CARD_CROP_H 大小的矩形区域。
    坐标会被安全地钳位到图像边界内。

    Args:
        image: 1600×900 BGR 格式截图，None 时返回 None
        cursor_x: 光标中心 X 坐标
        cursor_y: 光标中心 Y 坐标

    Returns:
        裁剪后的卡片 BGR 图像，无效时返回 None
    """
    if image is None or image.size == 0:
        return None
    h, w = image.shape[:2]
    x1 = max(0, cursor_x - CARD_CROP_W // 2)
    x2 = min(w, cursor_x + CARD_CROP_W // 2)
    y1 = max(0, cursor_y - CARD_CROP_H // 2)
    y2 = min(h, cursor_y + CARD_CROP_H // 2)
    roi = image[y1:y2, x1:x2]
    return roi if roi.size > 0 else None


# ==========================================
# 一、Tesseract OCR 初始化
# ==========================================


def setup_tesseract() -> bool:
    """
    定位并配置 Tesseract OCR 引擎路径。

    查找策略：
    1. 先检查系统 PATH 中是否已有 Tesseract
    2. 如果没有，遍历 Windows 常见安装路径（Program Files 等）
    3. 找到后设置 pytesseract.pytesseract.tesseract_cmd

    返回:
        bool: True 表示配置成功，False 表示未找到 Tesseract
    """
    try:
        pytesseract.get_tesseract_version()
        log_success("Tesseract is available in system PATH.")
        return True
    except pytesseract.TesseractNotFoundError:
        pass

    # Windows 常见安装路径 + 本地 tools 目录 + PyInstaller 打包路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        from engine.runtime import get_base_dir, get_user_dir

        base_dir = get_base_dir()
        user_dir = get_user_dir()
    except ImportError:
        base_dir = os.path.dirname(script_dir)
        user_dir = base_dir
    common_paths = [
        os.path.join(script_dir, "tools", "tesseract", "tesseract.exe"),
        os.path.join(base_dir, "tools", "tesseract", "tesseract.exe"),
        os.path.join(user_dir, "tesseract", "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            log_success(f"Configured Tesseract path: {path}")
            return True

    log_warning("Tesseract OCR not found in common paths or PATH. OCR step may fail.")
    return False


# ==========================================
# 二、技能点 OCR 读取
# ==========================================


def read_skill_points(img: np.ndarray) -> int | None:
    """
    从游戏画面中 OCR 识别当前的技能点数字。

    技能点显示在暂停菜单 CARS 标签页的左侧区域。
    本函数使用多策略 OCR + 投票机制来提高识别准确率：

    处理流程：
    1. 根据 2560×1440 参考分辨率的百分比坐标裁剪技能点区域
    2. 灰度化 → Otsu 自适应阈值二值化 → 加边距 → 放大 3 倍
    3. 使用 PSM 7（单行文本模式）识别数字，精度最高
    4. 零技能点保底：如果 PSM 7 返回 0 或无结果，使用无限制 OCR 检测 "No Skill Points Available"

    参数:
        img: BGR 格式的游戏画面截图（原始分辨率）

    返回:
        int 或 None: 解析出的技能点数字，失败时返回 None
    """
    h, w, _ = img.shape

    # 技能点数字位于暂停菜单 Car Mastery 区域下方（蓝底黑字）
    # 手动标注确认：h: 72%-77%, w: 28.5%-30.5%
    crop_y1 = int(h * 0.72)
    crop_y2 = int(h * 0.77)
    crop_x1 = int(w * 0.285)
    crop_x2 = int(w * 0.305)

    roi = img[crop_y1:crop_y2, crop_x1:crop_x2]
    if roi.size == 0:
        return None

    # 每次都保存 ROI 原图到 debug/ 目录（便于排查识别问题）
    try:
        os.makedirs("debug", exist_ok=True)
        cv2.imwrite("debug/skill_points_roi.png", roi)
    except Exception:
        pass

    # 图像预处理：蓝底黑字 → 灰度 → Otsu 阈值 → 反转为黑字白底
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Tesseract 识别黑字白底效果最佳，确保数字为黑色、背景为白色
    # 检测当前极性：如果边缘像素多为黑色，说明背景是黑色，需要反转
    border_mean = (thresh[0, :].mean() + thresh[-1, :].mean() + thresh[:, 0].mean() + thresh[:, -1].mean()) / 4
    if border_mean < 128:
        # 白字黑底 → 反转为黑字白底
        thresh = cv2.bitwise_not(thresh)

    # 加大边距（40px 白色）+ 放大 4 倍（提升 Tesseract 小字识别率）
    # 注意：必须使用 INTER_LINEAR，INTER_CUBIC 在 4x 时会导致字形失真，Tesseract 漏读首位数字
    padded = cv2.copyMakeBorder(thresh, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    upscaled = cv2.resize(padded, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)

    # 保存预处理后图片（便于排查）
    try:
        cv2.imwrite("debug/skill_points_processed.png", upscaled)
    except Exception:
        pass

    # ===== OCR 识别（PSM 6 + PSM 7 双模式，取位数最多的结果） =====
    # PSM 6（自动分割）在各种缩放/边距组合下表现最稳定。
    # PSM 7（单行模式）作为备选。取位数最多的结果（漏读比幻读更常见）。
    best_val: int | None = None
    for psm in (6, 7):
        config = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
        try:
            text = pytesseract.image_to_string(upscaled, config=config).strip()
            if text.isdigit():
                val = int(text)
                safe_print(f"{Fore.CYAN}[OCR PSM{psm}]{Style.RESET_ALL} 识别结果: {val}")
                if best_val is None or len(text) > len(str(best_val)):
                    best_val = val
        except Exception:
            pass

    if best_val is not None and best_val > 0:
        safe_print(f"{Fore.GREEN}[OCR 最终]{Style.RESET_ALL} 采用值: {best_val}")
        return best_val

    # ===== 零技能点保底机制 =====
    # 当数字白名单 OCR 未检测到任何数字时，执行无限制 OCR 扫描。
    # 如果识别文本包含 "no", "avail", "point"（对应 "No Skill Points Available" 界面文字），
    # 或者文本为空，则可确信当前技能点为 0，应该开始刷图。
    try:
        raw_text = pytesseract.image_to_string(upscaled).strip().lower()
        if not raw_text or "no" in raw_text or "avail" in raw_text or "point" in raw_text:
            log_success(f"[零技能点检测] 成功匹配到零技能点界面特征 (识别文本: '{raw_text}')，判定当前技能点为 0。")
            return 0
    except Exception:
        pass

    return None


# ==========================================
# 三、通用卡片 OCR 管线
# ==========================================


def _ocr_card_text(card_img: np.ndarray | None, debug_label: str = "CARD") -> str:
    """
    通用卡片文字提取管线（内部函数）。

    处理流程：灰度化 → 反向二值化 → 加边距 → 2 倍放大 → Tesseract OCR
    使用反向二值化（THRESH_BINARY_INV）是因为 Forza UI 的卡片文字通常是
    浅色文字在深色背景上，反向后变成黑字白底，更适合 Tesseract 识别。

    参数:
        card_img: BGR 格式的卡片区域裁剪图
        debug_label: 调试输出时的标签名（用于区分不同调用场景）

    返回:
        str: 小写化的 OCR 识别文本，失败时返回空字符串
    """
    if card_img is None or card_img.size == 0:
        return ""
    try:
        gray = cv2.cvtColor(card_img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        padded = cv2.copyMakeBorder(thresh, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        upscaled = cv2.resize(padded, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        text = pytesseract.image_to_string(upscaled).strip().lower()
        # 高可见性调试输出
        try:
            safe_print(f"\n{Fore.BLUE}=================== [{debug_label} OCR] ===================")
            safe_print(f"{Fore.BLUE}Recognized text:")
            safe_print(Fore.WHITE + (text if text else "[empty]"))
            safe_print(f"{Fore.BLUE}{'=' * (len(debug_label) + 36)}\n")
        except Exception:
            pass  # safe_print 编码降级保护
        return text
    except Exception as e:
        log_error(f"_ocr_card_text ({debug_label}) error: {e}")
    return ""


# ==========================================
# 四、绿色选中边框检测
# ==========================================


def has_green_selection_border(card_img: np.ndarray | None) -> bool:
    """
    检测卡片图像是否具有绿色选中高亮边框。

    Forza Horizon 6 的 UI 中，当前选中的卡片会有一圈亮绿色的发光边框。
    本函数通过以下步骤检测：
    1. 创建只覆盖卡片外围 15 像素的边框掩码
    2. 在 HSV 色彩空间中筛选绿色像素
    3. 将绿色掩码与边框掩码做 AND 运算
    4. 统计绿色像素数量，超过 1500 个判定为"已选中"

    参数:
        card_img: BGR 格式的卡片区域裁剪图

    返回:
        bool: True 表示卡片被绿色高亮选中
    """
    if card_img is None or card_img.size == 0:
        return False
    try:
        h, w, _ = card_img.shape
        hsv = cv2.cvtColor(card_img, cv2.COLOR_BGR2HSV)

        # 创建仅覆盖外围 15 像素的边框区域掩码
        border_mask = np.zeros((h, w), dtype=np.uint8)
        border_thickness = 15
        border_mask[0:border_thickness, :] = 255  # 上边
        border_mask[h - border_thickness : h, :] = 255  # 下边
        border_mask[:, 0:border_thickness] = 255  # 左边
        border_mask[:, w - border_thickness : w] = 255  # 右边

        # 在 HSV 空间中过滤绿色像素
        lower_green = HSV_GREEN_BORDER_LOWER
        upper_green = HSV_GREEN_BORDER_UPPER

        # 使用 bitwise_and 将绿色掩码限定在边框区域内
        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        green_border_mask = cv2.bitwise_and(green_mask, border_mask)
        green_pixel_count = np.sum(green_border_mask == 255)

        # 调试输出绿色像素计数
        try:
            safe_print(
                f"{Fore.GREEN}[BORDER DEBUG]{Style.RESET_ALL} 边缘绿色边框像素点计数: {green_pixel_count} / 800 (阈值)"
            )
        except Exception:
            pass

        return green_pixel_count >= 800
    except Exception as e:
        log_error(f"Error checking green selection border: {e}")
    return False


def has_green_selection_border_padded(
    image: np.ndarray | None,
    box_x: int,
    box_y: int,
    box_w: int,
    box_h: int,
    pad: int = 20,
) -> bool:
    """
    带外扩边距的绿色选中边框检测（更鲁棒的版本）。

    与 has_green_selection_border 的区别：
    - 不是在裁剪后的卡片图上检测，而是在原始场景图上检测
    - 在匹配位置周围额外扩展 pad 像素，覆盖模板裁剪偏移导致的边框遗漏
    - 更适合 OCR 定位后的二次验证

    参数:
        scene_img: 完整的 1600×900 场景截图
        crop_x, crop_y: 目标位置的左上角坐标
        w, h: 目标区域的宽度和高度
        pad: 外扩边距（默认 30 像素）

    返回:
        bool: True 表示该区域周围有绿色高亮边框
    """
    if image is None or image.size == 0:
        return False
    try:
        scene_h, scene_w, _ = image.shape

        # 计算带外扩的裁剪坐标（确保不超出画面边界）
        y1 = max(0, box_y - pad)
        y2 = min(scene_h, box_y + box_h + pad)
        x1 = max(0, box_x - pad)
        x2 = min(scene_w, box_x + box_w + pad)

        crop_padded = image[y1:y2, x1:x2]
        hsv = cv2.cvtColor(crop_padded, cv2.COLOR_BGR2HSV)

        # 在整个外扩区域中统计绿色像素（不区分边框/内容）
        lower_green = HSV_GREEN_BORDER_LOWER
        upper_green = HSV_GREEN_BORDER_UPPER

        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        green_pixel_count = np.sum(green_mask == 255)

        # 调试输出
        try:
            safe_print(
                f"{Fore.GREEN}[BORDER DEBUG]{Style.RESET_ALL} 区域(含外扩边框)绿色高亮像素点计数: {green_pixel_count} / 800 (阈值)"
            )
        except Exception:
            pass

        return green_pixel_count >= 800
    except Exception as e:
        log_error(f"Error checking padded green selection border: {e}")
    return False


# ==========================================
# 五、UI 光标定位
# ==========================================


def find_cursor_position(image: np.ndarray | None) -> tuple[int, int] | None:
    """
    在 1600×900 缩放画面中定位 UI 焦点光标的中心坐标。

    Forza Horizon 6 的 UI 中，当前聚焦的元素会被一个亮黄绿色的矩形边框包围。
    本函数通过以下步骤检测该边框的中心位置：

    1. 将画面从 BGR 转为 HSV 色彩空间
    2. 使用 inRange 过滤出亮黄绿色像素（H=35-85, S>=80, V>=80）
    3. 使用 findContours 寻找所有绿色轮廓
    4. 过滤面积 < 300 的噪声轮廓
    5. 按面积降序排列，选取第一个通过车库网格形状校验的轮廓

    形状校验规则（排除误检的标签栏/标题高亮）：
    - 宽高比不超过 4:1（排除 558×61 这种极扁的标签栏高亮）
    - 最短边 >= 50 像素（排除过细的 UI 装饰线条）
    - 中心 Y 坐标 > 150（排除顶部标签栏区域的高亮）

    参数:
        image: 1600×900 BGR 格式截图

    返回:
        tuple(int, int) 或 None: 光标中心坐标 (cx, cy)，检测不到时返回 None
    """
    if image is None or image.size == 0:
        return None
    try:
        img_h, img_w = image.shape[:2]
        # PERF-4: 先裁剪有效区域再做 HSV 转换，减少 ~35% 像素量
        # 左侧 21% 是详情面板，顶部 19% 是标签栏 — 不含车库网格光标
        crop_x_offset = int(img_w * 0.21)
        crop_y_offset = int(img_h * 0.19)
        roi = image[crop_y_offset:, crop_x_offset:]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # 亮黄绿色的 HSV 阈值范围（适用于地平线 UI 高亮绿色边框）
        lower_green = HSV_GREEN_CURSOR_LOWER
        upper_green = HSV_GREEN_CURSOR_UPPER

        mask = cv2.inRange(hsv, lower_green, upper_green)

        # 闭运算（先膨胀后腐蚀）：将高亮边框的 4 条细线桥接为完整矩形轮廓
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 寻找绿色区域的轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # 过滤面积过小的噪声轮廓（阈值 300 像素）
        valid_contours = [c for c in contours if cv2.contourArea(c) >= 300]
        if not valid_contours:
            return None

        # 按面积降序排列，优先尝试最大的轮廓
        valid_contours.sort(key=cv2.contourArea, reverse=True)

        for contour in valid_contours:
            x, y, w, h = cv2.boundingRect(contour)
            # 加回裁剪偏移，映射回原始 1600×900 坐标系
            cx = x + w // 2 + crop_x_offset
            cy = y + h // 2 + crop_y_offset
            area = cv2.contourArea(contour)

            # === 形状校验：排除非车库网格元素（标签栏、菜单标题等） ===
            aspect_ratio = max(w, h) / max(min(w, h), 1)
            min_dim = min(w, h)

            if aspect_ratio > 4.0:
                # 宽高比过大 → 这是标签栏/标题高亮，不是车辆卡片
                try:
                    safe_print(
                        f"{Fore.YELLOW}[DYNAMIC VISION]{Style.RESET_ALL} 跳过异形轮廓: {w}x{h} (宽高比={aspect_ratio:.1f}>4.0), 面积={area:.0f}"
                    )
                except Exception:
                    pass
                continue

            if min_dim < 50:
                # 最短边太小 → UI 装饰线条或小标签
                try:
                    safe_print(
                        f"{Fore.YELLOW}[DYNAMIC VISION]{Style.RESET_ALL} 跳过过小轮廓: {w}x{h} (最短边={min_dim}<50), 面积={area:.0f}"
                    )
                except Exception:
                    pass
                continue

            if cy <= 150:
                # 中心在画面顶部 → 标签栏区域，不是车库网格
                try:
                    safe_print(
                        f"{Fore.YELLOW}[DYNAMIC VISION]{Style.RESET_ALL} 跳过顶部轮廓: (cx={cx}, cy={cy}) 在标签栏区域 (cy<=150), {w}x{h}"
                    )
                except Exception:
                    pass
                continue

            # 通过所有校验 → 这是车库网格中的光标
            try:
                safe_print(
                    f"{Fore.GREEN}[DYNAMIC VISION]{Style.RESET_ALL} 找到高亮焦点位置: (cx={cx}, cy={cy}), 边框尺寸: {w}x{h}, 面积: {area:.0f}"
                )
            except Exception:
                pass
            return cx, cy

        # 所有轮廓都未通过校验 → 输出调试信息
        top = valid_contours[0]
        x, y, w, h = cv2.boundingRect(top)
        try:
            safe_print(
                f"{Fore.RED}[DYNAMIC VISION]{Style.RESET_ALL} 所有轮廓均未通过车库网格校验！最大轮廓: {w}x{h} at ({x + w // 2 + crop_x_offset}, {y + h // 2 + crop_y_offset}), 面积={cv2.contourArea(top):.0f}"
            )
        except Exception:
            pass
        return None
    except Exception as e:
        log_error(f"find_cursor_position 执行出错: {e}")
    return None


# ==========================================
# 六、车辆卡片校验函数
# ==========================================


def verify_new_target_car(
    image: np.ndarray | None,
    cursor_x: int,
    cursor_y: int,
    target_keyword: str = "IMPREZA",
) -> bool:
    """
    双重目标锁定校验机制：OCR 车名 + NEW 标签检测。

    在车库网格导航中，模板匹配可能会误触相邻的非目标车辆。
    本函数通过两道独立的校验来确保精确度：

    校验 1 — OCR 车名文字检测：
      - 在光标位置裁剪卡片区域
      - OCR 识别文字，检查是否包含目标关键字（如 "IMPREZA"）
      - 支持完整匹配 + 滑动窗口部分匹配 + 备选关键字（"22b", "sti", "subaru"）

    校验 2 — NEW 黄色标签 HSV 检测：
      - 在卡片底部右侧区域检测黄色像素
      - NEW 标签表示该车尚未加过技能点，是目标车辆
      - 阈值：黄色像素 > 300 即判定有 NEW 标签

    两道校验都通过才返回 True。

    参数:
        image: 1600×900 BGR 格式截图
        cursor_x, cursor_y: 当前光标中心坐标
        target_keyword: 目标车名关键字（默认 "IMPREZA"）

    返回:
        bool: True 表示双重校验通过
    """
    if image is None or image.size == 0:
        return False
    try:
        roi = crop_card_roi(image, cursor_x, cursor_y)
        if roi is None:
            return False

        # --- 校验 1: OCR 多关键词全命中检查 ---
        # 1998 Subaru Impreza 22B-STi Version 的独特特征关键词
        # 要求至少命中 2 个才算锁定，避免误选其它 Subaru 车型
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        padded = cv2.copyMakeBorder(thresh, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        upscaled = cv2.resize(padded, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        text = pytesseract.image_to_string(upscaled).strip().lower()

        # 目标车特征关键词匹配（使用全局常量）
        matched_kws = [kw for kw in IMPREZA_22B_KEYWORDS if kw in text]
        has_keyword = len(matched_kws) >= IMPREZA_22B_MIN_MATCH

        if has_keyword:
            safe_print(f"{Fore.GREEN}  [多关键词命中] 匹配 {len(matched_kws)}/3: {matched_kws}{Style.RESET_ALL}")

        # --- 校验 2: HSV 颜色检查（寻找 'NEW' 黄色标签） ---
        # NEW 标签位于卡片右侧 → 高度 71%-82%、宽度 82%-96%
        roi_h, roi_w = roi.shape[:2]
        roi_bottom = roi[int(roi_h * 0.71) : int(roi_h * 0.82), int(roi_w * 0.82) : int(roi_w * 0.96)]
        hsv_roi = cv2.cvtColor(roi_bottom, cv2.COLOR_BGR2HSV)
        lower_yellow = HSV_YELLOW_NEW_LOWER
        upper_yellow = HSV_YELLOW_NEW_UPPER

        yellow_mask = cv2.inRange(hsv_roi, lower_yellow, upper_yellow)
        yellow_pixels = cv2.countNonZero(yellow_mask)

        has_new_tag = yellow_pixels > 300

        # --- 校验 3: LEGENDARY 橙色稀有度标签检测 ---
        # 1998 Impreza 22B 固定为 LEGENDARY（橙色底色），COMMON/RARE/EPIC 不是目标车
        # 稀有度标签区域: 卡片高度 82%-94%、宽度 4%-70%
        rarity_roi = roi[int(roi_h * 0.82) : int(roi_h * 0.94), int(roi_w * 0.04) : int(roi_w * 0.70)]
        if rarity_roi.size > 0:
            hsv_rarity = cv2.cvtColor(rarity_roi, cv2.COLOR_BGR2HSV)
            # 橙色 HSV: H=10-25, S>100, V>100
            orange_mask = cv2.inRange(hsv_rarity, np.array([10, 100, 100]), np.array([25, 255, 255]))
            orange_pixels = cv2.countNonZero(orange_mask)
            has_legendary = orange_pixels > 200
        else:
            orange_pixels = 0
            has_legendary = False

        # --- 综合判断（三重校验） ---
        if has_keyword and has_new_tag and has_legendary:
            log_success(
                f"[锁定成功] 三重校验通过！关键词 {len(matched_kws)}/3 {matched_kws} + NEW标签 ({yellow_pixels}px) + LEGENDARY ({orange_pixels}px)"
            )
            return True
        else:
            # 打印失败原因（方便调试）
            log_warning("[锁定失败] 三重校验未全部通过:")
            if not has_keyword:
                log_warning(
                    f"  ❌ 原因1：关键词不足 (命中 {len(matched_kws)}/3 {matched_kws}, 需≥2, OCR: '{text.replace(chr(10), ' ')}')"
                )
            else:
                log_success(f"  ✓ 检查1：关键词命中 {len(matched_kws)}/3 {matched_kws}")

            if not has_new_tag:
                log_warning(f"  ❌ 原因2：没有检测到 'NEW' 标签 (黄色像素: {yellow_pixels} <= 300)")
            else:
                log_success(f"  ✓ 检查2：检测到 'NEW' 标签 (黄色像素: {yellow_pixels})")

            if not has_legendary:
                log_warning(f"  ❌ 原因3：不是 LEGENDARY (橙色像素: {orange_pixels} <= 200)")
            else:
                log_success(f"  ✓ 检查3：LEGENDARY 橙色标签 (橙色像素: {orange_pixels})")

            return False

    except Exception as e:
        log_error(f"verify_new_target_car 校验出错: {e}")
    return False


def check_new_tag_only(image: np.ndarray | None, cursor_x: int, cursor_y: int) -> bool:
    """
    仅检测 NEW 黄色标签（跳过 OCR 车名校验的轻量版本）。

    使用场景：当模板匹配已给出高分（> 0.95）时，车辆身份已被模板确认，
    只需要确认该车是否是尚未加过技能点的"新车"。

    检测原理：
    在卡片底部右侧 45% 的区域中，统计 HSV 黄色像素数量。
    黄色像素 > 300 即判定存在 NEW 标签。

    参数:
        image: 1600×900 BGR 格式截图
        cursor_x, cursor_y: 当前光标中心坐标

    返回:
        bool: True 表示有 NEW 标签（新车），False 表示已加过点
    """
    if image is None or image.size == 0:
        return False
    try:
        roi = crop_card_roi(image, cursor_x, cursor_y)
        if roi is None:
            return False

        # NEW 标签在卡片右侧 → 高度 71%-82%、宽度 82%-96%
        roi_h, roi_w = roi.shape[:2]
        roi_bottom = roi[int(roi_h * 0.71) : int(roi_h * 0.82), int(roi_w * 0.82) : int(roi_w * 0.96)]
        hsv_roi = cv2.cvtColor(roi_bottom, cv2.COLOR_BGR2HSV)
        lower_yellow = HSV_YELLOW_NEW_LOWER
        upper_yellow = HSV_YELLOW_NEW_UPPER
        yellow_mask = cv2.inRange(hsv_roi, lower_yellow, upper_yellow)
        yellow_pixels = cv2.countNonZero(yellow_mask)

        has_new = yellow_pixels > 300
        if has_new:
            log_success(f"[NEW 标签检测] ✓ 检测到 NEW 标签 (黄色像素: {yellow_pixels}，区域:卡片底部)")
        else:
            log_warning(
                f"[NEW 标签检测] ✗ 未检测到 NEW 标签 (黄色像素: {yellow_pixels} <= 300，区域:卡片底部)，可能已加过点"
            )
        return has_new
    except Exception as e:
        log_error(f"check_new_tag_only 出错: {e}")
    return False


def check_is_high_class(image: np.ndarray | None, cursor_x: int, cursor_y: int) -> bool:
    """
    检测当前卡片的车辆是否为高级别（S1/S2 等）。

    用途：在删车流程中保护用户的主力车（S2 825 Impreza）不被误删。
    B 级车是可以安全删除的，而 S1/S2 级别的车是用户手动升级的主力车。

    检测原理（基于 PI 徽章颜色）：
    - S2 主力车: 徽章左半部分是 **蓝色**，右半部分是黑色
    - B 级车:    徽章左半部分是 **橙色**，右半部分是黑色
    通过 HSV 检测蓝色 vs 橙色像素数量来判定级别。

    参数:
        image: 1600×900 BGR 格式截图
        cursor_x, cursor_y: 当前光标中心坐标

    返回:
        bool: True 表示是高级别车（应跳过），False 表示是 B 级车
    """
    if image is None or image.size == 0:
        return False
    try:
        card = crop_card_roi(image, cursor_x, cursor_y)
        if card is None:
            return False

        card_h, card_w = card.shape[:2]
        # PI 徽章: 卡片高度 82%-94%、宽度 71%-96% 区域
        # 只看右侧 PI 徽章 (S2/B)，避开左侧 LEGENDARY 金色标签和右侧越界
        badge = card[int(card_h * 0.82) : int(card_h * 0.94), int(card_w * 0.71) : int(card_w * 0.96)]

        hsv = cv2.cvtColor(badge, cv2.COLOR_BGR2HSV)

        # 蓝色 (S1/S2 徽章): H=100-130, S>50, V>50
        blue_mask = cv2.inRange(hsv, np.array([100, 50, 50]), np.array([130, 255, 255]))
        blue_pixels = cv2.countNonZero(blue_mask)

        # 橙色 (B 级徽章): H=5-25, S>100, V>100
        orange_mask = cv2.inRange(hsv, np.array([5, 100, 100]), np.array([25, 255, 255]))
        orange_pixels = cv2.countNonZero(orange_mask)

        # 判定: 蓝色多 → S2，橙色多 → B 级
        if blue_pixels > orange_pixels and blue_pixels > 50:
            log_warning(f"[PI 检测] ⚠ 检测到高级别车辆 (蓝色: {blue_pixels} > 橙色: {orange_pixels})")
            return True

        if orange_pixels > blue_pixels and orange_pixels > 50:
            log_success(f"[PI 检测] ✓ B 级车辆 (橙色: {orange_pixels} > 蓝色: {blue_pixels})")
            return False

        # 兜底: 两种颜色都不明确，保守处理 — 宁可漏删不可误删 S2 主力车
        log_warning(f"[PI 检测] ⚠ 颜色不明确 (蓝色: {blue_pixels}, 橙色: {orange_pixels})，保守跳过")
        return True
    except Exception as e:
        log_error(f"check_is_high_class 出错: {e}")
    return False


# ==========================================
# 八、通用 ROI 区域 OCR
# ==========================================


def read_text_in_roi(
    image: np.ndarray | None,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    whitelist: str | None = None,
) -> str:
    """
    在指定的 ROI（Region of Interest）矩形区域内执行 OCR 文字识别。

    处理流程：
    1. 根据坐标裁剪 ROI 区域
    2. 放大 3 倍以提升小字体识别率
    3. 转灰度（不做二值化，保留更多细节）
    4. 使用 PSM 7（单行文本模式）识别

    参数:
        image: 1600×900 BGR 格式截图
        x1, y1, x2, y2: ROI 矩形区域的坐标
        whitelist: 可选，OCR 字符白名单（如 "0123456789" 只识别数字）

    返回:
        str: 小写化的 OCR 识别文本，失败时返回空字符串
    """
    if image is None or image.size == 0:
        return ""
    try:
        h, w, _ = image.shape
        # 确保坐标在有效范围内
        rx1 = max(0, int(x1))
        rx2 = min(w, int(x2))
        ry1 = max(0, int(y1))
        ry2 = min(h, int(y2))

        roi = image[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            return ""

        # 保存调试原图（仅在调试模式下）
        if DEBUG_WRITE_FILES:
            cv2.imwrite("debug_ocr_raw.png", roi)

        # 图像预处理：放大 3 倍 → 灰度化
        resized_roi = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(resized_roi, cv2.COLOR_BGR2GRAY)

        if DEBUG_WRITE_FILES:
            cv2.imwrite("debug_ocr_processed.png", gray)

        # OCR 识别配置
        config_str = "--psm 7"  # 单行文本模式
        if whitelist is not None:
            config_str += f" -c tessedit_char_whitelist={whitelist}"

        text = pytesseract.image_to_string(gray, config=config_str).strip().lower()
        return text
    except Exception as e:
        log_error(f"read_text_in_roi OCR 识别出错: {e}")
    return ""


# ==========================================
# 九、车库网格空位检测
# ==========================================


def has_cell_below(image: np.ndarray | None, cursor_x: int, cursor_y: int) -> bool:
    """
    检测光标下方一行位置是否存在车辆卡片（非空位）。

    使用 CARD_CROP 百分比定位采样区域：
    高度 87%-153%、宽度 13%-88%（相对于 CARD_CROP 裁剪区域）。
    该区域覆盖当前卡片下方到下一行卡片的主体部分。

    判断规则：
    - 空位背景通常很暗（亮度 < 40）且颜色单调（方差 < 15）
    - 车辆卡片通常较亮（亮度 > 40）且有丰富的色彩变化（方差 > 15）
    - 满足任一条件即判定有车

    参数:
        image: 1600×900 BGR 格式截图
        cursor_x, cursor_y: 当前光标中心坐标

    返回:
        bool: True = 下方有车辆卡片, False = 下方是空位或超出边界
    """
    if image is None or image.size == 0:
        return False
    try:
        h, w, _ = image.shape
        crop_w, crop_h = CARD_CROP_W, CARD_CROP_H

        # CARD_CROP 区域的绝对坐标
        card_x1 = max(0, cursor_x - crop_w // 2)
        card_y1 = max(0, cursor_y - crop_h // 2)

        # 采样区域: h101%-192%, w4%-97%
        sy1 = max(0, int(card_y1 + crop_h * 1.01))
        sy2 = min(h, int(card_y1 + crop_h * 1.92))
        sx1 = max(0, int(card_x1 + crop_w * 0.04))
        sx2 = min(w, int(card_x1 + crop_w * 0.97))

        # 超出画面底部 → 没有下一行
        if sy1 >= h - 30:
            safe_print(f"{Fore.YELLOW}[GRID]{Style.RESET_ALL} 下方超出画面边界 (sy1={sy1}, h={h})")
            return False

        sample = image[sy1:sy2, sx1:sx2]
        if sample.size == 0:
            return False

        # 计算采样区域的统计特征
        gray_sample = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray_sample))  # 平均亮度
        std_brightness = float(np.std(gray_sample))  # 亮度方差（颜色丰富度）

        # 判断规则：亮度 > 40 或方差 > 15 即视为有车
        has_car = mean_brightness > 40 or std_brightness > 15

        safe_print(
            f"{Fore.CYAN}[GRID]{Style.RESET_ALL} 下方单元格检测: 亮度={mean_brightness:.1f}, 方差={std_brightness:.1f} → {'有车' if has_car else '空位'}"
        )
        return has_car

    except Exception as e:
        log_error(f"has_cell_below 检测出错: {e}")
    return False


# ==========================================
# 十、车库网格空位检测（统一版）
# ==========================================


def is_empty_slot(image: np.ndarray, cursor_x: int, cursor_y: int) -> bool:
    """
    检测当前光标所在的车库卡片是否为空位。

    通过采样当前卡片下半部分区域（CARD_CROP h87%-153%, w13%-88%）的
    亮度和方差来判断：
    - 空位背景：亮度 ≤ 50 且方差 ≤ 5（几乎纯色深灰）
    - 车辆卡片：亮度 > 50 或方差 > 5（有图像/文字内容）

    此函数是所有车库网格扫描模块的统一空位检测入口，
    替代之前分散在 garage.py 中的 4 处重复内联实现。

    Args:
        image: 1600×900 BGR 格式截图
        cursor_x: 当前光标中心 X 坐标
        cursor_y: 当前光标中心 Y 坐标

    Returns:
        bool: True = 空位, False = 有车辆卡片
    """
    if image is None or image.size == 0:
        return True
    try:
        crop_w, crop_h = CARD_CROP_W, CARD_CROP_H
        card_x1 = max(0, cursor_x - crop_w // 2)
        card_y1 = max(0, cursor_y - crop_h // 2)
        sy1 = max(0, int(card_y1 + crop_h * 0.87))
        sy2 = min(image.shape[0], int(card_y1 + crop_h * 1.53))
        sx1 = max(0, int(card_x1 + crop_w * 0.13))
        sx2 = min(image.shape[1], int(card_x1 + crop_w * 0.88))
        sample = image[sy1:sy2, sx1:sx2]
        if sample.size == 0:
            return True
        gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        std_brightness = float(np.std(gray))
        is_empty = (
            mean_brightness <= EMPTY_SLOT_BRIGHTNESS_THRESHOLD and std_brightness <= EMPTY_SLOT_VARIANCE_THRESHOLD
        )
        if is_empty:
            safe_print(
                f"{Fore.YELLOW}[GRID]{Style.RESET_ALL} "
                f"空位检测: 亮度={mean_brightness:.1f}, "
                f"方差={std_brightness:.1f} → 空位"
            )
        return is_empty
    except Exception as e:
        log_error(f"is_empty_slot 检测出错: {e}")
    return True


# ==========================================
# 十一、品牌标签栏选中检测（统一版）
# ==========================================

# 品牌标签栏的默认 ROI（百分比坐标）
BRAND_TAB_ROI_Y: tuple[float, float] = (0.14, 0.18)
BRAND_TAB_ROI_X: tuple[float, float] = (0.09, 0.91)


def detect_selected_brand_tab(
    raw_img: np.ndarray,
    roi_y: tuple[float, float] = BRAND_TAB_ROI_Y,
    roi_x: tuple[float, float] = BRAND_TAB_ROI_X,
) -> str | None:
    """
    检测品牌标签栏中当前选中（高亮）的标签文字。

    算法原理：
    游戏 UI 中，选中的品牌标签背景色更暗（深色高亮），未选中的标签背景较亮。
    通过在标签栏灰度图上滑动窗口（10% 宽度，步长 5px），找到平均亮度最低的区域，
    然后向两侧扩展（阈值 120）找到完整的暗区范围，最后对该暗区做 OCR 识别文字。

    此函数统一了之前分散在 navigation.py 和 garage.py 中的 2 处重复实现。

    Args:
        raw_img: 原始分辨率 BGR 截图
        roi_y: 标签栏垂直范围 (y1%, y2%)，默认 (0.14, 0.18)
        roi_x: 标签栏水平范围 (x1%, x2%)，默认 (0.09, 0.91)

    Returns:
        str: 选中标签的 OCR 文字（小写），检测失败返回 None
    """
    if raw_img is None or raw_img.size == 0:
        return None

    rh, rw = raw_img.shape[:2]
    tab_strip = raw_img[int(rh * roi_y[0]) : int(rh * roi_y[1]), int(rw * roi_x[0]) : int(rw * roi_x[1])]
    if tab_strip.size == 0:
        return None

    tab_gray = cv2.cvtColor(tab_strip, cv2.COLOR_BGR2GRAY)
    tab_w = tab_gray.shape[1]
    win = int(tab_w * 0.10)
    if win <= 0 or tab_w <= win:
        return None

    # 滑动窗口找最暗区域
    min_mean: float = 999.0
    min_x: int = 0
    for xi in range(0, tab_w - win, 5):
        m = float(np.mean(tab_gray[:, xi : xi + win]))
        if m < min_mean:
            min_mean = m
            min_x = xi

    # 向两侧扩展暗区
    xs, xe = min_x, min_x + win
    while xs > 0 and float(np.mean(tab_gray[:, max(0, xs - 10) : xs])) < 120:
        xs -= 10
    while xe < tab_w and float(np.mean(tab_gray[:, xe : min(tab_w, xe + 10)])) < 120:
        xe += 10

    # OCR 选中标签文字
    sel_roi = tab_strip[:, xs:xe]
    if sel_roi.size == 0:
        return None
    sel_gray = cv2.cvtColor(sel_roi, cv2.COLOR_BGR2GRAY)
    _, sel_thresh = cv2.threshold(sel_gray, 150, 255, cv2.THRESH_BINARY)

    try:
        text = pytesseract.image_to_string(sel_thresh, config="--psm 7").strip().lower()
        return text if text else None
    except Exception as e:
        log_error(f"detect_selected_brand_tab OCR 异常: {e}")
        return None
