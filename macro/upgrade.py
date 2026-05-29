# -*- coding: utf-8 -*-
"""
macro/upgrade.py — 车辆加点宏
"""

import time
import cv2
import numpy as np
import vgamepad as vg
from engine.utils import log_info, log_success, log_warning, log_error
from engine.utils import press_button as _press_button
from macro.core import capture_screenshot, capture_raw_screenshot
import pytesseract
import re
from engine.ocr import DEBUG_WRITE_FILES

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
        from collections import Counter
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is not None:
            h, w = raw_img.shape[:2]
            ocr_results = []

            # ROI: 数字区域 (h85-88%, w35-38.5%)
            roi = raw_img[int(h * 0.85):int(h * 0.88), int(w * 0.35):int(w * 0.385)]

            if roi.size > 0:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

                # === 主力管线: 灰度阈值（实测最稳定） ===
                pipelines = []

                # 1. 灰度 threshold 150（test_from_state 测试14验证通过）
                _, t150 = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
                pipelines.append(("gray_t150", t150))

                # 2. 灰度 threshold 160
                _, t160 = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
                pipelines.append(("gray_t160", t160))

                # 3. Otsu 自适应阈值
                _, t_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                pipelines.append(("gray_otsu", t_otsu))

                # 4. HSV 黄色通道（放宽阈值 + 膨胀增粗笔画）
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                yellow_mask = cv2.inRange(hsv,
                                          np.array([15, 40, 100]),
                                          np.array([45, 255, 255]))
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_CLOSE, kernel)
                # 膨胀 1 次增粗抗锯齿导致的细笔画
                yellow_mask = cv2.dilate(yellow_mask, kernel, iterations=1)
                pipelines.append(("hsv_yellow", yellow_mask))

                # 调试输出
                if DEBUG_WRITE_FILES:
                    cv2.imwrite("debug_ap_roi_raw.png", roi)
                    cv2.imwrite("debug_ap_roi_gray_t150.png", t150)
                    cv2.imwrite("debug_ap_roi_yellow_mask.png", yellow_mask)

                # 对每个管线执行 OCR（PSM 7 单行模式）
                for label, binary_img in pipelines:
                    padded = cv2.copyMakeBorder(binary_img, 20, 20, 20, 20,
                                                cv2.BORDER_CONSTANT, value=0)
                    up = cv2.resize(padded, None, fx=3, fy=3,
                                    interpolation=cv2.INTER_CUBIC)
                    up_inv = cv2.bitwise_not(up)
                    text = pytesseract.image_to_string(
                        up_inv,
                        config='--psm 7 -c tessedit_char_whitelist=0123456789'
                    ).strip()
                    nums = re.findall(r'\d+', text)
                    if nums:
                        ocr_results.append(int(nums[0]))

            # 投票（平票取最大值：OCR 更容易漏掉前导数字）
            if ocr_results:
                counter = Counter(ocr_results)
                top_count = counter.most_common(1)[0][1]
                tied = [val for val, cnt in counter.items() if cnt == top_count]
                available_points = max(tied)
                log_info(f"  [Available Points] OCR: {available_points} (读数: {ocr_results}, {w}x{h})")
            else:
                log_warning("  [Available Points] OCR 未识别到数字！")

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
        # 弹窗区域: h27-83%, w26-82%
        roi = resized[int(h_img*0.27):int(h_img*0.83), int(w_img*0.26):int(w_img*0.82)]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config='--psm 6').strip().lower()
        if "cannot" in text and "afford" in text:
            log_warning(f"  ⚠️ [{step_name}] 检测到 'Cannot Afford Perk' 弹窗 (OCR: '{text[:50]}')，按 A 关闭...")
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

