# -*- coding: utf-8 -*-
"""
FH6_AutoBot 核心状态机 + 手柄宏 + 视觉导航引擎 (module_macro.py)
================================================================
本模块是整个自动化系统的核心，包含：

  1. 主状态机 (run_master_bot_loop)
     四阶段无限循环：刷点 -> 买车 -> 加点 -> 卖车 -> (循环)

  2. 五步视觉导航系统 (navigate_to_impreza_purchase_screen)
     Campaign -> Collection Journal -> Navigator -> Car Collection -> Subaru -> Impreza
     每一步都经过: 模板匹配 + OCR 校验 + 绿色高亮边框校验 三重确认

  3. 车库网格导航引擎 (_navigate_garage_grid)
     打字机走位遍历 3行×N列，支持多种校验函数（NEW标签/级别检测）

  4. 手柄宏操作
     action_buy_single_car / action_upgrade_car_skills / action_remove_single_car
     action_get_in_car / navigate_menu_to_garage 等

  5. 视觉刷车引擎
     dynamic_navigate_to_target / safe_exit_to_menu / return_to_garage
"""

import time
import sys
import os
import cv2
import mss
import numpy as np
import vgamepad as vg
import ctypes
from ctypes import wintypes
from colorama import Fore, Style
import module_ocr
from module_ocr import DEBUG_WRITE_FILES
from utils import (
    safe_print, log_info, log_success, log_warning, log_error,
    find_game_window, force_foreground, get_client_rect,
    press_button as _press_button
)

import pytesseract
import re

def log_state_header(state, description):
    safe_print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    safe_print(f"{Fore.MAGENTA}{Style.BRIGHT}   🔥 当前状态: {state}")
    safe_print(f"{Fore.MAGENTA}{Style.BRIGHT}   👉 任务描述: {description}")
    safe_print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}")

# ==========================================
# 一、 全局配置参数
# ==========================================

MAX_SKILL_POINTS = 999     # 技能点满值上限

POINTS_PER_CAR = 30        # 每辆 Impreza 技能树加满超级抽奖需要 30 点

# 每轮循环能够处理的车辆数 = 999 // 30 = 33 辆
CARS_TO_PROCESS = MAX_SKILL_POINTS // POINTS_PER_CAR

# 主状态机的四个状态常量（循环顺序：刷点 -> 买车 -> 加点 -> 卖车 -> 刷点...）
STATE_BUY_CARS = "STATE_BUY_CARS"         # 阶段 2：批量购买 Subaru Impreza
STATE_UPGRADE_CARS = "STATE_UPGRADE_CARS" # 阶段 3：逐辆消耗技能点升级技能树
STATE_TRASH_CARS = "STATE_TRASH_CARS"     # 阶段 4：移除已升级的 Impreza、保留主力车
STATE_FARM_POINTS = "STATE_FARM_POINTS"   # 阶段 1：自动跑 EventLab 刷到 999 技能点

# MSS singleton - use shared instance from utils to avoid duplicate GDI handles
_get_mss = None  # will be set after import

def _get_mss():
    """Proxy to shared MSS singleton in utils.py"""
    from utils import get_mss
    return get_mss()

# 焦点检查节流（避免每帧 1.5s 的抢焦点延迟）

_last_foreground_check = 0

_FOREGROUND_CHECK_INTERVAL = 10.0  # max check foreground window once per 10 seconds

def _scan_for_subaru_page(hwnd, gamepad, anchor_templates, max_presses=15):
    """
    车库内循环按 LB（左肩键）翻页，直到检测到 Subaru_page.png 模板。
    用于在车库网格中快速定位到 Subaru 品牌页面。
    返回 True 表示找到，False 表示超出最大按键次数或无模板。
    """
    if not (anchor_templates and "SUBARU_PAGE" in anchor_templates):
        log_info("  -> LB x 4 (no SUBARU_PAGE template, using fixed count)...")
        for _ in range(4):
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, delay=0.8)
        return False

    template_sp = anchor_templates["SUBARU_PAGE"]
    gray_template = cv2.cvtColor(template_sp, cv2.COLOR_BGR2GRAY)
    for lb_i in range(1, max_presses + 1):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, delay=1.0)
        resized_check, _, _, _, _ = capture_screenshot(hwnd)
        if resized_check is None:
            continue
        gray_screen = cv2.cvtColor(resized_check, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(gray_screen, gray_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        if max_val >= 0.85:
            log_success(f"    Subaru page detected! (LB x {lb_i}, score: {max_val:.3f})")
            return True
    log_warning(f"  Subaru page not found after {max_presses} LB presses")
    return False

# ==========================================

# 二、 视觉模板装载与状态检测

# ==========================================

def load_menu_templates():
    """
    装载主菜单标签模板和导航锚点模板。
    菜单模板用于“反差法”识别当前激活标签，
    锚点模板用于五步导航中每一步的精确校验。
    """
    templates_dir = "templates"
    menu_files = {

        "CAMPAIGN": "campaign.png",
        "CARS": "cars.png",
        "MY HORIZON": "my_horizon.png",
        "ONLINE": "online.png",
        "CREATIVE HUB": "creative_hub.png",
        "STORE": "store.png"

    }
    anchor_files = {

        "COLLECTION_JOURNAL": "Collection_Journal.png",
        "COLLECTION_JOURNAL_ST": "Collection_Journal_ST.png",
        "PLAYING": "playing.png",
        "NAVIGATOR": "Navigator.png",
        "CAR_COLLECTION": "Car_Collection.png",
        "CAR_COLLECTION_PAGE": "Car_Collection_page.png",
        "SUBARU": "Subaru.png",
        "IMPREZA": "Impreza.png",
        "GARAGE": "garage.png",
        "SUBARU_PAGE": "Subaru_page.png",
        "MY_CARS": "my_cars.png"

    }
    loaded_menus = {}
    for state, filename in menu_files.items():
        path = os.path.join(templates_dir, filename)
        if not os.path.exists(path):
            log_warning(f"未找到菜单模板 {state}: {path}")
            continue

        img = cv2.imread(path)
        if img is not None:
            loaded_menus[state] = img

    loaded_anchors = {}
    for state, filename in anchor_files.items():
        path = os.path.join(templates_dir, filename)
        if not os.path.exists(path):
            log_warning(f"未找到锚点模板 {state}: {path}")
            continue

        img = cv2.imread(path)
        if img is not None:
            loaded_anchors[state] = img
            log_success(f"已成功加载锚点 {state}!")

    return loaded_menus, loaded_anchors

def get_current_menu_state(img, loaded_menus):
    """
    检测当前激活的菜单标签页。
    原理：Forza 的未选中标签与模板匹配分高（>= 0.85），
    而当前激活的标签因高亮样式匹配分低（< 0.75）。
    返回状态名称字符串，或 'UNKNOWN'。
    """
    resized = cv2.resize(img, (1600, 900), interpolation=cv2.INTER_AREA)
    menu_scores = {}
    for state, template in loaded_menus.items():
        res = cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        menu_scores[state] = max_val

    high_matches = [state for state, score in menu_scores.items() if score >= 0.85]
    if len(high_matches) < 3:
        return "UNKNOWN"

    # 根据未选中的反差匹配低值判定当前激活状态 (Forza 菜单特点)

    if menu_scores.get("CAMPAIGN", 0) < 0.75 and menu_scores.get("CARS", 0) >= 0.85:
        return "CAMPAIGN"

    if menu_scores.get("CARS", 0) < 0.75 and menu_scores.get("CAMPAIGN", 0) >= 0.85:
        return "CARS"

    for state in ["MY HORIZON", "ONLINE", "CREATIVE HUB", "STORE"]:
        if menu_scores.get(state, 0) < 0.75:
            if state == "CREATIVE HUB":
                return "CREATIVE_HUB"

            return state

    return "UNKNOWN"

# ==========================================

# 三、 截图与导航宏

# ==========================================

def log_step_header(step_num, title):
    safe_print(f"\n{Fore.BLUE}{Style.BRIGHT}==================================================")
    safe_print(f"\n{Fore.BLUE}{Style.BRIGHT}    [导航第 {step_num} 步] {title}")
    safe_print(f"{Fore.BLUE}{Style.BRIGHT}=================================================={Style.RESET_ALL}")

def capture_screenshot(hwnd):
    """
    获取当前游戏窗口的截图并缩放至 1600x900。
    包含窗口最小化恢复、前台焦点检查（节流 10s）、
    GDI 句柄损坏自动重置等防御机制。
    返回: (resized_img, cx, cy, cw, ch) 或 (None, ...)
    """
    global _last_foreground_check
    cw, ch = 2560, 1440
    cx, cy = 0, 0
    if hwnd:
        try:
            # 检查窗口是否被最小化（IsIconic），如果是则恢复它
            if ctypes.windll.user32.IsIconic(hwnd):
                log_warning("游戏窗口已最小化，正在恢复...")
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                time.sleep(2.0)  # 等待窗口恢复

            # 节流前台检查：最多每 10 秒检查一次，避免每帧 1.5s 的焦点抢夺延迟
            now = time.time()
            if now - _last_foreground_check > _FOREGROUND_CHECK_INTERVAL:
                current_fg = ctypes.windll.user32.GetForegroundWindow()
                if current_fg != hwnd:
                    force_foreground(hwnd)

                _last_foreground_check = now

            cx, cy, cw, ch = get_client_rect(hwnd)

            # 防御：窗口坐标异常（最小化时可能返回 0x0 或负坐标）
            if cw <= 0 or ch <= 0 or cx < -10000:
                log_error(f"截图捕获失败: Region has zero or negative size: {{'top': {cy}, 'left': {cx}, 'width': {cw}, 'height': {ch}}}")
                return None, cx, cy, cw, ch

        except Exception as e:
            log_warning(f"获取窗口坐标失败: {e}. 默认使用全屏。")

    try:
        sct = _get_mss()
        monitor = {"top": cy, "left": cx, "width": cw, "height": ch}
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        resized = cv2.resize(img, (1600, 900), interpolation=cv2.INTER_AREA)
        return resized, cx, cy, cw, ch

    except Exception as e:
        log_error(f"截图捕获失败: {e}")
        # GDI 句柄可能已损坏，重置 MSS 单例
        try:
            from utils import get_mss as _reset_check
            import utils
            if hasattr(utils, '_mss_instance') and utils._mss_instance is not None:
                log_warning("正在重置 MSS 截图上下文...")
                try:
                    utils._mss_instance.close()
                except Exception:
                    pass
                utils._mss_instance = None
        except Exception:
            pass
        return None, cx, cy, cw, ch


def capture_raw_screenshot(hwnd):
    """
    获取原始分辨率截图（不缩放），专供 OCR 使用。
    百分比 ROI 在原始图上裁剪，文字保持原始清晰度，
    不受 2560→1600 缩放导致的模糊影响。
    返回: 原始分辨率 BGR 图像，或 None
    """
    if hwnd:
        try:
            cx, cy, cw, ch = get_client_rect(hwnd)
            if cw <= 0 or ch <= 0:
                return None
        except Exception:
            return None
    else:
        return None
    try:
        sct = _get_mss()
        monitor = {"top": cy, "left": cx, "width": cw, "height": ch}
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        return None

def navigate_to_impreza_purchase_screen(hwnd, gamepad, loaded_menus, loaded_anchors):
    """
    五步导航系统：从任意画面（Free Roam）寻路至 Subaru Impreza 购买画面。
    
    导航步骤概述：
    第一步：主菜单 Campaign 页签 → 5 次 D-pad Left 预移动焦点 → 精确定位并选中 Collection Journal
    第二步：Collection Journal 页 → 使用 D-pad Right 移动 1 次 → 选中并进入 Navigator
    第三步：Navigator 子菜单 → 使用 D-pad Down 移动 1 次 → 选中并进入 Car Collection
    第四步：Car Collection 页 → 打开搜索 → 输入 Subaru → 定位品牌
    第五步：Subaru 品牌页 → 选中 Impreza → 进入购买页面
    """
    log_info("正在启动五步导航系统，寻路至 Subaru Impreza 购买画面...")
    search_step = 0
    max_attempts = 50
    attempts = 0
    initial_presses_done = False  # 记录是否已完成 5 次左移
    # ==================================================

    # 第一步：进入 Collection Journal

    # ==================================================

    log_step_header(1, "主 Campaign 页签中 Collection Journal")
    step1_success = False
    while attempts < max_attempts:
        attempts += 1
        resized, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized is None:
            time.sleep(0.5)
            continue

        # 1. 启动守护：若处于 Free Roam 开车画面，自动按 START 打开菜单

        if "PLAYING" in loaded_anchors:
            res_play = cv2.matchTemplate(resized, loaded_anchors["PLAYING"], cv2.TM_CCOEFF_NORMED)
            _, max_val_play, _, _ = cv2.minMaxLoc(res_play)
            if max_val_play >= 0.85:
                log_success(f"检测到处于 Free Roam 驾驶画面 (playing.png score: {max_val_play:.3f})，正在按下 START 打开菜单...")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.5)  # 等待菜单页面加载
                continue

        # 2. 获取当前菜单标签页状态

        menu_state = get_current_menu_state(resized, loaded_menus)
        if menu_state == "CAMPAIGN":
            log_success("已成功定位到 CAMPAIGN 标签页！正在扫描 Collection Journal...")
            # 首次定位到 CAMPAIGN，先执行 5 次 D-pad Left 预移动焦点

            if not initial_presses_done:
                log_info("首次定位到 CAMPAIGN，开始执行 5 次 D-pad Left 预移动焦点...")
                for i in range(5):
                    log_info(f"预移动第 {i+1}/5 次：按下 D-pad Left...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0.8)  # 等待焦点移动稳定

                initial_presses_done = True
                log_success("已完成 5 次 D-pad Left 预移动，继续执行后续扫描与校验逻辑。")
                continue  # 重新截图进行匹配校验

            # 选中态 (ST) vs 中 (Norm)模板差对

            if "COLLECTION_JOURNAL_ST" in loaded_anchors and "COLLECTION_JOURNAL" in loaded_anchors:
                template_st = loaded_anchors["COLLECTION_JOURNAL_ST"]
                template_norm = loaded_anchors["COLLECTION_JOURNAL"]
                # 选中态 (ST)

                res_st = cv2.matchTemplate(resized, template_st, cv2.TM_CCOEFF_NORMED)
                _, max_val_st, _, max_loc_st = cv2.minMaxLoc(res_st)
                # 未选中态 (Norm)

                res_norm = cv2.matchTemplate(resized, template_norm, cv2.TM_CCOEFF_NORMED)
                _, max_val_norm, _, _ = cv2.minMaxLoc(res_norm)
                log_info(f"Collection Journal 差分对比 -> 选中(ST): {max_val_st:.3f} | 未选中(Norm): {max_val_norm:.3f}")
                is_text_valid = False
                is_selected = False
                # 核亮依据中须 (>= 0.85)须中 (说卡中大)

                if max_val_st >= 0.85 and max_val_st >= max_val_norm:
                    # 裁剪卡片进行严格验证

                    template_h, template_w, _ = template_st.shape
                    crop_x, crop_y = max_loc_st[0], max_loc_st[1]
                    card_crop = resized[crop_y : crop_y + template_h, crop_x : crop_x + template_w]
                    # 运行 OCR 严格校对

                    is_text_valid = module_ocr.verify_journal_text(card_crop)
                    if is_text_valid:
                        # 严格绿中边校确保该卡确被亮中！

                        is_selected = module_ocr.has_green_selection_border(card_crop)
                        log_info(f"OCR 严格校验: 通过, 绿色选中边框校验: {'通过' if is_selected else '未通过'}")

                    else:
                        log_info(f"严格: ")

                else:
                    if max_val_st >= 0.80:
                        log_info("Collection Journal 卡片在屏幕中可见且被高亮选中 (匹配度达标)")

                if is_selected:
                    log_success(f"绿色选中边框严格校验通过！Collection Journal (已选中)！按 A 进入...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)  # 进入 Collection Journal 页面
                    step1_success = True
                    break

            # 没有选中，只使用 D-pad Left 移动

            log_info("Collection Journal 未被高亮选中，使用 D-pad Left 移动焦点...")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0.8)  # 等待高亮移动稳定
            search_step += 1

        elif menu_state in ["CARS", "MY HORIZON", "ONLINE", "CREATIVE_HUB", "STORE"]:
            # 不在 CAMPAIGN 标签页，使用 LB 左翻页

            log_info(f"当前在 {menu_state} 页面，按 LB 左翻页...")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, delay=0.8)  # 等待标签页切换稳定

        else:
            log_warning("页面识别失败，按 B 尝试返回上一级...")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)

    if not step1_success:
        log_error("第步 Collection Journal 失败导中止！")
        return False

    # ==================================================

    # 第二步：进入 Navigator

    # ==================================================

    log_step_header(2, " Collection Journal 页面中并 Navigator")
    log_info("已 Collection Journal 页面移以中 Navigator...")
    for i in range(1):
        log_info(f"第 {i+1}/1 次移 D-pad Right...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.8)  # 等待焦点稳定移动

    # 对 Navigator 精确校验！

    log_info("正启 Navigator 模板OCR 绿亮校系...")
    template_nav = loaded_anchors["NAVIGATOR"]
    nav_attempts = 0
    max_nav_attempts = 15
    step2_success = False
    while nav_attempts < max_nav_attempts:
        nav_attempts += 1
        log_info(f"正 Navigator 校 (尝 {nav_attempts}/{max_nav_attempts})...")
        time.sleep(0.5)  # 等待游戏画面稳定渲染
        # 截取帧

        resized_nav, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized_nav is None:
            continue

        # 模板匹配 Navigator (未选中/选中)

        res_nav = cv2.matchTemplate(resized_nav, template_nav, cv2.TM_CCOEFF_NORMED)
        _, max_val_nav, _, max_loc_nav = cv2.minMaxLoc(res_nav)
        log_info(f"Navigator 模板: {max_val_nav:.3f} (: 0.80)")
        is_nav_text_valid = False
        is_nav_selected = False
        if max_val_nav >= 0.80:
            # 裁剪卡片核验

            t_h, t_w, _ = template_nav.shape
            nav_crop_x, nav_crop_y = max_loc_nav[0], max_loc_nav[1]
            nav_crop = resized_nav[nav_crop_y : nav_crop_y + t_h, nav_crop_x : nav_crop_x + t_w]
            # OCR 严格验证

            is_nav_text_valid = module_ocr.verify_navigator_text(nav_crop)
            if is_nav_text_valid:
                # 严格绿亮中边校

                is_nav_selected = module_ocr.has_green_selection_border_padded(resized_nav, nav_crop_x, nav_crop_y, t_w, t_h)
                log_info(f"Navigator 严格: , 绿中边校: {'' if is_nav_selected else ''}")

            else:
                log_info(f"Navigator 严格: ")

        if is_nav_selected:
            step2_success = True
            break

        # 没有选中，提示并继续

        log_warning("Navigator 卡可被亮中面载...")

    if step2_success:
        log_success("Navigator 绿色高亮严格校验通过！按 A 进入 Navigator 子级页面...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    else:
        log_error("Navigator 严格校验失败！导航第 2 步中止！")
        return False
    # ==================================================

    # 第三步：进入 Car Collection

    # ==================================================

    log_step_header(3, " Navigator 子中中并 Car Collection")
    log_info("已 Navigator 子页面正使 D-pad Down 移以中 Car Collection...")
    for i in range(1):
        log_info(f"第 {i+1}/1 次移动 D-pad Down...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.8)  # 等待焦点稳定移动

    # 对 Car Collection 执行模板 + OCR + 绿色高亮校验

    log_info("正在启动 Car Collection 模板 + OCR + 绿色高亮校验系统...")
    template_cc = loaded_anchors["CAR_COLLECTION"]
    cc_attempts = 0
    max_cc_attempts = 15
    step3_success = False
    while cc_attempts < max_cc_attempts:
        cc_attempts += 1
        log_info(f"正在校验 Car Collection (尝试 {cc_attempts}/{max_cc_attempts})...")
        time.sleep(0.5)

        resized_cc, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized_cc is None:
            continue

        # 模板匹配 Car Collection

        res_cc = cv2.matchTemplate(resized_cc, template_cc, cv2.TM_CCOEFF_NORMED)
        _, max_val_cc, _, max_loc_cc = cv2.minMaxLoc(res_cc)
        log_info(f"Car Collection 模板匹配分: {max_val_cc:.3f} (阈值: 0.80)")
        is_cc_text_valid = False
        is_cc_selected = False
        if max_val_cc >= 0.80:
            # 裁剪卡片区域做 OCR 验证

            t_h, t_w, _ = template_cc.shape
            cc_crop_x, cc_crop_y = max_loc_cc[0], max_loc_cc[1]
            cc_crop = resized_cc[cc_crop_y : cc_crop_y + t_h, cc_crop_x : cc_crop_x + t_w]
            is_cc_text_valid = module_ocr.verify_car_collection_text(cc_crop)
            if is_cc_text_valid:
                # 绿色高亮选中边框校验

                is_cc_selected = module_ocr.has_green_selection_border_padded(resized_cc, cc_crop_x, cc_crop_y, t_w, t_h)
                log_info(f"Car Collection OCR 校验: 通过, 绿色选中边框校验: {'通过' if is_cc_selected else '未通过'}")

            else:
                log_info(f"Car Collection OCR 校验: 未通过")

        if is_cc_selected:
            step3_success = True
            break

        log_warning("Car Collection 卡片未被高亮选中...")

        # 每 3 次失败后尝试额外的 D-pad 移动来寻找 Car Collection
        if cc_attempts % 3 == 0:
            if cc_attempts <= 9:
                log_info(f"  -> 尝试额外按 D-pad Down 移动焦点 (第 {cc_attempts // 3} 次补偿)...")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.8)
            else:
                # 可能已经过头了，尝试 D-pad Up 回退
                log_info(f"  -> 尝试按 D-pad Up 回退焦点 (第 {(cc_attempts - 9) // 3} 次回退)...")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.8)

    if step3_success:
        log_success("Car Collection 绿色高亮严格校验通过！按 A 进入 Car Collection 页面...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    else:
        log_error("Car Collection 严格校验失败！导航第 3 步中止！")
        return False
    # ==================================================

    # 第四步：进入 Subaru

    # ==================================================

    log_step_header(4, "校验 Car Collection Page 并定位 Subaru 品牌筛选表")
    log_info("正在启动 Car Collection Page 页面校验...")
    template_cc_page = loaded_anchors["CAR_COLLECTION_PAGE"]
    cc_page_attempts = 0
    max_cc_page_attempts = 15
    cc_page_success = False
    while cc_page_attempts < max_cc_page_attempts:
        cc_page_attempts += 1
        log_info(f"正在校验 Car Collection Page (尝试 {cc_page_attempts}/{max_cc_page_attempts})...")
        time.sleep(0.5)

        resized_cc_page, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized_cc_page is None:
            continue

        # 模板匹配 Car Collection Page

        res_cc_page = cv2.matchTemplate(resized_cc_page, template_cc_page, cv2.TM_CCOEFF_NORMED)
        _, max_val_cc_page, _, _ = cv2.minMaxLoc(res_cc_page)
        log_info(f"Car Collection Page 模板匹配分: {max_val_cc_page:.3f} (阈值: 0.80)")
        if max_val_cc_page >= 0.80:
            cc_page_success = True
            break

        log_warning("Car Collection Page 页面尚未加载...")

    if cc_page_success:
        log_success("Car Collection Page 页面加载校验成功！")

    else:
        log_error("Car Collection Page 页面校验失败！导航第 4 步中止！")
        return False

    # 按 BACK 键打开搜索表

    log_info("按 BACK 键打开搜索表...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK, delay=1.5)  # 等待搜索表弹出稳定
    # D-pad Up 3次

    for i in range(3):
        log_info(f"预移动 D-pad Up ({i+1}/3)...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.8)

    # D-pad Right 3次

    for i in range(3):
        log_info(f"预移动 D-pad Right ({i+1}/3)...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.8)

    # 校验选中 Subaru.png

    log_info("正在进行 Subaru 模板高亮校验...")
    template_subaru = loaded_anchors["SUBARU"]
    subaru_attempts = 0
    max_subaru_attempts = 15
    step4_success = False
    while subaru_attempts < max_subaru_attempts:
        subaru_attempts += 1
        log_info(f"正在校验 Subaru (尝试 {subaru_attempts}/{max_subaru_attempts})...")
        time.sleep(0.5)
        # 帧

        resized_subaru, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized_subaru is None:
            continue

        # 模板匹配 Subaru

        res_subaru = cv2.matchTemplate(resized_subaru, template_subaru, cv2.TM_CCOEFF_NORMED)
        _, max_val_subaru, _, max_loc_subaru = cv2.minMaxLoc(res_subaru)
        log_info(f"Subaru 模板匹配分: {max_val_subaru:.3f} (阈值: 0.80)")
        is_subaru_selected = False
        if max_val_subaru >= 0.80:
            # 选中绿色边框校验

            t_h, t_w, _ = template_subaru.shape
            is_subaru_selected = module_ocr.has_green_selection_border_padded(resized_subaru, max_loc_subaru[0], max_loc_subaru[1], t_w, t_h)
            log_info(f"Subaru 绿色高亮边框校验: {'通过' if is_subaru_selected else '未通过'}")

        if is_subaru_selected:
            step4_success = True
            break

        log_warning("Subaru 未被高亮选中...")

    if step4_success:
        log_success("Subaru 选中校验严格通过！按 A 进入 Subaru 列表...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    else:
        log_error("Subaru 严格高亮校验失败！导航第 4 步（Subaru）中止！")
        return False
    # ==================================================

    # 第五步：进入 Impreza

    # ==================================================

    log_step_header(5, " Subaru 表中并 Impreza")
    log_info("已进入 Subaru 列表，正在使用 D-pad Down 移动以选中 Impreza...")
    for i in range(1):
        log_info(f"第 {i+1}/1 次移 D-pad Down...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.8)  # 等待焦点稳定移动

    # 对 Impreza 精模板OCR 绿亮校！

    log_info("正在启动 Impreza 模板+OCR+绿色高亮校验系统...")
    template_impreza = loaded_anchors["IMPREZA"]
    impreza_attempts = 0
    max_impreza_attempts = 15
    step5_success = False
    while impreza_attempts < max_impreza_attempts:
        impreza_attempts += 1
        log_info(f"正在校验 Impreza (尝试 {impreza_attempts}/{max_impreza_attempts})...")
        time.sleep(0.5)  # 等待游戏画面稳定渲染
        # 帧

        resized_impreza, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized_impreza is None:
            continue

        # 1. 模板匹配 Impreza

        res_impreza = cv2.matchTemplate(resized_impreza, template_impreza, cv2.TM_CCOEFF_NORMED)
        _, max_val_impreza, _, max_loc_impreza = cv2.minMaxLoc(res_impreza)
        log_info(f"Impreza 模板匹配分: {max_val_impreza:.3f} (阈值: 0.80)")
        is_impreza_text_valid = False
        is_impreza_selected = False
        if max_val_impreza >= 0.80:
            # 裁剪卡片核验

            t_h, t_w, _ = template_impreza.shape
            impreza_crop_x, impreza_crop_y = max_loc_impreza[0], max_loc_impreza[1]
            impreza_crop = resized_impreza[impreza_crop_y : impreza_crop_y + t_h, impreza_crop_x : impreza_crop_x + t_w]
            # 2. OCR 严格验证

            is_impreza_text_valid = module_ocr.verify_impreza_text(impreza_crop)
            if is_impreza_text_valid:
                # 3. 严格绿亮中边校

                is_impreza_selected = module_ocr.has_green_selection_border_padded(resized_impreza, impreza_crop_x, impreza_crop_y, t_w, t_h)
                log_info(f"Impreza OCR严格校验: 通过, 绿色选中边框校验: {'通过' if is_impreza_selected else '未通过'}")

            else:
                log_info(f"Impreza OCR严格校验: 未通过")

        if is_impreza_selected:
            step5_success = True
            break

        # 没有选中，提示并继续

        log_warning("Impreza 卡片可见但未被高亮选中，等待画面加载...")

    if step5_success:
        log_success("模板+OCR 匹配且绿色高亮边框严格校验通过！按 A 进入购买/涂装设计画面...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)  # 等待买车列表加载
        log_success("导航第一步至第五步已全部顺利完成！已到达 Subaru Impreza 购买画面")
        return True

    else:
        log_error("Impreza 严格高亮校验失败！启用保底按 A...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
        log_success("导航第一步至第五步保底完成！")
        return True

def is_word_similar(ocr_word, target_keyword):
    """
    增强鲁棒性的模糊词匹配。
    支持子串匹配、编辑距离匹配和符号容错校验。
    """
    w1 = ocr_word.upper()
    w2 = target_keyword.upper()
    # 1. 快速/子串匹配对比（初级）

    if w2 in w1:
        return True

    if w1 in w2 and len(w1) >= 3:
        return True

    # 2. 编辑距离字母符号对比

    clean_w1 = "".join(c for c in w1 if c.isalnum())
    clean_w2 = "".join(c for c in w2 if c.isalnum())
    if not clean_w1 or not clean_w2:
        return False

    if clean_w2 in clean_w1:
        return True

    if clean_w1 in clean_w2 and len(clean_w1) >= 3:
        return True

    # 3. 对轻度 OCR 误 'Cers'  'CARS'使大距离 (距离 <= 1 似度 >= 70%)

    if len(clean_w1) >= 3 and len(clean_w2) >= 3:
        def edit_distance(s1, s2):
            if len(s1) > len(s2):
                s1, s2 = s2, s1

            distances = range(len(s1) + 1)
            for i2, c2 in enumerate(s2):
                distances_ = [i2+1]
                for i1, c1 in enumerate(s1):
                    if c1 == c2:
                        distances_.append(distances[i1])

                    else:
                        distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))

                distances = distances_

            return distances[-1]

        dist = edit_distance(clean_w1, clean_w2)
        max_len = max(len(clean_w1), len(clean_w2))
        similarity = 1.0 - (dist / max_len)
        if similarity >= 0.70:
            return True

    return False

def dynamic_navigate_to_target(template_path, vision_engine, gamepad, hwnd=None, target_keyword="CARS"):
    """
    基于 OpenCV 坐标的反馈式 UI 导航追踪寻路系统。
    含震荡检测和宽松容差。
    通过屏幕像素中坐标差计算并驱动 D-pad 移动，
    锁定并确认目标后按 A 确认进入。
    """
    if hwnd is None:
        hwnd = find_game_window()

    # 确保 Tesseract 路正确置只口次每次循迭代

    module_ocr.setup_tesseract()
    log_info(f"正在启动坐标反馈式 OpenCV 追踪寻路导航系统，模板: {template_path}...")
    max_steps = 60  # 增加步数上限（原 20）以应对慢速 UI 响应
    step = 0
    # 对车卡模板使大容差(150px)松对使精松容差(55px)以确保落

    TOLERANCE = 150 if "target_car" in template_path.lower() else 55
    last_action = None
    locked_successfully = False
    # 记次位置以置 OCR 裁

    last_cx, last_cy = 475, 488  # 车辆常见位置默认值
    # 坐标计算标

    locked_tx = None
    locked_ty = None
    while step < max_steps:
        step += 1
        log_info(f"追踪第 {step}/{max_steps} 步，截取画面中...")
        resized, cx, cy, cw, ch = capture_screenshot(hwnd)
        if resized is None:
            time.sleep(0.5)
            continue

        cursor_pos = vision_engine.find_cursor_position(resized)
        # 核修使纯 pytesseract.image_to_data 空位鲁灰度 + 种 PSM 模式

        if locked_tx is None:
            # menu_roi = resized[200:1200, 50:450]

            img_h, img_w = resized.shape[:2]
            y1 = 200
            y2 = min(img_h, 1200)
            x1 = 50
            x2 = min(img_w, 450)
            menu_roi = resized[y1:y2, x1:x2]
            if menu_roi.size > 0:
                # 保存状态存

                if DEBUG_WRITE_FILES:
                    cv2.imwrite("debug_ocr_raw.png", menu_roi)
                # 3大灰度以保证

                resized_roi = cv2.resize(menu_roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                gray = cv2.cvtColor(resized_roi, cv2.COLOR_BGR2GRAY)
                # 保存状态为保容便们灰度为

                if DEBUG_WRITE_FILES:
                    cv2.imwrite("debug_menu_scan_final.png", gray)
                # 空白 OCR 结果，尝试 psm 3 并 psm 11 或 psm 6 作为强制保障

                ocr_success = False
                for psm in [3, 11, 6]:
                    try:
                        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config=f'--psm {psm}')
                        for i, word in enumerate(data['text']):
                            ocr_word = str(word).strip()
                            if not ocr_word:
                                continue

                            # 使强模词次校

                            if is_word_similar(ocr_word, target_keyword):
                                # 空坐标格式

                                locked_tx = x1 + (data['left'][i] // 3)
                                locked_ty = y1 + (data['top'][i] // 3)
                                log_success(f"非空白 OCR (PSM {psm}) 检测到 '{data['text'][i]}'！屏幕坐标: ({locked_tx}, {locked_ty})")
                                ocr_success = True
                                break

                    except Exception as ocr_err:
                        log_warning(f"  [!] Tesseract PSM {psm} 运行异常: {ocr_err}")

                    if ocr_success:
                        break

                if not ocr_success:
                    log_warning(f"  [!] 左侧文字中不含 '{target_keyword}'，跳过该描述...")

            else:
                log_error("  [!] 裁剪区域左侧大小为 0")

        if cursor_pos is None or locked_tx is None:
            log_warning("  [!] 高亮边框像素占比低于 0.5，跳过...")
            time.sleep(0.5)
            continue

        cx, cy = cursor_pos
        last_cx, last_cy = cx, cy
        # 核修复左侧x < 450强水平偏差 diff_x = 0绝微小水平偏差起 D-pad Left/Right

        # 此们紧容差 30 素以确保精确对不度差误

        current_tolerance = TOLERANCE
        diff_x = locked_tx - cx
        if cx < 450 and locked_tx < 450:
            diff_x = 0
            if "target_car" not in template_path.lower():
                current_tolerance = 30

        diff_y = locked_ty - cy
        log_info(f"  坐标 -> 光标: ({cx}, {cy}) | 目标: ({locked_tx}, {locked_ty}) | 坐标偏差: (diff_x={diff_x}, diff_y={diff_y}) (容差: {current_tolerance}px)")
        # 1. 容差范围内即锁定

        if abs(diff_x) < current_tolerance and abs(diff_y) < current_tolerance:
            safe_print("目标已锁定！跳出追踪循环")
            locked_successfully = True
            break

        # 2. 运行震荡防御

        if diff_x > current_tolerance:
            if last_action == 'DPAD_LEFT':
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡 (当前动作 DPAD_LEFT 与上次动作 DPAD_RIGHT 相反)！强制中断并进入锁定确认！")
                locked_successfully = True
                break

            log_info("  ⚡ [控制决策] 目标在右侧，发送按键: D-pad Right")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0)
            last_action = 'DPAD_RIGHT'

        elif diff_x < -current_tolerance:
            if last_action == 'DPAD_RIGHT':
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡 (当前动作 DPAD_RIGHT 与上次动作 DPAD_LEFT 相反)！强制中断并进入锁定确认！")
                locked_successfully = True
                break

            log_info("  ⚡ [控制决策] 目标在左侧，发送按键: D-pad Left")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0)
            last_action = 'DPAD_LEFT'

        elif diff_y > current_tolerance:
            if last_action == 'DPAD_UP':
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡 (当前动作 DPAD_DOWN 与上次动作 DPAD_UP 相反)！强制中断并进入锁定确认！")
                locked_successfully = True
                break

            log_info("   [] : D-pad Down")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0)
            last_action = 'DPAD_DOWN'

        elif diff_y < -current_tolerance:
            if last_action == 'DPAD_DOWN':
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡 (当前动作 DPAD_UP 与上次动作 DPAD_DOWN 相反)！强制中断并进入锁定确认！")
                locked_successfully = True
                break

            log_info("   [] : D-pad Up")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0)
            last_action = 'DPAD_UP'

            time.sleep(0.5)  # 等待画面渲染稳定

    # --- 3. 校确认段寻车严格 OCR 确认止误触 ---

    if locked_successfully:
        is_car_target = "target_car" in template_path.lower()
        if is_car_target:
            log_info("正在启动位置校验确认程序...")
            time.sleep(0.5)  # 等待帧渲染稳定
            resized_final, cx, cy, cw, ch = capture_screenshot(hwnd)
            if resized_final is not None:
                # 位置命中但位置不使用 last_cx/cy

                cursor_pos = vision_engine.find_cursor_position(resized_final)
                if cursor_pos is not None:
                    last_cx, last_cy = cursor_pos

                # 裁剪 [cy-100:cy+50, cx-150:cx+150] 并读取

                y1, y2 = last_cy - 100, last_cy + 50
                x1, x2 = last_cx - 150, last_cx + 150
                ocr_text = vision_engine.read_text_in_roi(resized_final, x1, y1, x2, y2)
                log_info(f"  [置校] 位置 OCR 读容: '{ocr_text.replace('\n', ' ')}'")
                # 是否包含 (22B IMPREZA)

                ocr_upper = ocr_text.upper()
                if "22B" in ocr_upper or "IMPREZA" in ocr_upper:
                    log_success("  校验确认：读取到 ('22B'/'IMPREZA')，确认无误！")

                else:
                    safe_print("位置不符，终止")
                    raise ValueError("位置不符止")

        # 按 A 确认

        log_info("  -> [确认阶段] 按 A 以确认进入...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)
        return True

    log_error(f"  [!] 导航超时: {template_path}")
    return False

# _press_button 已从 utils.py 导入（import 别名）
def navigate_menu_to_garage(hwnd, gamepad, anchor_templates=None):
    """
    从主菜单导航进入车库的手柄宏。
    
    按键序列：
    1. RB × 2 → 切换到 MY HORIZON 标签
    2. A × 2  → 选择 Return Home → 确认 Yes
    3. 轮询 Campaign 画面等待 Return Home 加载
    4. RB × 2 → 切换到 Cars 标签
    5. Down × 2
    6. A × 1  → 确认选择
    7. Down × 7
    8. A × 1  → 进入车库
    9. LB 循环按直到检测到 Subaru_page.png
    """
    log_info("正在执行主菜单→车库导航宏...")
    # 1. RB × 2 → 切换到 MY HORIZON 标签

    log_info("  -> [1/9] RB × 2 切换到 MY HORIZON 标签...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
    # 2. A × 2 → 选择 Return Home → 确认 Yes

    log_info("  -> [2/9] A × 2 选择 Return Home + 确认 Yes...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)
    # 3. 轮询 Campaign 画面

    log_info("  -> [3/9] 等待 Return Home 加载完毕，轮询 Campaign 画面...")
    max_wait = 30  #  30
    detected = False
    for attempt in range(max_wait):
        time.sleep(1.0)
        resized, _, _, _, _ = capture_screenshot(hwnd)
        if resized is None:
            continue

        try:
            # 大左侧含签栏 + 大 + 项

            h, w = resized.shape[:2]
            roi = resized[0:h//2, 0:w//2]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # 深度检测度

            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            text = pytesseract.image_to_string(thresh).strip().lower()
            # 选项 + 标签栏

            keywords = ["campaign", "drive", "collection", "festival", "settings", "buy", "cars"]
            for kw in keywords:
                if kw in text:
                    log_success(f"    检测到 '{kw}' 已加载！第 {attempt+1} 次")
                    detected = True
                    break

            if detected:
                break

            # 每 3 次打印 OCR 信息

            if (attempt + 1) % 3 == 0:
                short_text = text.replace('\n', ' ')[:80]
                log_info(f"  ... 第 {attempt+1} 次 OCR 读取: '{short_text}'")

        except Exception as e:
            if (attempt + 1) % 5 == 0:
                log_warning(f"  ... 第 {attempt+1} 次 OCR 异常: {e}")

    if not detected:
        log_warning(f"  ⚠️ 超时 {max_wait} 次仍未到达 Campaign，继续...")

    # 4. RB × 2 → 切换到 Cars 标签

    log_info("  -> [4/9] RB × 2 切换到 Cars 标签...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
    # 5. Down × 2

    log_info("  -> [5/9] Down × 2...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
    # 6. A × 1

    log_info("  -> [6/9] A × 1 确认选择...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
    # 7. Down × 7

    log_info("  -> [7/9] Down × 7...")
    for i in range(7):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
    # 8. A × 1

    log_info("  -> [8/9] A × 1 进入车库...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
    # 9. LB scan until Subaru_page.png detected
    log_info("  -> [9/9] LB scan for Subaru page...")
    _scan_for_subaru_page(hwnd, gamepad, anchor_templates)

    log_success(" 主菜单→车库导航宏完成！已到达车库网格界面")


def _wait_for_designs_and_paints(hwnd, max_wait=8):
    """
    轮询检测 'Designs and Paints' 文字，确认已进入车辆详情页。
    返回 True 表示检测到，False 表示超时未检测到。
    """
    for i in range(max_wait):
        time.sleep(1.0)
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is None:
            continue
        h, w = raw_img.shape[:2]
        # "Designs and Paints" 页面标题 (7-25% 高度, 0-25% 宽度)
        top_roi = raw_img[int(h * 0.07):int(h * 0.25), 0:int(w * 0.25)]
        gray = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config='--psm 7').strip().lower()
        if "design" in text and "paint" in text:
            log_success(f"  ✅ 检测到 'Designs and Paints' (OCR: '{text}'，等待 {i+1}s)")
            return True
        if i % 2 == 1:
            log_info(f"  等待 Designs and Paints... #{i+1}: OCR='{text}'")
    log_warning(f"  ⚠️ {max_wait}s 内未检测到 'Designs and Paints'")
    return False


def _wait_for_cars_text(hwnd, max_wait=8):
    """
    轮询检测 'Cars' 文字，确认在菜单页面可以按 A 进入车库。
    返回 True 表示检测到，False 表示超时未检测到。
    """
    for i in range(max_wait):
        time.sleep(1.0)
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is None:
            continue
        h, w = raw_img.shape[:2]
        # "Cars" 大标题位置 (16-26% 高度, 0-20% 宽度)
        top_roi = raw_img[int(h * 0.16):int(h * 0.26), 0:int(w * 0.20)]
        gray = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config='--psm 7').strip().lower()
        if "car" in text:
            log_success(f"  ✅ 检测到 'Cars' (OCR: '{text}'，等待 {i+1}s)")
            return True
        if i % 2 == 1:
            log_info(f"  等待 Cars... #{i+1}: OCR='{text}'")
    log_warning(f"  ⚠️ {max_wait}s 内未检测到 'Cars'")
    return False


def _wait_for_anna_link(hwnd, max_wait=15):
    """
    轮询检测 'ANNA' 或 'LINK' 文字，确认已回到自由漫游画面。
    返回 True 表示检测到，False 表示超时。
    """
    for i in range(max_wait):
        time.sleep(1.0)
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is None:
            continue
        h, w = raw_img.shape[:2]
        # ANNA / LINK 在画面底部 (93-100% 高度, 0-25% 宽度)
        bottom_roi = raw_img[int(h * 0.93):h, 0:int(w * 0.25)]
        gray = cv2.cvtColor(bottom_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config='--psm 7').strip().lower()
        if "anna" in text or "link" in text:
            log_success(f"  ✅ 检测到自由漫游界面 (OCR: '{text}'，等待 {i+1}s)")
            return True
        if i % 2 == 1:
            log_info(f"  等待自由漫游 (ANNA/LINK)... #{i+1}: OCR='{text}'")
    log_warning(f"  ⚠️ {max_wait}s 内未检测到 ANNA/LINK")
    return False


def _navigate_garage_grid(hwnd, gamepad, verify_fn, label="车", template_path="templates/target_car.png", start_col=1, start_row=1):
    """
    车库 3行 × N列 "打字机走位" 网格导航引擎。

    遍历模式（打字机走位 — 逐列从上到下）：
    ┌─ Col1 ─┐  ┌─ Col2 ─┐  ┌─ Col3 ─┐
    │ ① Row1 │  │ ④ Row1 │  │ ⑦ Row1 │
    │ ② Row2 │→│ ⑤ Row2 │→│ ⑧ Row2 │→ ...
    │ ③ Row3 │  │ ⑥ Row3 │  │ ⑨ Row3 │
    └────────┘  └────────┘  └────────┘

    支持 start_col/start_row 从上次位置继续扫描。
    返回: (success, found_col, found_row) — 找到时返回位置。
    """
    log_info(f"正在启动车库网格导航: {label}...")
    if start_col > 1 or start_row > 1:
        log_info(f"  从第 {start_col} 列第 {start_row} 行继续扫描")
    else:
        log_info(f"  遍历模式: 打字机走位（逐列从上到下，复位后右移）")

    TOLERANCE = 150
    MAX_COLUMNS = 200               # 安全上限
    total_excluded = 0              # 累计跳过的车（仅统计）
    found_first_target = False      # 是否已找到第一辆目标车

    # 快进到起始列：按 Right 移动到 start_col
    if start_col > 1:
        log_info(f"  ⏩ 快进: 按 {start_col - 1} 次 Right 跳到第 {start_col} 列...")
        for _ in range(start_col - 1):
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.15)
        time.sleep(0.3)

    for col in range(start_col, start_col + MAX_COLUMNS):
        log_info(f"")
        log_info(f"{'='*40}")
        log_info(f"  📋 正在扫描第 {col} 列...")
        log_info(f"{'='*40}")

        col_has_target = False
        rows_descended = 0  # 本列向下移动了几行（用于精确复位）
        # 首列从 start_row 开始，后续列从第 1 行开始
        first_row = (start_row - 1) if col == start_col else 0
        if first_row > 0:
            log_info(f"  ⏩ 快进: 按 {first_row} 次 Down 跳到第 {first_row + 1} 行...")
            for _ in range(first_row):
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.15)
                rows_descended += 1
            time.sleep(0.3)

        # === 扫描本列的行 ===
        for row in range(first_row, 3):  # row 0, 1, 2
            time.sleep(0.3)
            resized, _, _, _, _ = capture_screenshot(hwnd)
            if resized is None:
                time.sleep(0.5)
                continue

            cursor_pos = module_ocr.find_cursor_position(resized)
            if cursor_pos is None:
                log_warning(f"    [行{row+1}] 无法检测到光标")
                break
            cx, cy = cursor_pos
            log_info(f"    [行{row+1}] 光标位置: ({cx}, {cy})")

            # === 空位检测：检查当前单元格是否为空位（深灰背景，无车辆内容） ===
            # 空位特征：亮度 ≤ 50, 方差 ≤ 5（几乎纯色深灰）
            is_empty_slot = False
            try:
                sample_sz = 40
                sy1 = max(0, cy - sample_sz)
                sy2 = min(resized.shape[0], cy + sample_sz)
                sx1 = max(0, cx - sample_sz)
                sx2 = min(resized.shape[1], cx + sample_sz)
                cell_sample = resized[sy1:sy2, sx1:sx2]
                if cell_sample.size > 0:
                    gray_cell = cv2.cvtColor(cell_sample, cv2.COLOR_BGR2GRAY)
                    cell_mean = float(np.mean(gray_cell))
                    cell_std = float(np.std(gray_cell))
                    if cell_mean <= 50 and cell_std <= 5:
                        is_empty_slot = True
                        log_info(f"    [行{row+1}] 🔲 检测到空位 (亮度={cell_mean:.1f}, 方差={cell_std:.1f})，跳过")
            except Exception as e:
                log_warning(f"Detection check exception: {e}")

            if is_empty_slot:
                if row == 0:
                    # 第 1 行就是空位 → 整列为空，直接跳过本列
                    log_info(f"    [行{row+1}] 第 1 行即为空位，跳过整列")
                    break
                else:
                    # 第 2/3 行是空位 → 网格不规则，品牌区域已扫完
                    log_info(f"    [行{row+1}] 检测到空位，品牌区域已扫完，停止扫描")
                    # 先复位再退出
                    if rows_descended > 0:
                        log_info(f"  ⬆️ 复位: 按 {rows_descended} 次 Up 回到第 1 行...")
                        for i in range(rows_descended):
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                    return False, 0, 0

            # 检查当前单元格是否有目标车辆（只看光标位置附近的匹配）
            target_result = module_ocr.find_target_car(resized, template_path, cursor_pos=(cx, cy))
            if target_result is not None and target_result != "ALL_EXCLUDED":
                tx, ty, match_score = target_result
                if abs(tx - cx) < TOLERANCE and abs(ty - cy) < TOLERANCE:
                    # 目标在当前单元格内！
                    found_first_target = True
                    col_has_target = True
                    log_success(f"    [行{row+1}] 🎯 目标匹配！分数: {match_score:.3f}，正在校验...")
                    if verify_fn(resized, cx, cy):
                        log_success(f"    [行{row+1}] ✅ {label} 校验通过！按 A 进入详情... (列{col}, 行{row+1})")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                        return True, col, row + 1
                    else:
                        total_excluded += 1
                        log_info(f"    [行{row+1}] 跳过此车 (累计跳过: {total_excluded})")
                else:
                    log_info(f"    [行{row+1}] 目标在其他单元格 (tx={tx}, ty={ty})，忽略")
            else:
                # 当前单元格不是目标车辆
                if found_first_target and not is_empty_slot:
                    log_info(f"    [行{row+1}] 已越过 Impreza 区域（当前单元格非目标），停止扫描")
                    # 先复位再退出
                    if rows_descended > 0:
                        for i in range(rows_descended):
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                    return False, 0, 0
                log_info(f"    [行{row+1}] 当前单元格无目标")

            # 如果不是最后一行，检查下方是否有车再决定是否 Down
            if row < 2:
                if module_ocr.has_cell_below(resized, cx, cy):
                    log_info(f"    [行{row+1}] 下方有车，按 D-pad Down...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                    rows_descended += 1
                else:
                    log_info(f"    [行{row+1}] 下方为空位，停止本列向下扫描")
                    break

        # === 步骤 C: 复位 — 按等量 Up 回到第 1 行 ===
        if rows_descended > 0:
            log_info(f"  ⬆️ 复位: 按 {rows_descended} 次 Up 回到第 1 行...")
            for i in range(rows_descended):
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
            time.sleep(0.3)

        # 无目标列不做退出，继续扫描（光标卡住时才退出）

        # === 步骤 D: 在第 1 行按 Right 进入下一列 ===
        log_info(f"  ➡️ 按 Right 移到第 {col + 1} 列...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.5)

    log_info(f"  已扫描 {MAX_COLUMNS} 列，未找到更多 {label}")
    return False, 0, 0

# 模块级变量：记住上次加点选车位置
_last_upgrade_col = 1
_last_upgrade_row = 1

def navigate_to_car_in_garage(hwnd, gamepad, template_path="templates/target_car.png", target_keyword="IMPREZA"):
    """选择有 NEW 标签的 Impreza（用于加点），从上次位置继续扫描"""
    global _last_upgrade_col, _last_upgrade_row

    def _verify(resized, cx, cy):
        has_new = module_ocr.check_new_tag_only(resized, cx, cy)
        if not has_new:
            log_warning("  ⚠️ 该车已加过点，跳过...")
        return has_new

    log_info(f"  📍 上次位置: 列{_last_upgrade_col}, 行{_last_upgrade_row}")
    result, found_col, found_row = _navigate_garage_grid(
        hwnd, gamepad, _verify, label="NEW 车",
        template_path=template_path,
        start_col=_last_upgrade_col, start_row=_last_upgrade_row
    )
    if result:
        _last_upgrade_col = found_col
        _last_upgrade_row = found_row
        log_info(f"  📍 记录位置: 列{found_col}, 行{found_row}")
    return result

def reset_upgrade_position():
    """重置加点选车位置（新一轮买车后调用）"""
    global _last_upgrade_col, _last_upgrade_row
    _last_upgrade_col = 1
    _last_upgrade_row = 1
    log_info("  📍 加点位置已重置为 列1, 行1")

def action_buy_single_car(hwnd, gamepad, car_index):
    """
    进入购买阶段，根据需要购买的车辆数量执行手柄宏循环：
    输入菜单按键 (START) -> D-pad Down 1 次 -> 确认按键 (A) 3 次
    """
    log_info(f"正在执行购买流程：开始购买第 {car_index}/{CARS_TO_PROCESS} 辆车...")
    # 1.  (START)

    log_info("  -> []  (START)...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.0)  # 等待购买菜单弹出并加载
    # 2. 输入 D-pad Down 1次

    log_info("  -> [手柄输入] 按下 D-pad Down 1次...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=1.0)  # 等待光标稳定移动到确认位置
    # 3. 输入 A 键三次

    for i in range(3):
        log_info(f"  -> [手柄输入] 按下 A 键 ({i+1}/3)...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
        if i < 2:
            time.sleep(2.0)  # 确认框与过渡页面之间的过渡延迟

        else:
            time.sleep(5.0)  # 最后一击 A 键后是实际扣款、购买动画和数据同步，需要较长稳定时间

    log_success(f"第 {car_index}/{CARS_TO_PROCESS} 辆车购买指令全部发送成功！")

def _scan_and_delete_cars(hwnd, gamepad, template_path="templates/target_car.png"):
    """
    带状态机的车库扫描删除引擎。
    
    使用打字机走位扫描车库网格，找到可删除的车（无 NEW 标签 + B 级 Impreza）后执行删除。
    删除后根据游戏 UI 机制更新光标状态：
      - Row 3 删除 → 光标退到 Row 2（同列）
      - Row 2 删除 → 光标退到 Row 1（同列）
      - Row 1 删除 → 光标退到上一列 Row 3
    然后恢复扫描位置继续删除下一辆。
    """
    log_info("正在启动带状态机的删车扫描...")

    TOLERANCE = 150
    MAX_COLUMNS = 40
    consecutive_empty_cols = 0
    MAX_EMPTY_COLS = 5
    removed_count = 0
    current_row = 1  # 1-indexed
    current_col = 1

    def _is_removable(resized, cx, cy):
        """检查当前车是否可删除：无 NEW 标签 + 非 S1/S2 级别 + 卡片文字含 1998 SUBARU"""
        has_new = module_ocr.check_new_tag_only(resized, cx, cy)
        if has_new:
            log_warning("  ⚠️ 该车仍有 NEW 标签（未加点），跳过...")
            return False
        if module_ocr.check_is_high_class(resized, cx, cy):
            log_warning("  ⚠️ 该车是 S1/S2 级别（主力车），跳过！")
            return False
        # 卡片 OCR 校验：使用原始分辨率截图读取 "1998 SUBARU"
        try:
            raw_img = capture_raw_screenshot(hwnd)
            if raw_img is None:
                log_warning("  ⚠️ 原始截图失败，安全跳过")
                return False
            rh, rw = raw_img.shape[:2]
            # 将 1600x900 坐标换算到原始分辨率
            scale_x = rw / 1600.0
            scale_y = rh / 900.0
            rcx = int(cx * scale_x)
            rcy = int(cy * scale_y)
            crop_w = int(140 * scale_x)
            crop_h = int(110 * scale_y)
            x1 = max(0, rcx - crop_w)
            x2 = min(rw, rcx + crop_w)
            y1 = max(0, rcy - crop_h)
            y2 = min(rh, rcy + crop_h)
            card_roi = raw_img[y1:y2, x1:x2]
            ch, cw = card_roi.shape[:2]
            text_roi = card_roi[int(ch * 0.12):int(ch * 0.25), :]
            gray = cv2.cvtColor(text_roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            card_text = pytesseract.image_to_string(thresh, config='--psm 6').strip().lower()
            # 容错匹配: OCR 常把 9→8, 1998→1898 等
            has_year = any(y in card_text for y in ["1998", "1898", "1988", "199"])
            has_brand = "subaru" in card_text or "impreza" in card_text
            if has_year and has_brand:
                log_success(f"  ✅ 卡片 OCR 确认: 1998 SUBARU ('{card_text}')")
            else:
                log_warning(f"  ⚠️ 卡片 OCR 未匹配 '1998 subaru'，读取: '{card_text}'，跳过！")
                return False
        except Exception as e:
            log_warning(f"  ⚠️ 卡片 OCR 异常: {e}，安全跳过")
            return False
        return True

    def _check_cell(resized, cx, cy):
        """检查当前单元格是否有目标车辆"""
        target_result = module_ocr.find_target_car(resized, template_path, cursor_pos=(cx, cy))
        if target_result is not None and target_result != "ALL_EXCLUDED":
            tx, ty, score = target_result
            if abs(tx - cx) < TOLERANCE and abs(ty - cy) < TOLERANCE:
                return True, score
        return False, 0

    while current_col <= MAX_COLUMNS:
        log_info(f"\n{'='*40}")
        log_info(f"  📋 [删车] 正在扫描第 {current_col} 列...")
        log_info(f"{'='*40}")

        col_has_target = False

        # 从 current_row 开始扫描（正常情况从 Row 1 开始）
        while current_row <= 3:
            time.sleep(0.3)
            resized, _, _, _, _ = capture_screenshot(hwnd)
            if resized is None:
                time.sleep(0.5)
                continue

            cursor_pos = module_ocr.find_cursor_position(resized)
            if cursor_pos is None:
                log_warning(f"    [行{current_row}] 无法检测到光标")
                break
            cx, cy = cursor_pos
            log_info(f"    [行{current_row}] 光标位置: ({cx}, {cy})")

            # 空位检测
            is_empty = False
            try:
                sz = 40
                sy1, sy2 = max(0, cy - sz), min(resized.shape[0], cy + sz)
                sx1, sx2 = max(0, cx - sz), min(resized.shape[1], cx + sz)
                sample = resized[sy1:sy2, sx1:sx2]
                if sample.size > 0:
                    g = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
                    if float(np.mean(g)) <= 50 and float(np.std(g)) <= 5:
                        is_empty = True
                        log_info(f"    [行{current_row}] 🔲 检测到空位")
            except Exception as e:
                log_warning(f"Detection check exception: {e}")

            if is_empty:
                if current_row == 1:
                    log_info(f"    [行{current_row}] 第 1 行空位，跳过整列")
                    break
                else:
                    log_info(f"    [行{current_row}] 空位，品牌区域已扫完")
                    return removed_count

            # 检查是否有目标车辆
            has_target, score = _check_cell(resized, cx, cy)
            if has_target:
                col_has_target = True
                log_success(f"    [行{current_row}] 🎯 目标匹配！分数: {score:.3f}")

                if _is_removable(resized, cx, cy):
                    log_success(f"    [行{current_row}] ✅ 可删除！按 A 进入详情...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                    action_remove_single_car(hwnd, gamepad, removed_count + 1)
                    removed_count += 1
                    time.sleep(1.0)

                    # === 删除后状态机修正 ===
                    old_row, old_col = current_row, current_col
                    if current_row == 3:
                        current_row = 2
                    elif current_row == 2:
                        current_row = 1
                    elif current_row == 1:
                        current_col -= 1
                        current_row = 3
                    log_info(f"  [状态修正] 删除前: (行{old_row}, 列{old_col}) → 光标退到: (行{current_row}, 列{current_col})")

                    # === 恢复扫描位置 ===
                    if current_row in (1, 2):
                        # 按 Down 前进一格，落在补位的新车上
                        log_info(f"  [恢复] 按 Down 前进到行{current_row + 1}...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                        current_row += 1
                    elif current_row == 3:
                        # 跨列回退：按 Right 进下一列，强制 Up×2 回到第 1 行
                        log_info("  [恢复] 跨列回退：按 Right → Up×2 回到第 1 行...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.5)
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                        current_col += 1
                        current_row = 1

                    # 不要 break，继续从新位置扫描（current_row 已更新）
                    continue
                else:
                    log_info(f"    [行{current_row}] 该车不可删除，继续...")
            else:
                log_info(f"    [行{current_row}] 当前单元格无目标")

            # 向下移动
            if current_row < 3:
                if module_ocr.has_cell_below(resized, cx, cy):
                    log_info(f"    [行{current_row}] 下方有车，按 Down...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                    current_row += 1
                else:
                    log_info(f"    [行{current_row}] 下方为空位")
                    break
            else:
                # 已到第 3 行，本列扫描完毕
                break

        # 复位到第 1 行
        ups_needed = current_row - 1
        if ups_needed > 0:
            log_info(f"  ⬆️ 复位: 按 {ups_needed} 次 Up 回到第 1 行...")
            for _ in range(ups_needed):
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
            current_row = 1

        # 连续空列检测
        if not col_has_target:
            consecutive_empty_cols += 1
            if consecutive_empty_cols >= MAX_EMPTY_COLS:
                log_info(f"  连续 {consecutive_empty_cols} 列无目标，品牌区域扫完。")
                return removed_count
        else:
            consecutive_empty_cols = 0

        # 按 Right 进入下一列
        log_info(f"  ➡️ 按 Right 移到第 {current_col + 1} 列...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.5)
        current_col += 1
        current_row = 1
        time.sleep(0.3)

        # 品牌标签检测: 按 Right 后动态检测当前选中的标签
        # 标签位置会随选中品牌滑动，所以用滑动窗口找暗区再 OCR
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is not None:
            rh, rw = raw_img.shape[:2]
            # 标签栏: y14-18%
            tab_strip = raw_img[int(rh * 0.14):int(rh * 0.18), :]
            tab_gray = cv2.cvtColor(tab_strip, cv2.COLOR_BGR2GRAY)
            # 滑动窗口 (8% 宽) 找最暗区域
            win = int(rw * 0.08)
            min_mean, min_x = 999, 0
            for xi in range(int(rw * 0.05), rw - win, 5):
                m = float(np.mean(tab_gray[:, xi:xi + win]))
                if m < min_mean:
                    min_mean = m; min_x = xi
            # 向两侧扩展暗区
            xs, xe = min_x, min_x + win
            while xs > 0 and float(np.mean(tab_gray[:, max(0, xs-10):xs])) < 120:
                xs -= 10
            while xe < rw and float(np.mean(tab_gray[:, xe:min(rw, xe+10)])) < 120:
                xe += 10
            # OCR 选中标签文字
            sel_roi = tab_strip[:, xs:xe]
            sel_gray = cv2.cvtColor(sel_roi, cv2.COLOR_BGR2GRAY)
            _, sel_thresh = cv2.threshold(sel_gray, 150, 255, cv2.THRESH_BINARY)
            sel_text = pytesseract.image_to_string(sel_thresh, config='--psm 7').strip().lower()
            if "subaru" not in sel_text:
                log_info(f"  🛑 选中标签: '{sel_text}'，已离开 Subaru 区域")
                return removed_count

    log_info(f"  已扫描 {MAX_COLUMNS} 列，删车完成。")
    return removed_count

def navigate_to_car_for_removal(hwnd, gamepad, template_path="templates/target_car.png", target_keyword="IMPREZA"):
    """没 NEW 签为 B 级 Impreza已可移"""
    def _verify(resized, cx, cy):
        has_new = module_ocr.check_new_tag_only(resized, cx, cy)
        if has_new:
            log_warning("  ⚠️ 该车仍有 NEW 标签（未加点），需保留，跳过...")
            return False

        if module_ocr.check_is_high_class(resized, cx, cy):
            log_warning("  ⚠️ 该车是 S1/S2 级别（用户主力车），跳过！")
            return False

        log_success("    NEW 签为 B 级可以移！")
        return True

    result, _, _ = _navigate_garage_grid(hwnd, gamepad, _verify, label="移除车", template_path=template_path)
    return result

def action_remove_single_car(hwnd, gamepad, car_index):
    """
    从车库移除单辆车的手柄宏操作。
    前提：已通过 navigate_to_car_for_removal 选中目标车并按 A 进入了详情页。
    操作序列：
    1. D-pad Down × 4 → 移动到 "Remove Car From Garage"
    2. A             → 选择移除
    3. D-pad Right   → 在确认弹窗中切换到 "确认" 按钮
    4. A             → 确认移除
    """
    log_info(f"🗑️ 正在移除第 {car_index} 辆车...")
    # 1. D-pad Down  4  Remove Car

    for i in range(4):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.4)

    # 2. 按 A 选择移除

    log_info("  -> A Remove Car From Garage...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)
    # 3. 确认弹  D-pad Right 换"确认"

    log_info("  -> D-pad Down：切换到确认按钮...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
    # 4. 按 A 确认移除

    log_info("  -> A：确认移除！")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
    log_success(f"  ✅ 第 {car_index} 辆车已成功从车库移除！")

def navigate_to_main_car(hwnd, gamepad, template_path="templates/target_car.png"):
    """
    选择 S1/S2 级别的主力车（用于上车跑图）。

    不依赖 target_car.png 模板匹配（S2 主力车外观与 B 级不同，模板会失配），
    而是逐格扫描车库网格，直接用 PI 紫色徽章检测找到唯一的 S2 车。
    """
    log_info("正在启动车库网格导航: 主车寻...")
    log_info("  扫描模式: 逐格 PI 颜色检测（不依赖模板匹配）")

    MAX_COLUMNS = 30  # 主力车不会太远
    MAX_CONSECUTIVE_EMPTY = 3  # 连续空列停止

    consecutive_empty = 0
    rows_descended = 0

    for col in range(1, MAX_COLUMNS + 1):
        log_info(f"")
        log_info(f"{'='*40}")
        log_info(f"  📋 正在扫描第 {col} 列...")
        log_info(f"{'='*40}")

        col_found_car = False
        rows_descended = 0

        for row in range(3):  # 最多 3 行
            time.sleep(0.3)
            resized, _, _, _, _ = capture_screenshot(hwnd)
            if resized is None:
                time.sleep(0.5)
                continue

            cursor_pos = module_ocr.find_cursor_position(resized)
            if cursor_pos is None:
                log_warning(f"    [行{row+1}] 无法检测到光标")
                break
            cx, cy = cursor_pos
            log_info(f"    [行{row+1}] 光标位置: ({cx}, {cy})")

            # 空位检测
            is_empty = False
            try:
                sample_sz = 40
                sy1, sy2 = max(0, cy - sample_sz), min(resized.shape[0], cy + sample_sz)
                sx1, sx2 = max(0, cx - sample_sz), min(resized.shape[1], cx + sample_sz)
                cell_sample = resized[sy1:sy2, sx1:sx2]
                if cell_sample.size > 0:
                    gray_cell = cv2.cvtColor(cell_sample, cv2.COLOR_BGR2GRAY)
                    if float(np.mean(gray_cell)) <= 50 and float(np.std(gray_cell)) <= 5:
                        is_empty = True
                        log_info(f"    [行{row+1}] 🔲 空位，跳过")
            except Exception:
                pass

            if is_empty:
                if row == 0:
                    break  # 整列空
                else:
                    break  # 本列剩余行空

            col_found_car = True

            # 直接检测 PI 颜色，不需要模板匹配
            if module_ocr.check_is_high_class(resized, cx, cy):
                # 二次验证：OCR 读取卡片确认 1998 SUBARU
                is_1998_subaru = False
                try:
                    raw_img = capture_raw_screenshot(hwnd)
                    if raw_img is not None:
                        rh, rw = raw_img.shape[:2]
                        scale_x, scale_y = rw / 1600.0, rh / 900.0
                        rcx, rcy = int(cx * scale_x), int(cy * scale_y)
                        crop_w, crop_h = int(140 * scale_x), int(110 * scale_y)
                        x1, x2 = max(0, rcx - crop_w), min(rw, rcx + crop_w)
                        y1, y2 = max(0, rcy - crop_h), min(rh, rcy + crop_h)
                        card_roi = raw_img[y1:y2, x1:x2]
                        ch_r, cw_r = card_roi.shape[:2]
                        text_roi = card_roi[int(ch_r * 0.15):int(ch_r * 0.35), :]
                        gray = cv2.cvtColor(text_roi, cv2.COLOR_BGR2GRAY)
                        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        card_text = pytesseract.image_to_string(thresh, config='--psm 6').strip().lower()
                        has_year = any(y in card_text for y in ["1998", "1898", "1988", "199"])
                        has_brand = "subaru" in card_text or "impreza" in card_text
                        if has_year and has_brand:
                            log_success(f"    [行{row+1}] ✅ 卡片 OCR 确认: 1998 SUBARU ('{card_text}')")
                            is_1998_subaru = True
                        else:
                            log_warning(f"    [行{row+1}] ⚠️ S2 但非 1998 SUBARU (OCR: '{card_text}')，跳过")
                except Exception as e:
                    log_warning(f"    [行{row+1}] ⚠️ 卡片 OCR 异常: {e}")

                if is_1998_subaru:
                    log_success(f"    [行{row+1}] ✅ 找到主力车（S2 + 1998 SUBARU）！按 A 进入详情... (列{col}, 行{row+1})")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                    return True, col, row + 1
                else:
                    log_info(f"    [行{row+1}] S 级但非目标车，跳过...")
            else:
                log_info(f"    [行{row+1}] B 级车，跳过...")

            # 下一行
            if row < 2:
                if module_ocr.has_cell_below(resized, cx, cy):
                    log_info(f"    [行{row+1}] 下方有车，按 D-pad Down...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                    rows_descended += 1
                else:
                    log_info(f"    [行{row+1}] 下方为空位，停止本列向下扫描")
                    break

        # 复位到第 1 行
        if rows_descended > 0:
            log_info(f"  ⬆️ 复位: 按 {rows_descended} 次 Up 回到第 1 行...")
            for _ in range(rows_descended):
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
            time.sleep(0.3)

        # 连续空列检测
        if not col_found_car:
            consecutive_empty += 1
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                log_info(f"  连续 {consecutive_empty} 列无车，停止扫描。")
                break
        else:
            consecutive_empty = 0

        # 右移到下一列
        log_info(f"  ➡️ 按 Right 移到第 {col + 1} 列...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.5)

    log_warning("  ⚠️ 未找到 S1/S2 主力车！")
    return False, 0, 0

def action_get_in_car(hwnd, gamepad):
    """详页 'Get In Car'第个项认中"""
    log_info("  Get In Car...")
    time.sleep(1.0)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    log_success("  ✅ 已上车！")

def action_upgrade_car_skills(hwnd, gamepad, min_points=30):
    """
    全自动车辆熟练度加点手柄宏：
    1. 输入一次 A，等待 10 秒（进入车辆详情/历史）
    2. 输入 B（退回）
    3. 输入 D-pad Down 1 次
    4. 输入 A（进入技能树）
    5. 输入 D-pad Down 7 次
    6. 等待 1 秒
    7. 输入 A（选择超级轮盘）
    8. 输入 D-pad Right 1 次
    9. 输入 A（确认）
    10. 重复多次 (D-pad Up 1 次 + A)
    11. 输入 D-pad Left 1 次
    12. 输入 B × 2（退出技能树）
    确保页面与 usepoints.png 模板画面一致
    """
    log_info("正在执行车辆加点宏...")
    # 宏置延确保UI渲

    def press(button, count=1, delay=0.8):
        for k in range(count):
            gamepad.press_button(button=button)
            gamepad.update()
            time.sleep(0.15)
            gamepad.release_button(button=button)
            gamepad.update()
            time.sleep(delay)

    # 1. B × 1

    log_info("  -> 选好车后等待 2.0 秒以确保稳定...")
    time.sleep(2.0)
    log_info("  -> [1] B × 1...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
    # 2. Up × 1

    log_info("  -> [2] Up × 1...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.8)
    # 3.  A

    log_info("  -> [3]  A ...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.2)
    # 4. 输入 D-pad Down 7次

    log_info("  -> [4] 输入 D-pad Down 7次...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, count=7, delay=0.8)
    # 5.  A

    log_info("  -> [5]  A ...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.2)

    # === 触发条件 2: 扫描 Available Points ===
    time.sleep(1.0)  # 等待 UI 刷新
    available_points = -1
    try:
        # 使用原始分辨率截图，避免缩放导致文字模糊
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is not None:
            h, w = raw_img.shape[:2]
             # Available Points 数字精确位置: 84-88% 高度, 30-45% 宽度
            # 宽度从 28-50% 收窄到 30-45%，避免右侧背景噪点被识别为 "0"
            roi_ap = raw_img[int(h * 0.84):int(h * 0.88), int(w * 0.30):int(w * 0.45)]
            gray_ap = cv2.cvtColor(roi_ap, cv2.COLOR_BGR2GRAY)
            # 使用 OTSU 自适应阈值（固定 150 阈值在单位数时会把噪点识别为 0）
            _, thresh_ap = cv2.threshold(gray_ap, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            upscaled_ap = cv2.resize(thresh_ap, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            text_ap = pytesseract.image_to_string(upscaled_ap, config='--psm 7 -c tessedit_char_whitelist=0123456789').strip()
            numbers = re.findall(r'\d+', text_ap)
            if numbers:
                available_points = int(numbers[0])
            log_info(f"  [Available Points] OCR 读取: '{text_ap}' → 解析: {available_points} ({w}x{h})")
            if available_points >= 0 and available_points < min_points:
                log_warning(f"  ⚠️ Available Points = {available_points} < {min_points}，技能点不足！")
                return available_points
    except Exception as e:
        log_warning(f"  [Available Points] OCR 异常: {e}")

    def _check_cannot_afford(step_name):
        """检测 'Cannot Afford Perk' 弹窗并按 A 关闭"""
        time.sleep(0.5)
        resized, _, _, _, _ = capture_screenshot(hwnd)
        if resized is None:
            return False
        h_img, w_img = resized.shape[:2]
        # 弹窗标题栏: 画面中部偏下 (25-40% 高度, 25-75% 宽度) 黄绿色横幅
        roi = resized[int(h_img*0.25):int(h_img*0.40), int(w_img*0.25):int(w_img*0.75)]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # 荧光黄绿色: H=25-45, S>150, V>200
        yellow_mask = cv2.inRange(hsv, np.array([25, 150, 200]), np.array([45, 255, 255]))
        yellow_px = cv2.countNonZero(yellow_mask)
        if yellow_px > 2000:
            log_warning(f"  ⚠️ [{step_name}] 检测到 'Cannot Afford Perk' 弹窗 (黄色: {yellow_px})，按 A 关闭...")
            press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)
            return True
        return False

    # 6.  A

    log_info("  -> [6]  A ...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.2)
    if _check_cannot_afford("步骤6"):
        log_warning("  ⚠️ 技能点不足，提前结束加点宏")
        return available_points
    # 7. 输入 D-pad Right 1次

    log_info("  -> [7] 输入 D-pad Right 1次...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.8)
    # 8.  A

    log_info("  -> [8]  A ...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.2)
    if _check_cannot_afford("步骤8"):
        log_warning("  ⚠️ 技能点不足，提前结束加点宏")
        return available_points
    # 9. 重复多次 (D-pad Up 1次 + A)

    afford_failed = False
    for j in range(3):
        log_info(f"  -> [9] 循环 {j+1}/3: 输入 D-pad Up 1次...")
        press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.8)
        log_info(f"  -> [9] 循环 {j+1}/3: 按 A 确认...")
        press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.2)
        if _check_cannot_afford(f"循环{j+1}"):
            afford_failed = True
            break

    # 10. 输入 D-pad Left 1次

    log_info("  -> [10] 输入 D-pad Left 1次...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0.8)
    # 11.  A

    log_info("  -> [11]  A ...")
    press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)
    if afford_failed:
        _check_cannot_afford("步骤11")
    log_success("车辆加点宏执行完毕！页面特征应与 usepoints.png 一致")
    return available_points  # 返回剩余点数

def safe_exit_to_menu(hwnd, gamepad, anchor_template="templates/btn_My_car.png"):
    """
    基于 OCR 和 cv2.matchTemplate 的视觉刹车主菜单检测。
    尝试 8 次灰度匹配，若 anchor_template 匹配分 >= 0.70 则判定已回到主菜单。
    """
    log_info("正在执行视觉刹车主程序 safe_exit_to_menu()...")
    # 读传模板转为灰度

    template = cv2.imread(anchor_template, cv2.IMREAD_GRAYSCALE)
    if template is None:
        log_error(f"  [!] 无法加载模板: {anchor_template}，启用保底异常处理")
        raise FileNotFoundError(f"载模板: {anchor_template}")

    max_exit_loops = 8
    for loop_idx in range(1, max_exit_loops + 1):
        log_info(f"  -> [视觉刹车第 {loop_idx}/{max_exit_loops} 次] 截屏寻找锚点...")
        resized_exit, _, _, _, _ = capture_screenshot(hwnd)
        if resized_exit is not None:
            # 屏幕灰度

            gray_screen = cv2.cvtColor(resized_exit, cv2.COLOR_BGR2GRAY)
            # 使用 cv2.matchTemplate 寻找 anchor_template

            res = cv2.matchTemplate(gray_screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            log_info(f"  [视觉刹车] 匹配值 max_val={max_val:.3f}")
            if max_val >= 0.70:
                log_success(f"[视觉刹车] ✅ 视野中发现目标锚点图标 (score={max_val:.3f})，成功退回主菜单！")
                safe_print("✅ 已退回主菜单")
                return True

        # 未达到阈值，打印并按 B 键

        log_warning(f"[视觉刹车] 未看到目标锚点，按下 B 键...")
        # 发送手柄 B 键指令

        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=0)
        # 【非常关键】 time.sleep(2.0) 等待退场和进场动画完全播完

        time.sleep(2.0)

    raise TimeoutError(" 车循 8 次仍主！")

def return_to_garage(hwnd, gamepad, vision_engine=None, anchor_templates=None):
    """
    完整流程 return_to_garage()：
    在 Car Mastery Macro 执行完毕后回到车库。
    1. safe_exit_to_menu() → 逐步按 B 返回主菜单
    2. time.sleep(1.0) → 等待 UI 彻底稳定
    3. Down × 2 → A × 1 → Down × 7 → A × 1 → 进入车库
    4. LB 循环按直到检测到 Subaru_page.png
    """
    log_info("正在执行返回车库流程 return_to_garage()...")
    # 1. safe_exit_to_menu() 逐步按 B 返回

    safe_exit_to_menu(hwnd, gamepad)
    # 2. 等待 UI 彻底稳定

    log_info("  -> 等待主菜单 UI 稳定 1 秒...")
    time.sleep(1.0)
    # 3. Down × 2 → A × 1 → Down × 7 → A × 1 进入车库

    log_info("  -> [导航] Down × 1...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)

    log_info("  -> [导航] A × 1 确认选择...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)

    log_info("  -> [导航] Down × 7...")
    for i in range(7):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)

    log_info("  -> [导航] A × 1 进入车库...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
    # 4. 等待车库加载（OCR 检测画面顶部 "Car Select" 文字）
    log_info("  -> [等待] 轮询检测车库界面加载 (OCR: 'Car Select')...")
    max_poll = 15
    garage_loaded = False
    for poll_i in range(1, max_poll + 1):
        time.sleep(1.0)
        # 使用原始分辨率截图，避免缩放导致文字模糊
        raw_poll = capture_raw_screenshot(hwnd)
        if raw_poll is None:
            continue
        # "Car Select" 在顶栏下方第二行 (约 7%-14% 高度, 左侧 15%)
        h_p, w_p = raw_poll.shape[:2]
        top_roi = raw_poll[int(h_p * 0.07):int(h_p * 0.14), 0:int(w_p * 0.15)]
        gray_top = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
        _, thresh_top = cv2.threshold(gray_top, 200, 255, cv2.THRESH_BINARY)
        text_top = pytesseract.image_to_string(thresh_top, config='--psm 7').strip().lower()
        if "car" in text_top and "selec" in text_top:
            log_success(f"    ✅ 车库已加载！检测到 'Car Select' (OCR: '{text_top}'，等待 {poll_i} 秒)")
            garage_loaded = True
            break
        if poll_i % 3 == 0:
            log_info(f"    等待中... #{poll_i}: OCR 读取 = '{text_top}'")
    if not garage_loaded:
        log_warning(f"  ⚠️ 等待 {max_poll} 秒仍未检测到 'Car Select'，继续...")
    # 5. LB scan until Subaru page detected
    log_info("  -> [5/5] LB scan for Subaru page...")
    _scan_for_subaru_page(hwnd, gamepad, anchor_templates)

    log_success(" return_to_garage() complete!")

def run_master_bot_loop(initial_state=None):
    """
    主控制状态机无限循环。

    状态转换顺序：
      STATE_FARM_POINTS -> STATE_BUY_CARS -> STATE_UPGRADE_CARS -> STATE_TRASH_CARS -> (循环)

    每个状态内部的异常会被捕获并重试，不会击坎整个状态机。
    支持通过 initial_state 参数从任意阶段开始运行。
    用户可随时按 Ctrl+C 安全中止。
    """

    # 1. Find game window
    hwnd = find_game_window()
    if not hwnd:
        log_error("Forza Horizon 6 window not found!")
        sys.exit(1)

    # 2. Init virtual gamepad
    try:
        gamepad = vg.VX360Gamepad()
        log_success("Virtual Xbox 360 controller connected!")
    except Exception as e:
        log_error(f"装载虚拟控制器驱动失败，请检查 ViGEmBus 是否安装正确: {e}")
        sys.exit(1)

    # 3. 装载视觉模板

    menu_templates, anchor_templates = load_menu_templates()
    if not menu_templates and not anchor_templates:
        log_error("无法加载任何视觉模板，退出！")
        sys.exit(1)

    current_state = initial_state if initial_state else STATE_FARM_POINTS
    loop_count = 1
    try:
        while True:
            log_info(f"--- 循环回路 #{loop_count} ---")
            try:
                # ------------------------------------------

                # 1. 买车阶段（需技能点 >= 999）

                # ------------------------------------------

                if current_state == STATE_BUY_CARS:
                    log_state_header(STATE_BUY_CARS, f"购车购: {CARS_TO_PROCESS} 辆")
                    # 导航寻路 Subaru Impreza 购买画面

                    success = navigate_to_impreza_purchase_screen(hwnd, gamepad, menu_templates, anchor_templates)
                    if not success:
                        log_error("五步导航寻路失败！正在尝试从起始位置重试...")
                        time.sleep(2.0)
                        continue

                    log_success("五步导航阶段顺利完成！已到达购买画面")
                    log_info("正在执行宏购车购买步骤...")
                    for i in range(1, CARS_TO_PROCESS + 1):
                        action_buy_single_car(hwnd, gamepad, i)

                    log_success(f"全部 {CARS_TO_PROCESS} 辆车已购买完毕！")
                    # 购买完毕后按 4 次 B 返回主页标签

                    log_info("正在连续按 4 次 B 键返回主页标签...")
                    for i in range(4):
                        log_info(f"  -> [] 按 B ({i+1}/4)...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)

                    log_success("已按 B 键 4 次返回主页标签！")
                    # 转换 -> 加点阶段

                    current_state = STATE_UPGRADE_CARS
                    reset_upgrade_position()  # 新买的车从头开始扫描
                    log_info("流程转换 [STATE_BUY_CARS] ===> [STATE_UPGRADE_CARS]")
                    time.sleep(1.0)

                # ------------------------------------------

                # 2. 加点阶段

                # ------------------------------------------

                elif current_state == STATE_UPGRADE_CARS:
                    log_state_header(STATE_UPGRADE_CARS, "对车库中的 NEW 车逐辆加点...")
                    navigate_menu_to_garage(hwnd, gamepad, anchor_templates=anchor_templates)
                    upgraded_count = 0
                    while True:
                        upgraded_count += 1
                        log_info(f"\n{Fore.YELLOW}[CAR #{upgraded_count}]{Style.RESET_ALL} 正在导航并选中第 {upgraded_count} 辆车...")
                        success = navigate_to_car_in_garage(hwnd, gamepad)

                        # 触发条件 1: 导航返回 False → 无更多 NEW 车，立即进入删车
                        if not success:
                            log_info(f"  导航未找到更多 NEW 车，已加点 {upgraded_count - 1} 辆")
                            # B × 1
                            log_info("  -> B × 1...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                            # A × 1
                            log_info("  -> A × 1...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                            # LB 扫描 Subaru 页面
                            _scan_for_subaru_page(hwnd, gamepad, anchor_templates)
                            # 选中主力车
                            log_info("  -> 正在选中主力车...")
                            navigate_to_main_car(hwnd, gamepad)
                            # 等待确认进入详情页
                            if _wait_for_designs_and_paints(hwnd):
                                log_info("  -> B × 1 (已确认详情页)...")
                                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                            else:
                                log_warning("  ⚠️ 未检测到详情页，跳过 B 按键")
                            # Up × 2
                            log_info("  -> Up × 2...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.5)
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.5)
                            # 等待检测 'Cars' 再按 A 进入车库
                            if _wait_for_cars_text(hwnd):
                                log_info("  -> A × 1 进入车库 (已确认 Cars)...")
                                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                            else:
                                log_warning("  ⚠️ 未检测到 Cars，跳过 A 按键")
                            # LB scan for Subaru page
                            _scan_for_subaru_page(hwnd, gamepad, anchor_templates)
                            break

                        log_success(f"已选中第 {upgraded_count} 辆车并进入详情页，正在执行加点宏...")
                        remaining_points = action_upgrade_car_skills(hwnd, gamepad)

                        # 触发条件 2: Available Points < 30 → 技能点不足，进入删车
                        if remaining_points is not None and 0 <= remaining_points < 30:
                            log_info(f"  技能点不足 ({remaining_points} < 30)，退出技能树回到车库...")
                            # B × 2 退出技能树
                            log_info("  -> B × 2 退出技能树...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                            # Up × 1
                            log_info("  -> Up × 1...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.5)
                            # A × 1
                            log_info("  -> A × 1 进入车库...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                            # LB 扫描 Subaru 页面标签
                            _scan_for_subaru_page(hwnd, gamepad, anchor_templates)
                            # 选中主力车
                            log_info("  -> 正在选中主力车...")
                            navigate_to_main_car(hwnd, gamepad)
                            # A × 1
                            log_info("  -> A × 1 选中主力车...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                            # 等待检测 'Cars' 再按 A 进入车库
                            if _wait_for_cars_text(hwnd):
                                log_info("  -> A × 1 进入车库 (已确认 Cars)...")
                                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                            else:
                                log_warning("  ⚠️ 未检测到 Cars，跳过 A 按键")
                            _scan_for_subaru_page(hwnd, gamepad, anchor_templates)
                            break

                        return_to_garage(hwnd, gamepad, module_ocr, anchor_templates=anchor_templates)

                    log_success(f"加点阶段完成！共加点 {upgraded_count - 1} 辆车")
                    current_state = STATE_TRASH_CARS
                    log_info("流程转换 [STATE_UPGRADE_CARS] ===> [STATE_TRASH_CARS]")
                    time.sleep(1.0)

                # ------------------------------------------

                # 3. 清理车库阶段

                # ------------------------------------------

                elif current_state == STATE_TRASH_CARS:
                    log_state_header(STATE_TRASH_CARS, "移除已加点的 Impreza 车辆...")
                    removed_count = _scan_and_delete_cars(hwnd, gamepad)
                    log_success(f"删车阶段完成！共移除 {removed_count} 辆车")
                    # B × 2 退出车库
                    log_info("  -> B × 2 退出车库...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                    # 等待回到自由漫游画面后再按菜单键
                    if _wait_for_anna_link(hwnd):
                        log_info("  -> 按菜单键 (已确认自由漫游)...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.0)
                    else:
                        log_warning("  ⚠️ 未检测到自由漫游，仍然尝试按菜单键...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.0)

                    current_state = STATE_FARM_POINTS
                    log_info("流程转换 [STATE_TRASH_CARS] ===> [STATE_FARM_POINTS]")
                    time.sleep(1.0)

                # ------------------------------------------

                # 4. 刷图阶段

                # ------------------------------------------

                elif current_state == STATE_FARM_POINTS:
                    log_state_header(STATE_FARM_POINTS, "技能点已耗尽，启动全自动跑图刷点模式")
                    log_warning("状态说明：主控程序正在启动视觉导航与自动跑图模块，进入 EventLab 赚取技能点...")

                    verified_999 = False
                    farm_attempt = 0
                    while not verified_999:
                        farm_attempt += 1
                        try:
                            import module_farm_skills
                            log_info(f"正在启动 module_farm_skills (第 {farm_attempt} 次)...")
                            module_farm_skills.main(gamepad=gamepad)
                            log_success(f"刷图模块已返回！正在验证技能点...")

                        except Exception as e:
                            log_error(f"模块运行中出现错误: {e}")
                            try:
                                module_farm_skills.clear_race_state()
                            except Exception:
                                pass
                            log_warning("尝试等待 5 秒后重新开始刷图阶段...")
                            time.sleep(5.0)
                            continue

                        # === 验证技能点是否到达 999 ===
                        # 技能点只在暂停菜单 CARS 标签页可见，需要先导航过去
                        log_info("  [验证] 正在恢复窗口焦点和截图上下文...")
                        try:
                            import utils as _utils_mod
                            if hasattr(_utils_mod, '_mss_instance') and _utils_mod._mss_instance is not None:
                                try:
                                    _utils_mod._mss_instance.close()
                                except Exception:
                                    pass
                                _utils_mod._mss_instance = None
                        except Exception:
                            pass
                        force_foreground(hwnd)
                        time.sleep(3.0)

                        # farm 模块返回时已在暂停菜单，按 RB 导航到 CARS 标签页
                        log_info("  [验证] 正在导航到 CARS 标签页读取技能点...")
                        detected_points = None
                        cars_found = False

                        # 加载 CARS 标签模板用于检测
                        import module_farm_skills as _farm_mod
                        _farm_menus, _, _ = _farm_mod.load_templates()

                        for rb_press in range(8):  # 最多按 8 次 RB 遍历所有标签
                            resized_v, _, _, _, _ = capture_screenshot(hwnd)
                            if resized_v is None:
                                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
                                continue

                            # 检测当前是否在 CARS 标签（CARS 模板分低 = 当前活跃标签）
                            if _farm_menus:
                                menu_scores = {}
                                for state_name, tpl in _farm_menus.items():
                                    res_m = cv2.matchTemplate(resized_v, tpl, cv2.TM_CCOEFF_NORMED)
                                    _, mv, _, _ = cv2.minMaxLoc(res_m)
                                    menu_scores[state_name] = mv
                                high_count = sum(1 for s in menu_scores.values() if s >= 0.85)

                                if high_count >= 3 and menu_scores.get("CARS", 1.0) < 0.75:
                                    log_success(f"  [验证] 已到达 CARS 标签页！(CARS score={menu_scores.get('CARS', 0):.3f})")
                                    cars_found = True
                                    # 在 CARS 页读取技能点（用原始分辨率图片）
                                    pts = module_ocr.read_skill_points(resized_v)
                                    if pts is not None:
                                        detected_points = pts
                                    break

                            # 还没到 CARS，按 RB 翻页
                            log_info(f"  [验证] RB #{rb_press + 1}: 当前不在 CARS 标签，继续翻页...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)

                        if not cars_found:
                            log_warning("  [验证] 未能导航到 CARS 标签页")

                        # 读完后按 LB 回到 CAMPAIGN 标签（以便后续流程正确）
                        if cars_found:
                            log_info("  [验证] 按 LB 回到 CAMPAIGN 标签...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, delay=0.5)

                        if detected_points is not None:
                            log_info(f"  [验证] OCR 检测到技能点: {detected_points} / {MAX_SKILL_POINTS}")
                            if detected_points >= MAX_SKILL_POINTS:
                                log_success(f"  ✅ 技能点已确认到达 {detected_points} >= {MAX_SKILL_POINTS}！")
                                verified_999 = True
                            else:
                                shortfall = MAX_SKILL_POINTS - detected_points
                                extra_races = max(1, shortfall // 10 + 1)
                                log_warning(f"  ⚠️ 技能点不足！当前 {detected_points}，差 {shortfall} 点")
                                log_info(f"  重新计算：预计还需 {extra_races} 场比赛，即将重新启动刷图...")
                                # 清除旧状态，让 farm 模块重新 OCR 扫描
                                try:
                                    module_farm_skills.clear_race_state()
                                except Exception:
                                    pass
                                time.sleep(2.0)
                        else:
                            log_warning("  ⚠️ OCR 无法读取技能点，假设已达标继续...")
                            verified_999 = True

                    log_success(f"刷图阶段完成！技能点已验证到达 {MAX_SKILL_POINTS}！")

                    # 刷图完成，技能点已满 -> 转入买车阶段（循环）
                    current_state = STATE_BUY_CARS
                    log_info("流程转换 [STATE_FARM_POINTS] ===> [STATE_BUY_CARS] (新一轮开始！)")
                    loop_count += 1
                    time.sleep(2.0)

            except Exception as e:
                # BUG-6 修复：捕获所有状态分支中的未处理异常（TimeoutError, FileNotFoundError 等）
                # 不让单个状态的异常击溃整个状态机
                log_error(f"状态 {current_state} 执行中发生异常: {e}")
                log_warning("尝试等待 5 秒后重试当前状态...")
                time.sleep(5.0)
                continue

    except KeyboardInterrupt:
        print()
        log_warning("==================================================")
        log_warning("     ⛔ 主控大脑被用户手动中止 (KeyboardInterrupt)")
        log_warning("     正在安全释放控制器并退出主程序...")
        log_warning("==================================================")
        sys.exit(0)

