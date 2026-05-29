# -*- coding: utf-8 -*-
"""
tests/test_core.py — macro/core.py 常量与配置测试

覆盖：
  - 状态常量完整性
  - CARS_TO_PROCESS 计算公式
  - 日志函数可调用性
"""

import pytest

from macro.core import (
    CARS_TO_PROCESS,
    MAX_SKILL_POINTS,
    POINTS_PER_CAR,
    STATE_BUY_CARS,
    STATE_FARM_POINTS,
    STATE_TRASH_CARS,
    STATE_UPGRADE_CARS,
    log_state_header,
    log_step_header,
)


class TestCoreConstants:
    """核心配置常量测试。"""

    def test_max_skill_points(self) -> None:
        assert MAX_SKILL_POINTS == 999

    def test_points_per_car(self) -> None:
        assert POINTS_PER_CAR == 30

    def test_cars_to_process_formula(self) -> None:
        """CARS_TO_PROCESS 应等于 MAX_SKILL_POINTS // POINTS_PER_CAR。"""
        assert CARS_TO_PROCESS == MAX_SKILL_POINTS // POINTS_PER_CAR
        assert CARS_TO_PROCESS == 33

    def test_state_constants_unique(self) -> None:
        """四个状态常量必须互不相同。"""
        states = {STATE_BUY_CARS, STATE_UPGRADE_CARS,
                  STATE_TRASH_CARS, STATE_FARM_POINTS}
        assert len(states) == 4

    def test_state_constants_are_strings(self) -> None:
        """状态常量应为字符串类型。"""
        for s in [STATE_BUY_CARS, STATE_UPGRADE_CARS,
                  STATE_TRASH_CARS, STATE_FARM_POINTS]:
            assert isinstance(s, str)

    def test_state_names_have_prefix(self) -> None:
        """状态常量应以 STATE_ 开头（命名规范）。"""
        for s in [STATE_BUY_CARS, STATE_UPGRADE_CARS,
                  STATE_TRASH_CARS, STATE_FARM_POINTS]:
            assert s.startswith("STATE_")


class TestLogFunctions:
    """日志函数应可调用且不崩溃。"""

    def test_log_state_header_callable(self) -> None:
        """log_state_header 传入字符串不应崩溃。"""
        log_state_header("TEST_STATE", "测试描述")

    def test_log_step_header_callable(self) -> None:
        """log_step_header 传入字符串不应崩溃。"""
        log_step_header(1, "测试步骤标题")
