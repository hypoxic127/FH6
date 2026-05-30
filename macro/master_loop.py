# -*- coding: utf-8 -*-
"""
macro/master_loop.py — 主控状态机循环

从 macro/__init__.py 中分离出来，使 __init__.py 仅负责包导出。
"""

import sys
import threading
import time

import vgamepad as vg
from colorama import Fore, Style

import engine.ocr as module_ocr
from engine.utils import log_error, log_info, log_success, log_warning
from macro.core import (
    CARS_TO_PROCESS,
    MAX_SKILL_POINTS,
    STATE_BUY_CARS,
    STATE_FARM_POINTS,
    STATE_TRASH_CARS,
    STATE_UPGRADE_CARS,
    _press_button,
    capture_screenshot,
    find_game_window,
    force_foreground,
    log_state_header,
)
from macro.garage import (
    _scan_and_delete_cars,
    _wait_for_anna_link,
    _wait_for_cars_text,
    _wait_for_designs_and_paints,
    navigate_to_car_in_garage,
    navigate_to_main_car,
    reset_upgrade_position,
)
from macro.navigation import (
    _scan_for_subaru_page,
    navigate_menu_to_garage,
    return_to_garage,
)
from macro.purchase import (
    action_buy_single_car,
    navigate_to_impreza_purchase_screen,
)
from macro.upgrade import action_upgrade_car_skills

# 全局停止事件，由 Web UI 的 stop_bot 处理器设置
_stop_event: threading.Event = threading.Event()


class BotStoppedError(Exception):
    """用户通过 Web UI 主动停止 bot 时抛出。"""


def request_stop() -> None:
    """设置停止标志，主循环将在下一个检查点退出。"""
    _stop_event.set()


def clear_stop() -> None:
    """清除停止标志（启动前调用）。"""
    _stop_event.clear()


def _check_stop() -> None:
    """检查停止标志，若已设置则抛出 BotStoppedError。"""
    if _stop_event.is_set():
        raise BotStoppedError("Bot stopped by user")


def run_master_bot_loop(
    initial_state: str | None = None,
    skip_buy: bool = False,
    loop: bool = True,
) -> None:
    """
    主控制状态机。

    状态转换顺序：
      STATE_FARM_POINTS -> STATE_BUY_CARS -> STATE_UPGRADE_CARS -> STATE_TRASH_CARS -> (循环)
      当 skip_buy=True 时：
      STATE_FARM_POINTS -> STATE_UPGRADE_CARS -> STATE_TRASH_CARS -> (循环，跳过买车)

    Args:
        initial_state: 起始阶段，None 表示从 STATE_FARM_POINTS 开始
        skip_buy: 是否跳过买车阶段
        loop: True=无限循环所有阶段，False=只跑选中的阶段一次
    """

    hwnd = find_game_window()
    if not hwnd:
        log_error("Forza Horizon 6 window not found!")
        sys.exit(1)

    try:
        gamepad = vg.VX360Gamepad()
        log_success("Virtual Xbox 360 controller connected!")
    except Exception as e:
        log_error(f"装载虚拟控制器驱动失败，请检查 ViGEmBus 是否安装正确: {e}")
        sys.exit(1)

    current_state = initial_state if initial_state else STATE_FARM_POINTS
    loop_count = 1
    try:
        while True:
            _check_stop()
            log_info(f"--- 循环回路 #{loop_count} ---")
            try:
                # --- 1. 买车阶段 ---

                if current_state == STATE_BUY_CARS:
                    log_state_header(STATE_BUY_CARS, f"购车购: {CARS_TO_PROCESS} 辆")
                    success = navigate_to_impreza_purchase_screen(hwnd, gamepad)
                    if not success:
                        log_error("五步导航寻路失败！正在尝试从起始位置重试...")
                        time.sleep(2.0)
                        continue

                    log_success("五步导航阶段顺利完成！已到达购买画面")
                    log_info("正在执行宏购车购买步骤...")
                    for i in range(1, CARS_TO_PROCESS + 1):
                        action_buy_single_car(hwnd, gamepad, i)

                    log_success(f"全部 {CARS_TO_PROCESS} 辆车已购买完毕！")

                    log_info("正在连续按 4 次 B 键返回主页标签...")
                    for i in range(4):
                        log_info(f"  -> [] 按 B ({i + 1}/4)...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)

                    log_success("已按 B 键 4 次返回主页标签！")

                    current_state = STATE_UPGRADE_CARS
                    log_info("流程转换 [STATE_BUY_CARS] ====> [STATE_UPGRADE_CARS]")
                    if not loop:
                        log_success("✅ 买车阶段完成（单次模式）")
                        return
                    time.sleep(1.0)

                # --- 2. 加点阶段 ---

                elif current_state == STATE_UPGRADE_CARS:
                    log_state_header(STATE_UPGRADE_CARS, "对车库中的 NEW 车逐辆加点...")
                    reset_upgrade_position()  # 每次进入加点阶段都从头扫描（删车/跳过买车后网格已变）
                    navigate_menu_to_garage(hwnd, gamepad)
                    upgraded_count = 0
                    while True:
                        upgraded_count += 1
                        log_info(
                            f"\n{Fore.YELLOW}[CAR #{upgraded_count}]{Style.RESET_ALL} 正在导航并选中第 {upgraded_count} 辆车..."
                        )
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
                            _scan_for_subaru_page(hwnd, gamepad)
                            # 选中主力车
                            log_info("  -> 正在选中主力车...")
                            navigate_to_main_car(hwnd, gamepad)
                            # 等待确认进入详情页
                            if _wait_for_designs_and_paints(hwnd):
                                time.sleep(2.0)  # 等待详情页完全渲染
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
                            _scan_for_subaru_page(hwnd, gamepad)
                            break

                        log_success(f"已选中第 {upgraded_count} 辆车并进入详情页，正在执行加点宏...")
                        remaining_points = action_upgrade_car_skills(hwnd, gamepad)

                        # 触发条件 2: Available Points < 30 → 技能点不足，进入删车
                        if remaining_points is not None and remaining_points < 30:
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
                            _scan_for_subaru_page(hwnd, gamepad)
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
                            _scan_for_subaru_page(hwnd, gamepad)
                            break

                        return_to_garage(hwnd, gamepad)

                    log_success(f"加点阶段完成！共加点 {upgraded_count - 1} 辆车")
                    current_state = STATE_TRASH_CARS
                    log_info("流程转换 [STATE_UPGRADE_CARS] ====> [STATE_TRASH_CARS]")
                    if not loop:
                        log_success("✅ 加点阶段完成（单次模式）")
                        return
                    time.sleep(1.0)

                # --- 3. 清理车库阶段 ---

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
                        time.sleep(2.0)  # 等待自由漫游画面完全就绪
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.0)
                    else:
                        log_warning("  ⚠️ 未检测到自由漫游，仍然尝试按菜单键...")
                        _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.0)

                    current_state = STATE_FARM_POINTS
                    log_info("流程转换 [STATE_TRASH_CARS] ====> [STATE_FARM_POINTS]")
                    if not loop:
                        log_success("✅ 卖车阶段完成（单次模式）")
                        return
                    time.sleep(1.0)

                # --- 4. 刷图阶段 ---

                elif current_state == STATE_FARM_POINTS:
                    log_state_header(STATE_FARM_POINTS, "技能点已耗尽，启动全自动跑图刷点模式")
                    log_warning("状态说明：主控程序正在启动视觉导航与自动跑图模块，进入 EventLab 赚取技能点...")

                    verified_999 = False
                    farm_attempt = 0
                    while not verified_999:
                        farm_attempt += 1
                        try:
                            import farm.skills as module_farm_skills

                            log_info(f"正在启动 module_farm_skills (第 {farm_attempt} 次)...")
                            module_farm_skills.main(gamepad=gamepad)
                            log_success("刷图模块已返回！正在验证技能点...")

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
                            from engine.utils import reset_mss

                            reset_mss()
                        except Exception:
                            pass
                        force_foreground(hwnd)
                        time.sleep(3.0)

                        # farm 模块返回时已在暂停菜单，按 RB 导航到 CARS 标签页
                        log_info("  [验证] 正在导航到 CARS 标签页读取技能点...")
                        detected_points = None
                        cars_found = False

                        from engine.state_detect import get_detector

                        _detector = get_detector()

                        for rb_press in range(8):  # 最多按 8 次 RB 遍历所有标签
                            resized_v, _, _, _, _ = capture_screenshot(hwnd)
                            if resized_v is None:
                                _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)
                                continue

                            detected_state = _detector.detect(resized_v, mode="menu")
                            if detected_state == "CARS":
                                log_success(f"  [验证] 已到达 CARS 标签页！(StateDetector: {detected_state})")
                                cars_found = True
                                # 在 CARS 页读取技能点
                                pts = module_ocr.read_skill_points(resized_v)
                                if pts is not None:
                                    detected_points = pts
                                break

                            log_info(f"  [验证] RB #{rb_press + 1}: 当前状态={detected_state}，继续翻页...")
                            _press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.8)

                        if not cars_found:
                            log_warning("  [验证] 未能导航到 CARS 标签页")

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
                                log_info(f"  重新计算：预计还需 {extra_races} 场比赛")
                                try:
                                    module_farm_skills.clear_race_state()
                                except Exception:
                                    pass
                                time.sleep(2.0)
                        else:
                            log_warning("  ⚠️ OCR 无法读取技能点，假设已达标继续...")
                            verified_999 = True

                    log_success(f"刷图阶段完成！技能点已验证到达 {MAX_SKILL_POINTS}！")

                    if skip_buy:
                        current_state = STATE_UPGRADE_CARS
                        log_info("流程转换 [STATE_FARM_POINTS] =====> [STATE_UPGRADE_CARS] (跳过买车)")
                    else:
                        current_state = STATE_BUY_CARS
                        log_info("流程转换 [STATE_FARM_POINTS] =====> [STATE_BUY_CARS] (新一轮开始！)")
                    if not loop:
                        log_success("✅ 刷点阶段完成（单次模式）")
                        return
                    loop_count += 1
                    time.sleep(2.0)

            except Exception as e:
                log_error(f"状态 {current_state} 执行中发生异常: {e}")
                log_warning("尝试等待 5 秒后重试当前状态...")
                time.sleep(5.0)
                continue

    except BotStoppedError:
        log_warning("==================================================")
        log_warning("     ⛔ Bot 已被用户主动停止")
        log_warning("==================================================")
    except KeyboardInterrupt:
        print()
        log_warning("==================================================")
        log_warning("     ⛔ 主控大脑被用户手动中止 (KeyboardInterrupt)")
        log_warning("     正在安全释放控制器并退出主程序...")
        log_warning("==================================================")
        sys.exit(0)
