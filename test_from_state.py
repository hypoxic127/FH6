# -*- coding: utf-8 -*-
"""
FORZA HORIZON 6 AUTOBOT — 调试测试入口 (test_from_state.py)
======================================
允许单独测试各个子功能，无需跑完整状态机。

16 项测试覆盖：
  - 导航类：返回车库 / 视觉刹车 / 菜单导航 / 五步导航
  - 车库操作类：选车 / 加点 / 单车循环 / 主力车寻找
  - 删车/购买类：扫描删车 / 购买单车 / 移除单车
  - OCR 调试类：Car Select / Available Points / NEW 标签 / 卡片文字

用法:
    python test_from_state.py              # 交互式选择测试项目
    python test_from_state.py 1            # 直接运行对应编号的测试
"""

import sys
import time
import cv2
import vgamepad as vg
from colorama import init, Fore, Style

import module_macro
import module_ocr

init(autoreset=True)

# ==========================================
# 测试选项
# ==========================================
TEST_OPTIONS = {
    "1":  "return_to_garage       完整返回车库流程 (B退回 + Down×1→A→Down×7→A + OCR Car Select + LB扫Subaru)",
    "2":  "safe_exit_to_menu      仅视觉刹车退回主菜单 (反复按 B 直到识别到锚点)",
    "3":  "menu_to_garage         从主菜单导航进入车库 (9步宏序列)",
    "4":  "garage_car_select      仅测试车库选车导航 (2D网格找NEW标签Impreza)",
    "5":  "upgrade_car_skills     仅测试加点宏 (前提: 已选中车辆在详情页)",
    "6":  "single_car_cycle       单车完整循环 (选车→加点→返回车库) 可指定循环次数",
    "7":  "scan_and_delete        带状态机的扫描删车 (前提: 已在车库Subaru页面)",
    "8":  "full_state_machine     从指定状态启动完整状态机循环",
    "9":  "navigate_to_main_car   在车库网格中寻找主力车 (S1/S2 级别)",
    "10": "navigate_to_impreza    五步导航至 Impreza 购买界面",
    "11": "buy_single_car         仅测试购买单辆车宏 (前提: 已在购买界面)",
    "12": "remove_single_car      仅测试移除单辆车宏 (前提: 已选中车在详情页)",
    "13": "ocr_car_select         OCR测试: 截图检测 'Car Select' (前提: 游戏在车库界面)",
    "14": "ocr_available_points   OCR测试: 截图检测 Available Points (前提: 游戏在技能树界面)",
    "15": "debug_new_tag          NEW标签调试: 截图分析所有卡片黄色像素 (前提: 游戏在车库网格界面)",
    "16": "ocr_card_text          OCR测试: 截图读取卡片车型文字 (前提: 游戏在车库网格界面)",
}


def print_menu():
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==================================================")
    print(f"{Fore.CYAN}{Style.BRIGHT}   🧪 FORZA HORIZON 6 AUTOBOT - 功能测试入口")
    print(f"{Fore.CYAN}{Style.BRIGHT}   选择要测试的功能 [1-{len(TEST_OPTIONS)}]:")
    print(f"{Fore.CYAN}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    # 分类显示
    categories = {
        "📍 导航类": ["1", "2", "3", "10"],
        "🚗 车库操作类": ["4", "5", "6", "9"],
        "🗑️ 删车/购买类": ["7", "11", "12"],
        "🔄 完整流程类": ["8"],
        "🔍 OCR 调试类": ["13", "14", "15", "16"],
    }
    for cat_name, keys in categories.items():
        print(f"  {Fore.CYAN}{cat_name}{Style.RESET_ALL}")
        for key in keys:
            if key in TEST_OPTIONS:
                desc = TEST_OPTIONS[key]
                func_name, explanation = desc.split(None, 1)
                print(f"    {Fore.YELLOW}[{key:>2}]{Style.RESET_ALL}  {Fore.GREEN}{func_name}{Style.RESET_ALL}")
                print(f"         {explanation}")
        print()


def init_environment():
    """
    初始化所有测试共用的环境：
    1. 查找并激活 Forza Horizon 6 游戏窗口
    2. 初始化虚拟 Xbox 360 手柄
    3. 加载视觉模板（菜单标签 + 导航锚点）
    返回: (hwnd, gamepad, menu_templates, anchor_templates)
    """
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==================================================")
    print(f"{Fore.CYAN}{Style.BRIGHT}    🚗 初始化测试环境...")
    print(f"{Fore.CYAN}{Style.BRIGHT}=================================================={Style.RESET_ALL}")

    # 1. 查找游戏窗口
    hwnd = module_macro.find_game_window()
    if hwnd:
        module_macro.log_success("Forza Horizon 6 游戏窗口已成功检测！")
        module_macro.force_foreground(hwnd)
    else:
        module_macro.log_warning("未找到游戏窗口！视觉导航测试需要游戏窗口在前台。")

    # 2. 初始化虚拟手柄
    module_macro.log_info("正在装载虚拟 Xbox 360 控制器驱动...")
    try:
        gamepad = vg.VX360Gamepad()
        module_macro.log_success("虚拟控制器装载成功！")
    except Exception as e:
        module_macro.log_error(f"装载虚拟手柄驱动失败: {e}")
        sys.exit(1)

    # 3. 加载视觉模板
    menu_templates, anchor_templates = module_macro.load_menu_templates()

    return hwnd, gamepad, menu_templates, anchor_templates


def countdown(seconds=3):
    """倒计时提示"""
    module_macro.log_info(f"{seconds} 秒后开始执行，请确保游戏窗口在前台...")
    time.sleep(seconds)


# ==========================================
# 各测试函数
# ==========================================

def test_return_to_garage(hwnd, gamepad, anchor_templates):
    """测试 1: 完整返回车库流程"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: return_to_garage()")
    print(f"   流程: B退回主菜单 → Down×2→A→Down×7→A → 轮询my_cars → LB扫Subaru")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    module_macro.return_to_garage(hwnd, gamepad, anchor_templates=anchor_templates)
    module_macro.log_success("🎉 return_to_garage 测试完成！")


def test_safe_exit_to_menu(hwnd, gamepad):
    """测试 2: 仅视觉刹车退回主菜单"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: safe_exit_to_menu()")
    print(f"   功能: 反复按 B 键，直到画面中匹配到 btn_My_car.png 锚点")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    try:
        module_macro.safe_exit_to_menu(hwnd, gamepad)
        module_macro.log_success("🎉 safe_exit_to_menu 测试成功！已成功退回主菜单。")
    except TimeoutError as e:
        module_macro.log_error(f"safe_exit_to_menu 测试失败: {e}")
    except FileNotFoundError as e:
        module_macro.log_error(f"锚点模板缺失: {e}")


def test_menu_to_garage(hwnd, gamepad, anchor_templates):
    """测试 3: 从主菜单导航进入车库"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: navigate_menu_to_garage()")
    print(f"   流程: RB×2→A×2→轮询Campaign→RB×2→Down×2→A→Down×7→A→LB扫Subaru")
    print(f"   前提: 当前必须在主菜单界面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    module_macro.navigate_menu_to_garage(hwnd, gamepad, anchor_templates=anchor_templates)
    module_macro.log_success("🎉 主菜单→车库导航宏测试完成！")


def test_garage_car_select(hwnd, gamepad):
    """测试 4: 仅车库选车导航"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: navigate_to_car_in_garage()")
    print(f"   功能: 在车库网格中用模板匹配定位 NEW 标签 Impreza")
    print(f"   前提: 当前必须已在车库网格 Subaru 页面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    success = module_macro.navigate_to_car_in_garage(hwnd, gamepad)
    if success:
        module_macro.log_success("🎉 车库选车导航测试成功！已找到目标车并进入详情页。")
    else:
        module_macro.log_error("车库选车导航测试失败！未能找到目标车辆。")


def test_upgrade_car_skills(hwnd, gamepad):
    """测试 5: 仅测试加点宏"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: action_upgrade_car_skills()")
    print(f"   流程: B×1→Up×1→A(进技能树)→Down×7→A→OCR Available Points→...")
    print(f"   前提: 当前已选中车辆在详情页（光标在车辆上按了A）")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    remaining = module_macro.action_upgrade_car_skills(hwnd, gamepad)
    module_macro.log_success(f"🎉 加点宏测试完成！剩余 Available Points: {remaining}")


def test_single_car_cycle(hwnd, gamepad, anchor_templates):
    """测试 6: 单车完整循环"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: 单车完整循环 (选车→加点→返回车库)")
    print(f"   前提: 当前必须已在车库网格 Subaru 页面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    count_str = input(f"  {Fore.CYAN}要测试几辆车的循环？[默认 1]: {Style.RESET_ALL}").strip()
    car_count = int(count_str) if count_str.isdigit() and int(count_str) > 0 else 1
    countdown()

    for i in range(1, car_count + 1):
        module_macro.log_info(f"\n{'='*50}")
        module_macro.log_info(f"[CAR #{i}/{car_count}] 开始第 {i} 辆车的完整循环")
        module_macro.log_info(f"{'='*50}")

        # ① 选车
        module_macro.log_info("  [步骤 1/3] 搜索并锁定目标车辆...")
        success = module_macro.navigate_to_car_in_garage(hwnd, gamepad)
        if not success:
            module_macro.log_error(f"  [!] 第 {i} 辆车锁定失败！")
            break

        # ② 加点
        module_macro.log_info("  [步骤 2/3] 执行加点宏...")
        remaining = module_macro.action_upgrade_car_skills(hwnd, gamepad)
        if remaining is not None and 0 <= remaining < 30:
            module_macro.log_warning(f"  Available Points = {remaining} < 30，停止循环")
            break

        # ③ 返回车库
        module_macro.log_info("  [步骤 3/3] 返回车库...")
        module_macro.return_to_garage(hwnd, gamepad, anchor_templates=anchor_templates)

        module_macro.log_success(f"  ✅ 第 {i}/{car_count} 辆车完整循环完成！")

    module_macro.log_success(f"🎉 循环测试完成！")


def test_scan_and_delete(hwnd, gamepad):
    """测试 7: 带状态机的扫描删车"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: _scan_and_delete_cars()")
    print(f"   功能: 带状态机的车库扫描删除 (删后光标修正)")
    print(f"   前提: 当前必须已在车库网格 Subaru 页面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    removed = module_macro._scan_and_delete_cars(hwnd, gamepad)
    module_macro.log_success(f"🎉 扫描删车测试完成！共移除 {removed} 辆车")


def test_full_state_machine(hwnd, gamepad, menu_templates, anchor_templates):
    """测试 8: 从指定状态启动完整状态机"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: 从指定状态启动完整状态机循环")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    states = {
        "1": module_macro.STATE_BUY_CARS,
        "2": module_macro.STATE_UPGRADE_CARS,
        "3": module_macro.STATE_TRASH_CARS,
        "4": module_macro.STATE_FARM_POINTS,
    }
    print(f"  {Fore.YELLOW}[1]{Style.RESET_ALL}  STATE_BUY_CARS      (从买车开始)")
    print(f"  {Fore.YELLOW}[2]{Style.RESET_ALL}  STATE_UPGRADE_CARS  (从加点开始)")
    print(f"  {Fore.YELLOW}[3]{Style.RESET_ALL}  STATE_TRASH_CARS    (从删车开始)")
    print(f"  {Fore.YELLOW}[4]{Style.RESET_ALL}  STATE_FARM_POINTS   (从刷图开始)")
    print()
    state_choice = input(f"  {Fore.CYAN}选择起始状态 [1-4，默认 1]: {Style.RESET_ALL}").strip()
    initial_state = states.get(state_choice, module_macro.STATE_BUY_CARS)

    module_macro.log_info(f"将从 {initial_state} 状态启动状态机...")
    countdown()
    module_macro.run_master_bot_loop(initial_state=initial_state)


def test_navigate_to_main_car(hwnd, gamepad):
    """测试 9: 在车库寻找主力车"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: navigate_to_main_car()")
    print(f"   功能: 在车库网格中寻找 S1/S2 级别的主力车")
    print(f"   前提: 当前必须已在车库网格 Subaru 页面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    success = module_macro.navigate_to_main_car(hwnd, gamepad)
    if success:
        module_macro.log_success("🎉 找到主力车！已进入详情页。")
    else:
        module_macro.log_error("未能找到主力车。")


def test_navigate_to_impreza(hwnd, gamepad, menu_templates, anchor_templates):
    """测试 10: 五步导航至购买界面"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: navigate_to_impreza_purchase_screen()")
    print(f"   功能: 五步视觉导航从任意界面寻路至 Subaru Impreza 购买界面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    success = module_macro.navigate_to_impreza_purchase_screen(hwnd, gamepad, menu_templates, anchor_templates)
    if success:
        module_macro.log_success("🎉 五步导航测试成功！")
    else:
        module_macro.log_error("五步导航测试失败！")


def test_buy_single_car(hwnd, gamepad):
    """测试 11: 仅测试购买单辆车宏"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🧪 测试: action_buy_single_car()")
    print(f"   流程: START→Down×1→A×3 (购买确认)")
    print(f"   前提: 当前已在 Impreza 购买界面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    module_macro.action_buy_single_car(hwnd, gamepad, car_index=1)
    module_macro.log_success("🎉 购买单车宏测试完成！")


def test_remove_single_car(hwnd, gamepad):
    """测试 12: 仅测试移除单辆车宏"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")

    print(f"   🧪 测试: action_remove_single_car()")
    print(f"   流程: Down×4→A→Right→A (移除确认)")
    print(f"   前提: 当前已选中车辆在详情页")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")
    countdown()
    module_macro.action_remove_single_car(hwnd, gamepad, car_index=1)
    module_macro.log_success("🎉 移除单车宏测试完成！")


def test_ocr_car_select(hwnd):
    """测试 13: OCR 截图检测 'Car Select'（不需要手柄）"""
    import pytesseract
    import numpy as np
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🔍 OCR 测试: 检测 'Car Select'")
    print(f"   前提: 游戏画面在车库界面（能看到 Car Select 标题）")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    for attempt in range(3):
        print(f"\n  --- 第 {attempt + 1}/3 次截图 ---")
        resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
        if resized is None:
            module_macro.log_error("截图失败！")
            time.sleep(1.0)
            continue

        h, w = resized.shape[:2]
        # 测试多种 ROI 范围
        rois = {
            "ROI_A (4-12%, 0-20%)":  resized[int(h*0.04):int(h*0.12), 0:int(w*0.20)],
            "ROI_B (7-14%, 0-15%)":  resized[int(h*0.07):int(h*0.14), 0:int(w*0.15)],
            "ROI_C (5-15%, 0-25%)":  resized[int(h*0.05):int(h*0.15), 0:int(w*0.25)],
            "ROI_D (3-10%, 0-20%)":  resized[int(h*0.03):int(h*0.10), 0:int(w*0.20)],
        }
        for name, roi in rois.items():
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            text = pytesseract.image_to_string(thresh, config='--psm 7').strip()
            has_car_select = "car" in text.lower() and "select" in text.lower()
            status = f"{Fore.GREEN}✅ 命中！" if has_car_select else f"{Fore.RED}✗ 未命中"
            print(f"    {name}: OCR='{text}' → {status}{Style.RESET_ALL}")
            # 保存调试图片
            debug_name = name.split(" ")[0].lower()
            cv2.imwrite(f"debug_{debug_name}_thresh.png", thresh)
            cv2.imwrite(f"debug_{debug_name}_roi.png", roi)

        print(f"\n  💾 调试图片已保存到当前目录 (debug_roi_*.png, debug_roi_*_thresh.png)")
        time.sleep(2.0)

    module_macro.log_success("🎉 OCR Car Select 测试完成！")


def test_ocr_available_points(hwnd):
    """测试 14: OCR 截图检测 Available Points（不需要手柄）"""
    import pytesseract
    import re
    import numpy as np
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🔍 OCR 测试: 检测 Available Points")
    print(f"   前提: 游戏画面在 Car Mastery 技能树界面")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    for attempt in range(3):
        print(f"\n  --- 第 {attempt + 1}/3 次截图 ---")
        resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
        if resized is None:
            module_macro.log_error("截图失败！")
            time.sleep(1.0)
            continue

        h, w = resized.shape[:2]
        # 测试多种 ROI 范围
        rois = {
            "ROI_A (85-100%, 0-50%)":   resized[int(h*0.85):h, 0:int(w*0.50)],
            "ROI_B (87-93%, 20-45%)":   resized[int(h*0.87):int(h*0.93), int(w*0.20):int(w*0.45)],
            "ROI_C (85-95%, 15-50%)":   resized[int(h*0.85):int(h*0.95), int(w*0.15):int(w*0.50)],
            "ROI_D (88-94%, 0-30%)":    resized[int(h*0.88):int(h*0.94), 0:int(w*0.30)],
        }
        for name, roi in rois.items():
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            upscaled = cv2.resize(thresh, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            text_full = pytesseract.image_to_string(upscaled, config='--psm 7').strip()
            text_digits = pytesseract.image_to_string(upscaled, config='--psm 7 -c tessedit_char_whitelist=0123456789').strip()
            numbers = re.findall(r'\d+', text_digits)
            pts = int(numbers[0]) if numbers else -1
            print(f"    {name}:")
            print(f"      全文: '{text_full}' | 数字: '{text_digits}' → 解析: {pts}")
            # 保存调试图片
            debug_name = name.split(" ")[0].lower()
            cv2.imwrite(f"debug_ap_{debug_name}_thresh.png", thresh)
            cv2.imwrite(f"debug_ap_{debug_name}_roi.png", roi)

        print(f"\n  💾 调试图片已保存到当前目录 (debug_ap_*.png)")
        time.sleep(2.0)

    module_macro.log_success("🎉 OCR Available Points 测试完成！")


def test_debug_new_tag(hwnd):
    """测试 15: 截图分析所有卡片的 NEW 标签黄色像素"""
    import numpy as np
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🔍 NEW 标签调试: 分析车库网格卡片")
    print(f"   前提: 游戏画面在车库网格界面（Subaru 页面）")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
    if resized is None:
        module_macro.log_error("截图失败！")
        return

    h, w = resized.shape[:2]
    cv2.imwrite("debug_new_fullscreen.png", resized)
    print(f"  画面尺寸: {w}x{h}")

    # 车库网格典型位置 (1600x900): 3行 × ~6列
    card_positions = [
        # (列, 行, cx, cy) - 基于观察到的坐标
        (1, 1, 475, 278), (1, 2, 475, 488), (1, 3, 475, 698),
        (2, 1, 752, 278), (2, 2, 752, 488), (2, 3, 752, 698),
    ]

    crop_w, crop_h = 140, 110  # 卡片半宽/半高

    print(f"\n  {'位置':<12} {'黄色像素':<12} {'阈值300':<10} {'HSV范围'}")
    print(f"  {'─'*60}")

    for col, row, cx, cy in card_positions:
        x1 = max(0, cx - crop_w)
        x2 = min(w, cx + crop_w)
        y1 = max(0, cy - crop_h)
        y2 = min(h, cy + crop_h)
        roi = resized[y1:y2, x1:x2]
        if roi.size == 0:
            continue

        # 检测底部区域 NEW 标签
        roi_h, roi_w = roi.shape[:2]
        roi_bottom = roi[int(roi_h*0.55):, roi_w//3:]
        hsv_roi = cv2.cvtColor(roi_bottom, cv2.COLOR_BGR2HSV)

        # 标准范围 H=20-30
        mask_std = cv2.inRange(hsv_roi, np.array([20, 100, 100]), np.array([30, 255, 255]))
        px_std = cv2.countNonZero(mask_std)

        # 宽松范围 H=15-35
        mask_wide = cv2.inRange(hsv_roi, np.array([15, 80, 80]), np.array([35, 255, 255]))
        px_wide = cv2.countNonZero(mask_wide)

        status_std = f"{Fore.GREEN}✅ NEW" if px_std > 300 else f"{Fore.RED}✗ 无"
        status_wide = f"(宽松:{px_wide})"
        print(f"  列{col}行{row} ({cx},{cy})  标准:{px_std:<6} {status_std}{Style.RESET_ALL}  {status_wide}")

        # 保存每张卡片调试图
        cv2.imwrite(f"debug_new_c{col}r{row}_card.png", roi)
        cv2.imwrite(f"debug_new_c{col}r{row}_bottom.png", roi_bottom)
        cv2.imwrite(f"debug_new_c{col}r{row}_mask_std.png", mask_std)
        cv2.imwrite(f"debug_new_c{col}r{row}_mask_wide.png", mask_wide)

    print(f"\n  💾 调试图片已保存: debug_new_c*r*_*.png")
    print(f"  📌 如果有 NEW 标签的车标准像素 < 300，需要降低阈值或扩大 HSV 范围")
    module_macro.log_success("🎉 NEW 标签调试完成！")


def test_ocr_card_text(hwnd):
    """测试 16: OCR 读取顶部信息栏车型文字（不需要手柄）"""
    import pytesseract
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"   🔍 OCR 测试: 读取顶部信息栏 (1998 SUBARU)")
    print(f"   前提: 游戏画面在车库网格界面（选中了某辆车）")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    for attempt in range(3):
        print(f"\n  --- 第 {attempt + 1}/3 次截图 ---")
        resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
        if resized is None:
            module_macro.log_error("截图失败！")
            time.sleep(1.0)
            continue

        h, w = resized.shape[:2]
        # 测试多种顶栏 ROI
        rois = {
            "A (0-4%, 5-50%)":  resized[0:int(h*0.04), int(w*0.05):int(w*0.50)],
            "B (0-5%, 5-50%)":  resized[0:int(h*0.05), int(w*0.05):int(w*0.50)],
            "C (0-5%, 0-40%)":  resized[0:int(h*0.05), 0:int(w*0.40)],
            "D (0-6%, 5-55%)":  resized[0:int(h*0.06), int(w*0.05):int(w*0.55)],
        }
        for name, roi in rois.items():
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            upscaled = cv2.resize(thresh, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            text = pytesseract.image_to_string(upscaled, config='--psm 7').strip()
            has_match = "1998" in text.lower() and "subaru" in text.lower()
            status = f"{Fore.GREEN}✅ 命中" if has_match else f"{Fore.RED}✗ 未命中"
            print(f"    {name}: '{text}' → {status}{Style.RESET_ALL}")
            debug_name = name.split(" ")[0].lower()
            cv2.imwrite(f"debug_topbar_{debug_name}_thresh.png", thresh)
            cv2.imwrite(f"debug_topbar_{debug_name}_roi.png", roi)

        print(f"\n  💾 调试图片已保存: debug_topbar_*.png")
        time.sleep(2.0)

    module_macro.log_success("🎉 顶栏 OCR 测试完成！")

# ==========================================
# 主入口
# ==========================================

if __name__ == "__main__":
    # 支持命令行直接传入测试编号
    if len(sys.argv) > 1:
        choice = sys.argv[1].strip()
    else:
        print_menu()
        choice = input(f"  {Fore.CYAN}请输入测试编号 [1-{len(TEST_OPTIONS)}]: {Style.RESET_ALL}").strip()

    if choice not in TEST_OPTIONS:
        print(f"\n  {Fore.RED}✗ 无效选项: '{choice}'。请输入 1-{len(TEST_OPTIONS)} 之间的数字。{Style.RESET_ALL}")
        sys.exit(1)

    func_name = TEST_OPTIONS[choice].split(None, 1)[0]
    print(f"\n  {Fore.GREEN}✓ 已选择测试: [{choice}] {func_name}{Style.RESET_ALL}\n")

    # 初始化共用环境
    hwnd, gamepad, menu_templates, anchor_templates = init_environment()

    try:
        if choice == "1":
            test_return_to_garage(hwnd, gamepad, anchor_templates)
        elif choice == "2":
            test_safe_exit_to_menu(hwnd, gamepad)
        elif choice == "3":
            test_menu_to_garage(hwnd, gamepad, anchor_templates)
        elif choice == "4":
            test_garage_car_select(hwnd, gamepad)
        elif choice == "5":
            test_upgrade_car_skills(hwnd, gamepad)
        elif choice == "6":
            test_single_car_cycle(hwnd, gamepad, anchor_templates)
        elif choice == "7":
            test_scan_and_delete(hwnd, gamepad)
        elif choice == "8":
            test_full_state_machine(hwnd, gamepad, menu_templates, anchor_templates)
        elif choice == "9":
            test_navigate_to_main_car(hwnd, gamepad)
        elif choice == "10":
            test_navigate_to_impreza(hwnd, gamepad, menu_templates, anchor_templates)
        elif choice == "11":
            test_buy_single_car(hwnd, gamepad)
        elif choice == "12":
            test_remove_single_car(hwnd, gamepad)
        elif choice == "13":
            test_ocr_car_select(hwnd)
        elif choice == "14":
            test_ocr_available_points(hwnd)
        elif choice == "15":
            test_debug_new_tag(hwnd)
        elif choice == "16":
            test_ocr_card_text(hwnd)
    except KeyboardInterrupt:
        print()
        module_macro.log_warning("==================================================")
        module_macro.log_warning("     ⛔ 测试被用户手动中止 (Ctrl+C)")
        module_macro.log_warning("==================================================")
        sys.exit(0)
