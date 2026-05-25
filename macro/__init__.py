# -*- coding: utf-8 -*-
"""
macro/ 包入口 — 统一导出所有公开函数 + 主循环
"""

import sys
import time
import cv2
import vgamepad as vg
import module_ocr
from colorama import Fore, Style
from utils import log_info, log_success, log_warning, log_error
# 显式导出列表（含下划线开头的"内部"函数，因为外部模块直接引用它们）
__all__ = [
    # core
    'log_state_header', 'log_step_header',
    'capture_screenshot', 'capture_raw_screenshot',
    'find_game_window', 'force_foreground', '_press_button',
    'MAX_SKILL_POINTS', 'POINTS_PER_CAR', 'CARS_TO_PROCESS',
    'STATE_BUY_CARS', 'STATE_UPGRADE_CARS', 'STATE_TRASH_CARS', 'STATE_FARM_POINTS',
    # navigation
    'load_menu_templates', 'get_current_menu_state',
    '_scan_for_subaru_page', 'navigate_menu_to_garage',
    'safe_exit_to_menu', 'return_to_garage',
    # purchase
    'navigate_to_impreza_purchase_screen',
    'is_word_similar', 'dynamic_navigate_to_target',
    'action_buy_single_car',
    # garage
    '_wait_for_designs_and_paints', '_wait_for_cars_text', '_wait_for_anna_link',
    '_navigate_garage_grid',
    'navigate_to_car_in_garage', 'navigate_to_car_for_removal',
    'navigate_to_main_car',
    'action_remove_single_car', 'action_get_in_car',
    '_scan_and_delete_cars', 'reset_upgrade_position',
    # upgrade
    'action_upgrade_car_skills',
    # main loop
    'run_master_bot_loop',
]

# 导出基础设施
from macro.core import (
    log_state_header, log_step_header,
    capture_screenshot, capture_raw_screenshot,
    find_game_window, force_foreground,
    _press_button,
    MAX_SKILL_POINTS, POINTS_PER_CAR, CARS_TO_PROCESS,
    STATE_BUY_CARS, STATE_UPGRADE_CARS, STATE_TRASH_CARS, STATE_FARM_POINTS,
)

# 导出导航
from macro.navigation import (
    load_menu_templates, get_current_menu_state,
    _scan_for_subaru_page,
    navigate_menu_to_garage,
    safe_exit_to_menu, return_to_garage,
)

# 导出购买
from macro.purchase import (
    navigate_to_impreza_purchase_screen,
    is_word_similar, dynamic_navigate_to_target,
    action_buy_single_car,
)

# 导出车库
from macro.garage import (
    _wait_for_designs_and_paints, _wait_for_cars_text, _wait_for_anna_link,
    _navigate_garage_grid,
    navigate_to_car_in_garage, navigate_to_car_for_removal,
    navigate_to_main_car,
    action_remove_single_car, action_get_in_car,
    _scan_and_delete_cars,
    reset_upgrade_position,
)

# 导出加点
from macro.upgrade import action_upgrade_car_skills

# 主循环
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

                        return_to_garage(hwnd, gamepad, anchor_templates=anchor_templates)

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

