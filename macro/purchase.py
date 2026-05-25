# -*- coding: utf-8 -*-
"""
macro/purchase.py — 5步购买导航 + 购买宏
"""

import time
import cv2
import vgamepad as vg
from utils import log_info, log_success, log_warning, log_error, safe_print, find_game_window
from utils import press_button as _press_button
from macro.core import (
    capture_screenshot, capture_raw_screenshot,
    log_step_header, log_state_header,
    CARS_TO_PROCESS,
)
from macro.navigation import get_current_menu_state
import pytesseract
import module_ocr
from module_ocr import DEBUG_WRITE_FILES

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

