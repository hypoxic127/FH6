# -*- coding: utf-8 -*-
"""
macro/garage.py — 车库网格操作（选车、删车、主力车导航）
"""

import time
import cv2
import numpy as np
import vgamepad as vg
from utils import log_info, log_success, log_warning, log_error
from utils import press_button as _press_button
from macro.core import capture_screenshot, capture_raw_screenshot
import pytesseract
import module_ocr

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
            # 容错匹配: OCR 常把 1998→w99b/1898/1988 等
            import re as _re
            has_year = bool(_re.search(r'.?99[8b6]', card_text)) or any(y in card_text for y in ["1998", "1898", "1988", "199"])
            has_brand = any(b in card_text for b in ["subaru", "sub", "impreza"])
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
                        import re as _re
                        has_year = bool(_re.search(r'.?99[8b6]', card_text)) or any(y in card_text for y in ["1998", "1898", "1988", "199"])
                        has_brand = any(b in card_text for b in ["subaru", "sub", "impreza"])
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

