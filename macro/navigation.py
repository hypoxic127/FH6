# -*- coding: utf-8 -*-
"""
macro/navigation.py — 菜单导航、视觉刹车、返回车库
"""

import time
import cv2
import numpy as np
import vgamepad as vg
from utils import log_info, log_success, log_warning, log_error, safe_print
from utils import press_button as _press_button
from macro.core import capture_screenshot, capture_raw_screenshot
import pytesseract
import module_ocr


def _scan_for_subaru_page(hwnd, gamepad, max_presses=15):
    """按 LB 翻页直到 OCR 检测到 Subaru 品牌标签。返回 True/False。"""

    def _detect_selected_brand(hwnd):
        """检测品牌标签栏选中的标签文字（委托给 module_ocr 统一实现）"""
        raw_img = capture_raw_screenshot(hwnd)
        return module_ocr.detect_selected_brand_tab(raw_img)

    current_brand = _detect_selected_brand(hwnd)
    if current_brand and "subaru" in current_brand:
        log_success(f"    Subaru page detected on current screen! (OCR: '{current_brand}')")
        return True

    for lb_i in range(1, max_presses + 1):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, delay=1.0)
        current_brand = _detect_selected_brand(hwnd)
        if current_brand and "subaru" in current_brand:
            log_success(f"    Subaru page detected! (LB x {lb_i}, OCR: '{current_brand}')")
            return True
        if lb_i % 3 == 0:
            log_info(f"    LB x {lb_i}: 当前品牌 = '{current_brand}'")

    log_warning(f"  Subaru page not found after {max_presses} LB presses")
    return False


def _ocr_detect_menu_tab(hwnd):
    """OCR 标签栏检测：返回匹配到的菜单关键词数量和文本。"""
    resized, _, _, _, _ = capture_screenshot(hwnd)
    if resized is None:
        return 0, ""
    h, w = resized.shape[:2]
    roi = resized[int(h*0.14):int(h*0.18), int(w*0.09):int(w*0.57)]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    text = pytesseract.image_to_string(thresh).strip().lower()
    keywords = ["campaign", "drive", "collection", "festival", "settings", "buy", "cars", "horizon", "online", "creative", "store"]
    matched = sum(1 for kw in keywords if kw in text)
    return matched, text


def _ocr_wait_for_car_select(hwnd, max_poll=15):
    """OCR 轮询等待车库 'Car Select' 文字出现。"""
    log_info("  -> 轮询检测车库界面加载 (OCR: 'Car Select')...")
    for poll_i in range(1, max_poll + 1):
        time.sleep(1.0)
        raw_poll = capture_raw_screenshot(hwnd)
        if raw_poll is None:
            continue
        h_p, w_p = raw_poll.shape[:2]
        top_roi = raw_poll[int(h_p * 0.09):int(h_p * 0.13), int(w_p * 0.06):int(w_p * 0.16)]
        gray_top = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
        _, thresh_top = cv2.threshold(gray_top, 200, 255, cv2.THRESH_BINARY)
        text_top = pytesseract.image_to_string(thresh_top, config='--psm 7').strip().lower()
        if "car" in text_top and "selec" in text_top:
            log_success(f"    ✅ 车库已加载！(OCR: '{text_top}'，等待 {poll_i} 秒)")
            return True
        if poll_i % 3 == 0:
            log_info(f"    等待中... #{poll_i}: OCR = '{text_top}'")
    log_warning(f"  ⚠️ 等待 {max_poll} 秒仍未检测到 'Car Select'，继续...")
    return False


def navigate_menu_to_garage(hwnd, gamepad):
    """从主菜单导航进入车库：RB×2→A×2→等待→RB×2→Down×2→A→Down×7→A→等待→LB扫Subaru。"""
    log_info("正在执行主菜单→车库导航宏...")

    log_info("  -> [1/10] RB × 2 切换到 MY HORIZON 标签...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)

    log_info("  -> [2/10] A × 2 选择 Return Home + 确认 Yes...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)

    log_info("  -> [3/10] 等待 Return Home 加载完毕...")
    detected = False
    for attempt in range(30):
        time.sleep(1.0)
        matched, text = _ocr_detect_menu_tab(hwnd)
        if matched >= 1:
            log_success(f"    检测到菜单已加载！第 {attempt+1} 次")
            detected = True
            break
        if (attempt + 1) % 3 == 0:
            log_info(f"  ... 第 {attempt+1} 次 OCR: '{text[:80]}'")
    if not detected:
        log_warning("  ⚠️ 超时 30 次仍未到达 Campaign，继续...")

    log_info("  -> [4/10] RB × 2 切换到 Cars 标签...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)

    log_info("  -> [5/10] Down × 2...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)

    log_info("  -> [6/10] A × 1 确认选择...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)

    log_info("  -> [7/10] Down × 7...")
    for _ in range(7):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)

    log_info("  -> [8/10] A × 1 进入车库...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)

    log_info("  -> [9/10] 等待车库加载...")
    _ocr_wait_for_car_select(hwnd)

    log_info("  -> [10/10] LB 翻页定位 Subaru...")
    _scan_for_subaru_page(hwnd, gamepad)

    log_success(" 主菜单→车库导航宏完成！")


def safe_exit_to_menu(hwnd, gamepad):
    """OCR 视觉刹车：循环按 B 退回，OCR 检测标签栏关键词 >= 2 个即确认到达主菜单。"""
    log_info("正在执行视觉刹车 safe_exit_to_menu()...")

    for loop_idx in range(1, 9):
        resized, _, _, _, _ = capture_screenshot(hwnd)
        if resized is not None:
            try:
                h, w = resized.shape[:2]
                roi = resized[int(h*0.14):int(h*0.18), int(w*0.09):int(w*0.57)]
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
                text = pytesseract.image_to_string(thresh).strip().lower()
                menu_keywords = ["campaign", "cars", "horizon", "online", "creative", "store",
                                 "buy", "sell", "garage", "character", "customizable"]
                matched_count = sum(1 for kw in menu_keywords if kw in text)
                if matched_count >= 2:
                    log_success(f"[视觉刹车] ✅ 检测到菜单标签 (匹配 {matched_count} 个)，成功退回主菜单！")
                    safe_print("✅ 已退回主菜单")
                    return True
                log_info(f"  [视觉刹车 {loop_idx}/8] OCR: '{text[:60]}' (匹配 {matched_count} 个)")
            except Exception as e:
                log_warning(f"  [视觉刹车] OCR 异常: {e}")

        log_warning(f"[视觉刹车] 未看到菜单标签栏，按下 B 键...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=0)
        time.sleep(2.0)

    raise TimeoutError("连续 8 次视觉刹车仍未回到主菜单！")


def return_to_garage(hwnd, gamepad):
    """完整返回车库流程：视觉刹车→Down→A→Down×7→A→等待→LB扫Subaru。"""
    log_info("正在执行返回车库流程 return_to_garage()...")

    safe_exit_to_menu(hwnd, gamepad)

    log_info("  -> 等待主菜单 UI 稳定...")
    time.sleep(1.0)

    log_info("  -> Down × 1...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)

    log_info("  -> A × 1 确认选择...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)

    log_info("  -> Down × 7...")
    for _ in range(7):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)

    log_info("  -> A × 1 进入车库...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)

    _ocr_wait_for_car_select(hwnd)

    log_info("  -> LB 翻页定位 Subaru...")
    _scan_for_subaru_page(hwnd, gamepad)

    log_success(" return_to_garage() complete!")
