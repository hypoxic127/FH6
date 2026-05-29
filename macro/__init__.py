# -*- coding: utf-8 -*-
"""
macro/ 包入口 — 统一导出所有公开函数

本文件仅负责从各子模块收集并导出公共 API，不包含业务逻辑。
主循环实现在 macro/master_loop.py 中。
"""

__all__ = [
    # utils re-exports
    'log_info', 'log_success', 'log_warning', 'log_error',
    # core
    'log_state_header', 'log_step_header',
    'capture_screenshot', 'capture_raw_screenshot',
    'find_game_window', 'force_foreground', '_press_button',
    'MAX_SKILL_POINTS', 'POINTS_PER_CAR', 'CARS_TO_PROCESS',
    'STATE_BUY_CARS', 'STATE_UPGRADE_CARS', 'STATE_TRASH_CARS', 'STATE_FARM_POINTS',
    # navigation
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

from macro.core import (
    CARS_TO_PROCESS,
    MAX_SKILL_POINTS,
    POINTS_PER_CAR,
    STATE_BUY_CARS,
    STATE_FARM_POINTS,
    STATE_TRASH_CARS,
    STATE_UPGRADE_CARS,
    _press_button,
    capture_raw_screenshot,
    capture_screenshot,
    find_game_window,
    force_foreground,
    log_state_header,
    log_step_header,
)
from macro.garage import (
    _navigate_garage_grid,
    _scan_and_delete_cars,
    _wait_for_anna_link,
    _wait_for_cars_text,
    _wait_for_designs_and_paints,
    action_get_in_car,
    action_remove_single_car,
    navigate_to_car_for_removal,
    navigate_to_car_in_garage,
    navigate_to_main_car,
    reset_upgrade_position,
)

# 主循环（从 master_loop 模块导入，保持向后兼容）
from macro.master_loop import run_master_bot_loop  # noqa: F401
from macro.navigation import (
    _scan_for_subaru_page,
    navigate_menu_to_garage,
    return_to_garage,
    safe_exit_to_menu,
)
from macro.purchase import (
    action_buy_single_car,
    dynamic_navigate_to_target,
    is_word_similar,
    navigate_to_impreza_purchase_screen,
)
from macro.upgrade import action_upgrade_car_skills


