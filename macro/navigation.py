# -*- coding: utf-8 -*-
"""
macro/navigation.py — 菜单导航、视觉刹车、返回车库
"""

import time
import os
import cv2
import numpy as np
import vgamepad as vg
from utils import log_info, log_success, log_warning, log_error, safe_print
from utils import press_button as _press_button
from macro.core import capture_screenshot, capture_raw_screenshot
import pytesseract
import module_ocr

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

