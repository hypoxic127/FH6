# -*- coding: utf-8 -*-
"""
macro/upgrade.py — 车辆加点宏
"""

import time
import cv2
import numpy as np
import vgamepad as vg
from utils import log_info, log_success, log_warning, log_error
from utils import press_button as _press_button
from macro.core import capture_screenshot, capture_raw_screenshot
import pytesseract
import re

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
    # 宏按键延迟设置，确保 UI 渲染稳定

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
            # Available Points 黄色数字精确位置:
            #   y: 85-89% 高度 (底部 Available Points 行)
            #   x: 34-38.5% 宽度 (只截数字，排除右侧星形图标)
            roi_ap = raw_img[int(h * 0.85):int(h * 0.89), int(w * 0.34):int(w * 0.385)]
            # 使用 HSV 黄色通道提取 — 数字是黄色 (H=20-45)，精确隔离数字像素
            hsv_ap = cv2.cvtColor(roi_ap, cv2.COLOR_BGR2HSV)
            yellow_mask = cv2.inRange(hsv_ap, np.array([20, 80, 150]), np.array([45, 255, 255]))
            # 反色：Tesseract 期望黑字白底
            inverted_ap = cv2.bitwise_not(yellow_mask)
            # 加边距 + 4 倍放大，提高小字体识别率
            padded_ap = cv2.copyMakeBorder(inverted_ap, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
            upscaled_ap = cv2.resize(padded_ap, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
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

