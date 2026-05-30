# -*- coding: utf-8 -*-
"""
macro/garage.py — 车库网格操作（选车、删车、主力车导航）
"""

import time

import cv2
import numpy as np
import pytesseract
import vgamepad as vg

import engine.ocr as module_ocr
from engine.utils import log_info, log_success, log_warning
from engine.utils import press_button as _press_button
from macro.core import capture_raw_screenshot, capture_screenshot


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
        top_roi = raw_img[int(h * 0.07) : int(h * 0.25), 0 : int(w * 0.25)]
        gray = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config="--psm 7").strip().lower()
        if "design" in text and "paint" in text:
            log_success(f"  ✅ 检测到 'Designs and Paints' (OCR: '{text}'，等待 {i + 1}s)")
            return True
        if i % 2 == 1:
            log_info(f"  等待 Designs and Paints... #{i + 1}: OCR='{text}'")
    log_warning(f"  ⚠️ {max_wait}s 内未检测到 'Designs and Paints'")
    return False


def _wait_for_cars_text(hwnd, max_wait=8):
    """
    轮询检测 'Cars' / 'My Cars' 文字，确认在菜单页面可以按 A 进入车库。
    返回 True 表示检测到，False 表示超时未检测到。
    """
    for i in range(max_wait):
        time.sleep(1.0)
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is None:
            continue
        h, w = raw_img.shape[:2]
        # "My Cars" 大白字位置（标注工具确认：19-28% 高度, 3-14% 宽度）
        top_roi = raw_img[int(h * 0.19) : int(h * 0.28), int(w * 0.03) : int(w * 0.14)]
        gray = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config="--psm 7").strip().lower()
        if "car" in text:
            log_success(f"  ✅ 检测到 'My Cars' (OCR: '{text}'，等待 {i + 1}s)")
            return True
        if i % 2 == 1:
            log_info(f"  等待 My Cars... #{i + 1}: OCR='{text}'")
    log_warning(f"  ⚠️ {max_wait}s 内未检测到 'My Cars'")
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
        # ANNA / LINK 在画面底部 (h93-96%, w10-15%)
        bottom_roi = raw_img[int(h * 0.93) : int(h * 0.96), int(w * 0.10) : int(w * 0.15)]
        gray = cv2.cvtColor(bottom_roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config="--psm 7").strip().lower()
        if "anna" in text or "link" in text:
            log_success(f"  ✅ 检测到自由漫游界面 (OCR: '{text}'，等待 {i + 1}s)")
            return True
        if i % 2 == 1:
            log_info(f"  等待自由漫游 (ANNA/LINK)... #{i + 1}: OCR='{text}'")
    log_warning(f"  ⚠️ {max_wait}s 内未检测到 ANNA/LINK")
    return False


def _navigate_garage_grid(hwnd, gamepad, verify_fn, label="车", start_col=1, start_row=1):
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
        log_info("  遍历模式: 打字机走位（逐列从上到下，复位后右移）")

    MAX_COLUMNS = 200  # 安全上限
    total_excluded = 0  # 累计跳过的车（仅统计）

    # --- Impreza 区域检测 ---
    # 车库按品牌排列，Impreza 22B 聚在一起。进入区域后离开即可停止。
    in_impreza_zone = False  # 是否已进入 Impreza 区域
    consecutive_non_impreza = 0  # 连续非 Impreza 的单元格数
    NON_IMPREZA_EXIT_THRESHOLD = 3  # 连续 3 个非 Impreza 就视为已离开区域

    # 快进到起始列：按 Right 移动到 start_col
    if start_col > 1:
        log_info(f"  ⏩ 快进: 按 {start_col - 1} 次 Right 跳到第 {start_col} 列...")
        for _ in range(start_col - 1):
            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.15)
        time.sleep(0.3)

    for col in range(start_col, start_col + MAX_COLUMNS):
        log_info("")
        log_info(f"{'=' * 40}")
        log_info(f"  📋 正在扫描第 {col} 列...")
        log_info(f"{'=' * 40}")

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
                log_warning(f"    [行{row + 1}] 无法检测到光标")
                break
            cx, cy = cursor_pos
            log_info(f"    [行{row + 1}] 光标位置: ({cx}, {cy})")

            # === 空位检测（使用统一函数）===
            is_empty_slot = module_ocr.is_empty_slot(resized, cx, cy)
            if is_empty_slot:
                log_info(f"    [行{row + 1}] 🔲 检测到空位，跳过")
            if is_empty_slot:
                if row == 0:
                    # 第 1 行就是空位 → 整列为空，直接跳过本列
                    log_info(f"    [行{row + 1}] 第 1 行即为空位，跳过整列")
                    break
                else:
                    # 第 2/3 行是空位 → 网格不规则，品牌区域已扫完
                    log_info(f"    [行{row + 1}] 检测到空位，品牌区域已扫完，停止扫描")
                    # 先复位再退出
                    if rows_descended > 0:
                        log_info(f"  ⬆️ 复位: 按 {rows_descended} 次 Up 回到第 1 行...")
                        for i in range(rows_descended):
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                    return False, 0, 0

            # 直接使用 OCR 校验函数判断当前单元格
            if verify_fn(resized, cx, cy):
                in_impreza_zone = True
                consecutive_non_impreza = 0
                log_success(f"    [行{row + 1}] ✅ {label} 校验通过！按 A 进入详情... (列{col}, 行{row + 1})")
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                return True, col, row + 1
            else:
                total_excluded += 1
                log_info(f"    [行{row + 1}] 校验未通过，跳过 (累计跳过: {total_excluded})")

            # --- Impreza 区域检测（每个单元格都检测） ---
            # 利用 LEGENDARY 橙色标签作为区域标识：所有 Impreza 22B 都是 LEGENDARY
            # verify_fn 内部已经做过 OCR，这里只用轻量 HSV 颜色检测
            try:
                _crop_w, _crop_h = module_ocr.CARD_CROP_W, module_ocr.CARD_CROP_H
                _x1 = max(0, cx - _crop_w // 2)
                _x2 = min(resized.shape[1], cx + _crop_w // 2)
                _y1 = max(0, cy - _crop_h // 2)
                _y2 = min(resized.shape[0], cy + _crop_h // 2)
                _card = resized[_y1:_y2, _x1:_x2]
                if _card.size > 0:
                    _ch, _cw = _card.shape[:2]
                    _rarity = _card[int(_ch * 0.82) : int(_ch * 0.94), int(_cw * 0.04) : int(_cw * 0.70)]
                    if _rarity.size > 0:
                        _hsv = cv2.cvtColor(_rarity, cv2.COLOR_BGR2HSV)
                        _omask = cv2.inRange(_hsv, np.array([10, 100, 100]), np.array([25, 255, 255]))
                        _opx = cv2.countNonZero(_omask)
                        is_legendary = _opx > 200
                        if is_legendary:
                            if not in_impreza_zone:
                                in_impreza_zone = True
                                log_info(f"    [区域检测] 🟠 进入 LEGENDARY 区域 (橙色: {_opx}px)")
                            consecutive_non_impreza = 0
                        elif in_impreza_zone:
                            consecutive_non_impreza += 1
                            log_info(
                                f"    [区域检测] 非 LEGENDARY 卡片 (连续 {consecutive_non_impreza}/{NON_IMPREZA_EXIT_THRESHOLD})"
                            )
            except Exception:
                if in_impreza_zone:
                    consecutive_non_impreza += 1

            # 如果不是最后一行，检查下方是否有车再决定是否 Down
            if row < 2:
                if module_ocr.has_cell_below(resized, cx, cy):
                    log_info(f"    [行{row + 1}] 下方有车，按 D-pad Down...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                    rows_descended += 1
                else:
                    log_info(f"    [行{row + 1}] 下方为空位，停止本列向下扫描")
                    break

        # === 步骤 C: 复位 — 按等量 Up 回到第 1 行 ===
        if rows_descended > 0:
            log_info(f"  ⬆️ 复位: 按 {rows_descended} 次 Up 回到第 1 行...")
            for i in range(rows_descended):
                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
            time.sleep(0.3)

        # === Impreza 区域退出检测 ===
        if in_impreza_zone and consecutive_non_impreza >= NON_IMPREZA_EXIT_THRESHOLD:
            log_success(f"  🏁 已离开 Impreza 区域 (连续 {consecutive_non_impreza} 个非 Impreza)，停止扫描！")
            return False, 0, 0

        # === 步骤 D: 在第 1 行按 Right 进入下一列 ===
        log_info(f"  ➡️ 按 Right 移到第 {col + 1} 列...")
        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.5)

    log_info(f"  已扫描 {MAX_COLUMNS} 列，未找到更多 {label}")
    return False, 0, 0


# 模块级变量：记住上次加点选车位置
_last_upgrade_col = 1
_last_upgrade_row = 1


def navigate_to_car_in_garage(hwnd, gamepad, target_keyword="IMPREZA"):
    """选择有 NEW 标签的 Impreza（用于加点），从上次位置继续扫描"""
    global _last_upgrade_col, _last_upgrade_row

    def _verify(resized, cx, cy):
        # 双重校验：OCR 车名包含 IMPREZA + NEW 黄色标签
        return module_ocr.verify_new_target_car(resized, cx, cy, target_keyword=target_keyword)

    log_info(f"  📍 上次位置: 列{_last_upgrade_col}, 行{_last_upgrade_row}")
    result, found_col, found_row = _navigate_garage_grid(
        hwnd, gamepad, _verify, label="NEW 车", start_col=_last_upgrade_col, start_row=_last_upgrade_row
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


def _scan_and_delete_cars(hwnd, gamepad):
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

    MAX_COLUMNS = 40
    consecutive_empty_cols = 0
    MAX_EMPTY_COLS = 5
    removed_count = 0
    current_row = 1  # 1-indexed
    current_col = 1

    def _is_removable(resized, cx, cy):
        """检查当前车是否可删除：无 NEW 标签 + 非 S1/S2 级别 + 卡片含 Impreza 22B 关键词"""
        has_new = module_ocr.check_new_tag_only(resized, cx, cy)
        if has_new:
            log_warning("  ⚠️ 该车仍有 NEW 标签（未加点），跳过...")
            return False
        if module_ocr.check_is_high_class(resized, cx, cy):
            log_warning("  ⚠️ 该车是 S1/S2 级别（主力车），跳过！")
            return False
        # 卡片 OCR 校验：复用 _ocr_card_text + 全局关键词常量
        try:
            crop_w, crop_h = module_ocr.CARD_CROP_W, module_ocr.CARD_CROP_H
            _x1 = max(0, cx - crop_w // 2)
            _x2 = min(resized.shape[1], cx + crop_w // 2)
            _y1 = max(0, cy - crop_h // 2)
            _y2 = min(resized.shape[0], cy + crop_h // 2)
            card_roi = resized[_y1:_y2, _x1:_x2]
            card_text = module_ocr._ocr_card_text(card_roi, debug_label="DELETE")
            matched = [kw for kw in module_ocr.IMPREZA_22B_KEYWORDS if kw in card_text]
            if len(matched) >= module_ocr.IMPREZA_22B_MIN_MATCH:
                log_success(f"  ✅ 卡片 OCR 确认: 关键词 {len(matched)}/3 {matched}")
            else:
                log_warning(
                    f"  ⚠️ 卡片 OCR 未匹配 Impreza 22B (命中 {len(matched)}/3 {matched}, OCR: '{card_text[:50]}')，跳过！"
                )
                return False
        except Exception as e:
            log_warning(f"  ⚠️ 卡片 OCR 异常: {e}，安全跳过")
            return False
        return True

    while current_col <= MAX_COLUMNS:
        log_info(f"\n{'=' * 40}")
        log_info(f"  📋 [删车] 正在扫描第 {current_col} 列...")
        log_info(f"{'=' * 40}")

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

            # 空位检测（使用统一函数）
            is_empty = module_ocr.is_empty_slot(resized, cx, cy)
            if is_empty:
                log_info(f"    [行{current_row}] 🔲 检测到空位")

            if is_empty:
                if current_row == 1:
                    log_info(f"    [行{current_row}] 第 1 行空位，跳过整列")
                    break
                else:
                    log_info(f"    [行{current_row}] 空位，品牌区域已扫完")
                    return removed_count

            # 直接使用 OCR 校验判断是否可删除
            if _is_removable(resized, cx, cy):
                col_has_target = True
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
                log_info(
                    f"  [状态修正] 删除前: (行{old_row}, 列{old_col}) → 光标退到: (行{current_row}, 列{current_col})"
                )

                # === 恢复扫描位置 ===
                if current_row in (1, 2):
                    log_info(f"  [恢复] 按 Down 前进到行{current_row + 1}...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                    current_row += 1
                elif current_row == 3:
                    log_info("  [恢复] 跨列回退：按 Right → Up×2 回到第 1 行...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=0.5)
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, delay=0.3)
                    current_col += 1
                    current_row = 1

                continue
            else:
                log_info(f"    [行{current_row}] 校验未通过，跳过")

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

        # 品牌标签检测: 按 Right 后动态检测当前选中的标签（使用统一函数）
        raw_img = capture_raw_screenshot(hwnd)
        if raw_img is not None:
            sel_text = module_ocr.detect_selected_brand_tab(raw_img)
            if sel_text is not None and "subaru" not in sel_text:
                log_info(f"  🛑 选中标签: '{sel_text}'，已离开 Subaru 区域")
                return removed_count

    log_info(f"  已扫描 {MAX_COLUMNS} 列，删车完成。")
    return removed_count


def navigate_to_car_for_removal(hwnd, gamepad, target_keyword="IMPREZA"):
    """选择没有 NEW 标签且为 B 级的 Impreza（已加点，可移除）"""

    def _verify(resized, cx, cy):
        has_new = module_ocr.check_new_tag_only(resized, cx, cy)
        if has_new:
            log_warning("  ⚠️ 该车仍有 NEW 标签（未加点），需保留，跳过...")
            return False

        if module_ocr.check_is_high_class(resized, cx, cy):
            log_warning("  ⚠️ 该车是 S1/S2 级别（用户主力车），跳过！")
            return False

        log_success("    无 NEW 标签且为 B 级，可以移除！")
        return True

    result, _, _ = _navigate_garage_grid(hwnd, gamepad, _verify, label="移除车")
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


def navigate_to_main_car(hwnd, gamepad):
    """
    选择 S1/S2 级别的主力车（用于上车跑图）。

    不依赖 target_car.png 模板匹配（S2 主力车外观与 B 级不同，模板会失配），
    而是逐格扫描车库网格，直接用 PI 紫色徽章检测找到唯一的 S2 车。
    """
    log_info("正在启动车库网格导航: 主力车搜索...")
    log_info("  扫描模式: 逐格 PI 颜色检测（不依赖模板匹配）")

    MAX_COLUMNS = 30  # 主力车不会太远
    MAX_CONSECUTIVE_EMPTY = 3  # 连续空列停止

    consecutive_empty = 0
    rows_descended = 0

    for col in range(1, MAX_COLUMNS + 1):
        log_info("")
        log_info(f"{'=' * 40}")
        log_info(f"  📋 正在扫描第 {col} 列...")
        log_info(f"{'=' * 40}")

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
                log_warning(f"    [行{row + 1}] 无法检测到光标")
                break
            cx, cy = cursor_pos
            log_info(f"    [行{row + 1}] 光标位置: ({cx}, {cy})")

            # 空位检测（使用统一函数）
            is_empty = module_ocr.is_empty_slot(resized, cx, cy)

            if is_empty:
                log_info(f"    [行{row + 1}] 🔲 空位，跳过")
                if row == 0:
                    break  # 整列空
                else:
                    break  # 本列剩余行空

            col_found_car = True

            # 直接检测 PI 颜色，不需要模板匹配
            if module_ocr.check_is_high_class(resized, cx, cy):
                # 二次验证：复用 _ocr_card_text 管线确认是 Impreza 22B
                is_target_car = False
                try:
                    crop_w, crop_h = module_ocr.CARD_CROP_W, module_ocr.CARD_CROP_H
                    _x1 = max(0, cx - crop_w // 2)
                    _x2 = min(resized.shape[1], cx + crop_w // 2)
                    _y1 = max(0, cy - crop_h // 2)
                    _y2 = min(resized.shape[0], cy + crop_h // 2)
                    card_roi = resized[_y1:_y2, _x1:_x2]
                    card_text = module_ocr._ocr_card_text(card_roi, debug_label="MAIN_CAR")
                    # 多关键词匹配（使用全局常量）
                    matched = [kw for kw in module_ocr.IMPREZA_22B_KEYWORDS if kw in card_text]
                    if len(matched) >= module_ocr.IMPREZA_22B_MIN_MATCH:
                        log_success(f"    [行{row + 1}] ✅ 卡片 OCR 确认: 关键词 {len(matched)}/3 {matched}")
                        is_target_car = True
                    else:
                        log_warning(
                            f"    [行{row + 1}] ⚠️ S2 但非目标车 (命中 {len(matched)}/3 {matched}, OCR: '{card_text[:50]}')，跳过"
                        )
                except Exception as e:
                    log_warning(f"    [行{row + 1}] ⚠️ 卡片 OCR 异常: {e}")

                if is_target_car:
                    log_success(
                        f"    [行{row + 1}] ✅ 找到主力车（S2 + Impreza 22B）！按 A 进入详情... (列{col}, 行{row + 1})"
                    )
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=2.0)
                    return True, col, row + 1
                else:
                    log_info(f"    [行{row + 1}] S 级但非目标车，跳过...")
            else:
                log_info(f"    [行{row + 1}] B 级车，跳过...")

            # 下一行
            if row < 2:
                if module_ocr.has_cell_below(resized, cx, cy):
                    log_info(f"    [行{row + 1}] 下方有车，按 D-pad Down...")
                    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, delay=0.5)
                    rows_descended += 1
                else:
                    log_info(f"    [行{row + 1}] 下方为空位，停止本列向下扫描")
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
    """在详情页选择 'Get In Car'（第一个选项）并确认"""
    log_info("  Get In Car...")
    time.sleep(1.0)
    _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
    log_success("  ✅ 已上车！")
