# -*- coding: utf-8 -*-
"""
macro/purchase.py — 5步购买导航 + 购买宏（纯 OCR 版）
"""

import time

import cv2
import pytesseract
import vgamepad as vg

import engine.ocr as module_ocr
from engine.ocr import DEBUG_WRITE_FILES
from engine.utils import find_game_window, log_error, log_info, log_success, log_warning, safe_print
from engine.utils import press_button as _press_button
from macro.core import (
    CARS_TO_PROCESS,
    capture_screenshot,
    log_step_header,
)

# ==========================================
# OCR 辅助函数
# ==========================================


def _ocr_scan_keywords(hwnd, keywords, roi_pct=None, psm=6):
    """
    OCR 扫描画面中是否包含目标关键词。

    参数:
        hwnd: 窗口句柄
        keywords: 关键词列表 (小写)，任一匹配即成功
        roi_pct: (y1%, y2%, x1%, x2%) 裁剪比例，None 表示全画面
        psm: Tesseract PSM 模式

    返回:
        (matched: bool, text: str, word_boxes: list)
        word_boxes: 匹配到的词的 [(x, y, w, h), ...] 坐标列表（基于 resized 坐标系）
    """
    resized, _, _, _, _ = capture_screenshot(hwnd)
    if resized is None:
        return False, "", []

    h, w = resized.shape[:2]
    if roi_pct:
        y1, y2, x1, x2 = int(h * roi_pct[0]), int(h * roi_pct[1]), int(w * roi_pct[2]), int(w * roi_pct[3])
        roi = resized[y1:y2, x1:x2]
    else:
        y1, x1 = 0, 0
        roi = resized

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    upscaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    try:
        data = pytesseract.image_to_data(upscaled, output_type=pytesseract.Output.DICT, config=f"--psm {psm}")
    except Exception as e:
        log_warning(f"OCR image_to_data 异常: {e}")
        return False, "", []

    full_text = " ".join(str(w).strip() for w in data["text"] if str(w).strip()).lower()
    matched_boxes = []

    for i, word in enumerate(data["text"]):
        w_str = str(word).strip().lower()
        if not w_str:
            continue
        for kw in keywords:
            if kw in w_str or is_word_similar(w_str, kw):
                # 坐标从 2x 放大图换算回 resized 坐标系
                bx = x1 + data["left"][i] // 2
                by = y1 + data["top"][i] // 2
                bw = data["width"][i] // 2
                bh = data["height"][i] // 2
                matched_boxes.append((bx, by, bw, bh))
                break

    return len(matched_boxes) > 0, full_text, matched_boxes


def _check_green_at_boxes(hwnd, boxes, pad=40):
    """检测给定坐标 box 周围是否有绿色选中边框。

    OCR 返回的 box 是文字的精确矩形，通常远小于卡片。
    为覆盖卡片边缘的绿色边框，将小 box 扩展为最小 200x150 的卡片级区域。
    """
    resized, _, _, _, _ = capture_screenshot(hwnd)
    if resized is None or not boxes:
        return False

    MIN_W, MIN_H = 200, 150  # 卡片最小检测区域
    for bx, by, bw, bh in boxes:
        # 将小文字 box 扩展到卡片级尺寸（以文字中心为基准）
        if bw < MIN_W:
            cx = bx + bw // 2
            bx = cx - MIN_W // 2
            bw = MIN_W
        if bh < MIN_H:
            cy = by + bh // 2
            by = cy - MIN_H // 2
            bh = MIN_H
        # 确保坐标不越界
        bx = max(0, bx)
        by = max(0, by)
        if module_ocr.has_green_selection_border_padded(resized, bx, by, bw, bh, pad=pad):
            return True
    return False


def _detect_playing(hwnd):
    """使用 StateDetector 单例检测是否在自由漫游驾驶画面。"""
    from module_state_detect import get_detector

    resized, _, _, _, _ = capture_screenshot(hwnd)
    if resized is None:
        return False
    state = get_detector().detect(resized, mode="racing")
    return state == "PLAYING"


def _detect_campaign(hwnd):
    """使用 StateDetector 单例检测是否在 CAMPAIGN 标签页。"""
    from module_state_detect import get_detector

    resized, _, _, _, _ = capture_screenshot(hwnd)
    if resized is None:
        return False
    state = get_detector().detect(resized, mode="menu")
    return state == "CAMPAIGN"


# ==========================================
# 五步导航系统（纯 OCR 版）
# ==========================================


def navigate_to_impreza_purchase_screen(hwnd, gamepad):
    """
    五步导航系统：从任意画面（Free Roam）寻路至 Subaru Impreza 购买画面。
    全部使用 OCR + 绿框检测，无模板匹配。

    导航步骤：
    第一步：主菜单 Campaign 页签 → 定位并选中 Collection Journal
    第二步：Collection Journal 页 → 选中 Navigator
    第三步：Navigator 子菜单 → 选中 Car Collection
    第四步：Car Collection 页 → 打开搜索 → 定位 Subaru
    第五步：Subaru 品牌页 → 选中 Impreza → 进入购买页面
    """
    log_info("正在启动五步导航系统（纯 OCR 版），寻路至 Subaru Impreza 购买画面...")

    # ==================================================
    # 第一步：进入 Collection Journal
    # ==================================================

    log_step_header(1, "主 Campaign 页签中 Collection Journal")
    step1_success = False
    initial_presses_done = False
    attempts = 0
    max_attempts = 50

    while attempts < max_attempts:
        attempts += 1
        time.sleep(0.5)

        # 守护：检测是否在 Free Roam 驾驶画面
        if _detect_playing(hwnd):
            log_success("检测到处于 Free Roam 驾驶画面，正在按下 START 打开菜单...")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.5)
            continue

        # 检测是否在 CAMPAIGN 标签页
        if _detect_campaign(hwnd):
            log_success("已成功定位到 CAMPAIGN 标签页！正在扫描 Collection Journal...")

            # 首次到达 CAMPAIGN，执行 1 次 D-pad Left 预移动焦点
            if not initial_presses_done:
                log_info("首次定位到 CAMPAIGN，执行 1 次 D-pad Left 预移动焦点...")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0.8)
                initial_presses_done = True
                log_success("已完成 D-pad Left 预移动。")
                continue

            # OCR 扫描 "Collection Journal" + 绿框检测
            matched, text, boxes = _ocr_scan_keywords(hwnd, ["collection", "journal"], roi_pct=(0.30, 0.85, 0.05, 0.95))
            if matched and boxes:
                log_info("OCR 检测到 Collection Journal 文字，检查绿框选中...")
                if _check_green_at_boxes(hwnd, boxes, pad=50):
                    log_success("Collection Journal 绿色选中边框校验通过！按 A 进入...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
                    step1_success = True
                    break
                else:
                    log_info("Collection Journal 可见但未选中，按 D-pad Left 移动焦点...")
            else:
                log_info(f"未检测到 Collection Journal (OCR: '{text[:60]}')，按 D-pad Left...")

            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0.8)

        else:
            # 不在 CAMPAIGN，按 LB 左翻页 或 B 返回
            resized, _, _, _, _ = capture_screenshot(hwnd)
            if resized is not None:
                # 简单 OCR 检测标签栏是否有菜单关键词
                h, w = resized.shape[:2]
                tab_roi = resized[int(h * 0.14) : int(h * 0.18), int(w * 0.09) : int(w * 0.57)]
                tab_gray = cv2.cvtColor(tab_roi, cv2.COLOR_BGR2GRAY)
                _, tab_thresh = cv2.threshold(tab_gray, 150, 255, cv2.THRESH_BINARY)
                tab_text = pytesseract.image_to_string(tab_thresh).strip().lower()
                menu_kws = ["cars", "horizon", "online", "creative", "store"]
                if any(kw in tab_text for kw in menu_kws):
                    log_info(f"当前在其他菜单标签 (OCR: '{tab_text[:40]}')，按 LB 左翻页...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, delay=0.8)
                    continue

            log_warning("页面识别失败，按 B 尝试返回上一级...")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)

    if not step1_success:
        log_error("第一步 Collection Journal 导航失败，中止！")
        return False

    # ==================================================
    # 第二步：进入 Navigator
    # ==================================================

    log_step_header(2, "Collection Journal 页面中选中 Navigator")
    log_info("已进入 Collection Journal 页面，按 D-pad Right 移动到 Navigator...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.8)

    step2_success = False
    for nav_attempt in range(1, 16):
        log_info(f"正在校验 Navigator (尝试 {nav_attempt}/15)...")
        time.sleep(0.5)

        # 使用固定的 Navigator 卡片 ROI 检测绿框 (h:12%-83%, w:50%-80%)
        resized, _, _, _, _ = capture_screenshot(hwnd)
        if resized is None:
            continue
        rh, rw = resized.shape[:2]
        nav_x, nav_y = int(rw * 0.50), int(rh * 0.12)
        nav_w, nav_h = int(rw * 0.30), int(rh * 0.71)
        if module_ocr.has_green_selection_border_padded(resized, nav_x, nav_y, nav_w, nav_h, pad=10):
            log_success("Navigator 绿色选中边框校验通过！")
            step2_success = True
            break
        else:
            log_info(f"Navigator 卡片区域未检测到绿框 (尝试 {nav_attempt}/15)，按 D-pad Right 移动焦点...")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.8)

    if step2_success:
        log_success("按 A 进入 Navigator 子级页面...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    else:
        log_error("Navigator 校验失败！导航第 2 步中止！")
        return False

    # ==================================================
    # 第三步：进入 Car Collection
    # ==================================================

    log_step_header(3, "Navigator 子菜单中选中 Car Collection")
    log_info("已进入 Navigator 子页面，按 D-pad Down 移动到 Car Collection...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.8)

    step3_success = False
    for cc_attempt in range(1, 16):
        log_info(f"正在校验 Car Collection (尝试 {cc_attempt}/15)...")
        time.sleep(0.5)

        matched, text, boxes = _ocr_scan_keywords(hwnd, ["collection"], roi_pct=(0.30, 0.85, 0.05, 0.95))
        if matched and boxes:
            if _check_green_at_boxes(hwnd, boxes, pad=50):
                log_success("Car Collection 绿色选中边框校验通过！")
                step3_success = True
                break
            else:
                log_info("Car Collection 可见但未选中...")
        else:
            log_warning(f"Car Collection OCR 未匹配 (text: '{text[:40]}')")

        # 每 3 次失败后尝试额外 D-pad 移动
        if cc_attempt % 3 == 0:
            if cc_attempt <= 9:
                log_info("  -> 尝试额外按 D-pad Down 移动焦点...")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.8)
            else:
                log_info("  -> 尝试按 D-pad Up 回退焦点...")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.8)

    if step3_success:
        log_success("按 A 进入 Car Collection 页面...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    else:
        log_error("Car Collection 校验失败！导航第 3 步中止！")
        return False

    # ==================================================
    # 第四步：Car Collection 页面 → 定位 Subaru
    # ==================================================

    log_step_header(4, "校验 Car Collection Page 并定位 Subaru 品牌")

    # 4a: 等待页面加载 — OCR 检测标题含 "car collection"
    log_info("正在等待 Car Collection Page 加载...")
    cc_page_success = False
    for page_attempt in range(1, 16):
        time.sleep(0.5)
        matched, text, _ = _ocr_scan_keywords(hwnd, ["car", "collection"], roi_pct=(0.08, 0.15, 0.03, 0.25))
        if matched:
            cc_page_success = True
            log_success(f"Car Collection Page 页面加载确认！(OCR: '{text[:40]}')")
            break
        log_info(f"等待页面加载 ({page_attempt}/15)...")

    if not cc_page_success:
        log_error("Car Collection Page 页面校验失败！导航第 4 步中止！")
        return False

    # 4b: 按 BACK 键打开搜索表
    log_info("按 BACK 键打开搜索表...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK, delay=1.5)

    # D-pad Up 3次 + Right 3次 预移动
    for i in range(3):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.8)
    for i in range(3):
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.8)

    # 4c: OCR 校验 Subaru 选中（精确 ROI: h:68%-74%, w:68%-87%，黑底白字）
    log_info("正在进行 Subaru OCR + 绿框校验...")
    step4_success = False
    for sub_attempt in range(1, 16):
        log_info(f"正在校验 Subaru (尝试 {sub_attempt}/15)...")
        time.sleep(0.5)

        resized, _, _, _, _ = capture_screenshot(hwnd)
        if resized is None:
            continue
        rh, rw = resized.shape[:2]
        # 精确 Subaru 文字 ROI，内缩 8px 去掉绿色选中边框干扰
        pad_in = 8
        sub_roi = resized[
            int(rh * 0.68) + pad_in : int(rh * 0.74) - pad_in, int(rw * 0.68) + pad_in : int(rw * 0.87) - pad_in
        ]
        sub_gray = cv2.cvtColor(sub_roi, cv2.COLOR_BGR2GRAY)
        _, sub_thresh = cv2.threshold(sub_gray, 150, 255, cv2.THRESH_BINARY)
        sub_upscaled = cv2.resize(sub_thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        sub_text = pytesseract.image_to_string(sub_upscaled, config="--psm 7").strip().lower()
        log_info(f"  Subaru ROI OCR: '{sub_text}'")

        if "subaru" in sub_text or "subar" in sub_text:
            # 使用固定 ROI 检测绿框
            sub_x, sub_y = int(rw * 0.68), int(rh * 0.68)
            sub_w, sub_h = int(rw * 0.19), int(rh * 0.06)
            if module_ocr.has_green_selection_border_padded(resized, sub_x, sub_y, sub_w, sub_h, pad=30):
                log_success("Subaru 绿色选中边框校验通过！")
                step4_success = True
                break
            else:
                log_info("Subaru 可见但未选中...")
        else:
            log_warning(f"Subaru OCR 未匹配 (text: '{sub_text}')")

    if step4_success:
        log_success("按 A 进入 Subaru 列表...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    else:
        log_error("Subaru 校验失败！导航第 4 步（Subaru）中止！")
        return False

    # ==================================================
    # 第五步：进入 Impreza
    # ==================================================

    log_step_header(5, "Subaru 列表中选中 Impreza")
    log_info("已进入 Subaru 列表，按 D-pad Down 移动到 Impreza...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.8)

    step5_success = False
    for imp_attempt in range(1, 16):
        log_info(f"正在校验 Impreza (尝试 {imp_attempt}/15)...")
        time.sleep(0.5)

        matched, text, boxes = _ocr_scan_keywords(hwnd, ["impreza", "imprez"], roi_pct=(0.20, 0.90, 0.10, 0.90))
        if matched and boxes:
            if _check_green_at_boxes(hwnd, boxes, pad=50):
                log_success("Impreza 绿色选中边框校验通过！")
                step5_success = True
                break
            else:
                log_info("Impreza 可见但未选中...")
        else:
            log_warning(f"Impreza OCR 未匹配 (text: '{text[:40]}')")

    if step5_success:
        log_success("按 A 进入购买/涂装设计画面...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
        log_success("导航第一步至第五步已全部顺利完成！已到达 Subaru Impreza 购买画面")
        return True
    else:
        log_error("Impreza 校验失败！启用保底按 A...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
        log_success("导航第一步至第五步保底完成！")
        return True


# ==========================================
# 工具函数
# ==========================================


def is_word_similar(ocr_word, target_keyword):
    """增强鲁棒性的模糊词匹配：子串匹配 + 编辑距离 + 符号容错。"""
    w1 = ocr_word.upper()
    w2 = target_keyword.upper()

    if w2 in w1:
        return True
    if w1 in w2 and len(w1) >= 3:
        return True

    clean_w1 = "".join(c for c in w1 if c.isalnum())
    clean_w2 = "".join(c for c in w2 if c.isalnum())
    if not clean_w1 or not clean_w2:
        return False
    if clean_w2 in clean_w1:
        return True
    if clean_w1 in clean_w2 and len(clean_w1) >= 3:
        return True

    if len(clean_w1) >= 3 and len(clean_w2) >= 3:

        def edit_distance(s1, s2):
            if len(s1) > len(s2):
                s1, s2 = s2, s1
            distances = range(len(s1) + 1)
            for i2, c2 in enumerate(s2):
                distances_ = [i2 + 1]
                for i1, c1 in enumerate(s1):
                    if c1 == c2:
                        distances_.append(distances[i1])
                    else:
                        distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
                distances = distances_
            return distances[-1]

        dist = edit_distance(clean_w1, clean_w2)
        max_len = max(len(clean_w1), len(clean_w2))
        if 1.0 - (dist / max_len) >= 0.70:
            return True

    return False


def dynamic_navigate_to_target(template_path, vision_engine, gamepad, hwnd=None, target_keyword="CARS"):
    """
    基于 OCR 坐标的反馈式 UI 导航追踪寻路系统。
    含震荡检测和宽松容差。
    """
    if hwnd is None:
        hwnd = find_game_window()

    module_ocr.setup_tesseract()
    log_info(f"正在启动坐标反馈式 OCR 追踪寻路导航系统，目标: {target_keyword}...")
    max_steps = 60
    step = 0
    TOLERANCE = 150 if "target_car" in template_path.lower() else 55
    last_action = None
    locked_successfully = False
    last_cx, last_cy = 475, 488
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

        if locked_tx is None:
            img_h, img_w = resized.shape[:2]
            y1, y2 = 200, min(img_h, 1200)
            x1, x2 = 50, min(img_w, 450)
            menu_roi = resized[y1:y2, x1:x2]
            if menu_roi.size > 0:
                if DEBUG_WRITE_FILES:
                    cv2.imwrite("debug_ocr_raw.png", menu_roi)

                resized_roi = cv2.resize(menu_roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                gray = cv2.cvtColor(resized_roi, cv2.COLOR_BGR2GRAY)

                if DEBUG_WRITE_FILES:
                    cv2.imwrite("debug_menu_scan_final.png", gray)

                ocr_success = False
                for psm in [3, 11, 6]:
                    try:
                        data = pytesseract.image_to_data(
                            gray, output_type=pytesseract.Output.DICT, config=f"--psm {psm}"
                        )
                        for i, word in enumerate(data["text"]):
                            ocr_word = str(word).strip()
                            if not ocr_word:
                                continue
                            if is_word_similar(ocr_word, target_keyword):
                                locked_tx = x1 + (data["left"][i] // 3)
                                locked_ty = y1 + (data["top"][i] // 3)
                                log_success(
                                    f"OCR (PSM {psm}) 检测到 '{data['text'][i]}'！屏幕坐标: ({locked_tx}, {locked_ty})"
                                )
                                ocr_success = True
                                break
                    except Exception as ocr_err:
                        log_warning(f"  [!] Tesseract PSM {psm} 运行异常: {ocr_err}")
                    if ocr_success:
                        break

                if not ocr_success:
                    log_warning(f"  [!] 左侧文字中不含 '{target_keyword}'，跳过...")
            else:
                log_error("  [!] 裁剪区域左侧大小为 0")

        if cursor_pos is None or locked_tx is None:
            log_warning("  [!] 高亮边框像素占比低于 0.5，跳过...")
            time.sleep(0.5)
            continue

        cx, cy = cursor_pos
        last_cx, last_cy = cx, cy

        current_tolerance = TOLERANCE
        diff_x = locked_tx - cx
        if cx < 450 and locked_tx < 450:
            diff_x = 0
            if "target_car" not in template_path.lower():
                current_tolerance = 30

        diff_y = locked_ty - cy
        log_info(
            f"  坐标 -> 光标: ({cx}, {cy}) | 目标: ({locked_tx}, {locked_ty}) | 偏差: (dx={diff_x}, dy={diff_y}) (容差: {current_tolerance}px)"
        )

        if abs(diff_x) < current_tolerance and abs(diff_y) < current_tolerance:
            safe_print("目标已锁定！跳出追踪循环")
            locked_successfully = True
            break

        if diff_x > current_tolerance:
            if last_action == "DPAD_LEFT":
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡！强制锁定！")
                locked_successfully = True
                break
            log_info("  ⚡ 目标在右侧，D-pad Right")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0)
            last_action = "DPAD_RIGHT"
        elif diff_x < -current_tolerance:
            if last_action == "DPAD_RIGHT":
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡！强制锁定！")
                locked_successfully = True
                break
            log_info("  ⚡ 目标在左侧，D-pad Left")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, delay=0)
            last_action = "DPAD_LEFT"
        elif diff_y > current_tolerance:
            if last_action == "DPAD_UP":
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡！强制锁定！")
                locked_successfully = True
                break
            log_info("  ⚡ 目标在下方，D-pad Down")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0)
            last_action = "DPAD_DOWN"
        elif diff_y < -current_tolerance:
            if last_action == "DPAD_DOWN":
                log_warning("  ⚠️ [死循环防御] 检测到控制震荡！强制锁定！")
                locked_successfully = True
                break
            log_info("  ⚡ 目标在上方，D-pad Up")
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0)
            last_action = "DPAD_UP"

        time.sleep(0.5)

    # 锁定确认阶段
    if locked_successfully:
        is_car_target = "target_car" in template_path.lower()
        if is_car_target:
            log_info("正在启动位置校验确认程序...")
            time.sleep(0.5)
            resized_final, cx, cy, cw, ch = capture_screenshot(hwnd)
            if resized_final is not None:
                cursor_pos = vision_engine.find_cursor_position(resized_final)
                if cursor_pos is not None:
                    last_cx, last_cy = cursor_pos

                y1, y2 = last_cy - 100, last_cy + 50
                x1, x2 = last_cx - 150, last_cx + 150
                ocr_text = vision_engine.read_text_in_roi(resized_final, x1, y1, x2, y2)
                log_info(f"  [位置校验] OCR 读取内容: '{ocr_text.replace(chr(10), ' ')}'")

                ocr_upper = ocr_text.upper()
                if "22B" in ocr_upper or "IMPREZA" in ocr_upper:
                    log_success("  校验确认：读取到 ('22B'/'IMPREZA')，确认无误！")
                else:
                    safe_print("位置不符，终止")
                    raise ValueError("位置不符，终止导航")

        log_info("  -> [确认阶段] 按 A 以确认进入...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)
        return True

    log_error(f"  [!] 导航超时: {template_path}")
    return False


# ==========================================
# 购买宏
# ==========================================


def action_buy_single_car(hwnd, gamepad, car_index):
    """执行单辆车购买：START → Down → A×3。"""
    log_info(f"正在执行购买流程：开始购买第 {car_index}/{CARS_TO_PROCESS} 辆车...")

    log_info("  -> START 打开购买菜单...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.0)

    log_info("  -> D-pad Down...")
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=1.0)

    for i in range(3):
        log_info(f"  -> A ({i + 1}/3)...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
        if i < 2:
            time.sleep(2.0)
        else:
            time.sleep(5.0)

    log_success(f"第 {car_index}/{CARS_TO_PROCESS} 辆车购买指令全部发送成功！")
