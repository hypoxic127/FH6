# -*- coding: utf-8 -*-
"""
tests/test_farm_skills.py — farm/skills.py 单元测试

覆盖：
  - get_matches_needed()  比赛场次计算
  - save / load / clear race state  断点续跑持久化
"""

import json
import os

import pytest

from farm.skills import (
    RACE_STATE_FILE,
    clear_race_state,
    get_matches_needed,
    load_race_state,
    save_race_state,
)

# ==========================================
# get_matches_needed()
# ==========================================


class TestGetMatchesNeeded:
    """比赛场次计算器测试。"""

    def test_zero_points_needs_100_matches(self) -> None:
        """0 点 → 需要 ceil(999/10)=100 场。"""
        assert get_matches_needed(0) == 100

    def test_max_points_needs_zero(self) -> None:
        """999 点 → 不需要跑了。"""
        assert get_matches_needed(999) == 0

    def test_over_max_returns_zero(self) -> None:
        """超过 999 不能返回负数。"""
        assert get_matches_needed(1500) == 0

    def test_partial_points(self) -> None:
        """500 点 → 需要 ceil(499/10) = 50 场。"""
        assert get_matches_needed(500) == 50

    def test_one_match_boundary(self) -> None:
        """990 点 → 需要 1 场 (差 9 点, 每场 10 点)。"""
        assert get_matches_needed(990) == 1

    def test_exact_boundary(self) -> None:
        """989 点 → 需要 1 场。"""
        assert get_matches_needed(989) == 1

    def test_negative_points_clamps(self) -> None:
        """负数技能点也应正常返回（防御性编程）。"""
        result = get_matches_needed(-10)
        assert result >= 100  # 至少 100 场


# ==========================================
# Race State Persistence
# ==========================================


class TestRaceStatePersistence:
    """断点续跑 JSON 持久化测试。"""

    def test_save_creates_file(self, tmp_race_state) -> None:
        """save_race_state 应创建 JSON 文件。"""
        save_race_state(50, 10)
        assert os.path.exists(RACE_STATE_FILE)

    def test_save_load_roundtrip(self, tmp_race_state) -> None:
        """保存后加载应返回相同的数据。"""
        save_race_state(42, 7)
        result = load_race_state()
        assert result is not None
        matches_needed, matches_completed, last_updated = result
        assert matches_needed == 42
        assert matches_completed == 7
        assert isinstance(last_updated, str)

    def test_load_returns_none_when_no_file(self, tmp_race_state) -> None:
        """无文件时 load 应返回 None。"""
        assert load_race_state() is None

    def test_load_returns_none_when_zero_matches(self, tmp_race_state) -> None:
        """matches_needed=0 时 load 应返回 None（已完成）。"""
        save_race_state(0, 100)
        assert load_race_state() is None

    def test_clear_removes_file(self, tmp_race_state) -> None:
        """clear 应删除文件。"""
        save_race_state(10, 5)
        assert os.path.exists(RACE_STATE_FILE)
        clear_race_state()
        assert not os.path.exists(RACE_STATE_FILE)

    def test_clear_noop_when_no_file(self, tmp_race_state) -> None:
        """无文件时 clear 不应报错。"""
        clear_race_state()  # 不应抛异常

    def test_load_handles_corrupt_json(self, tmp_race_state) -> None:
        """损坏的 JSON 不应导致崩溃。"""
        with open(RACE_STATE_FILE, "w") as f:
            f.write("{invalid json!!!")
        assert load_race_state() is None

    def test_save_json_structure(self, tmp_race_state) -> None:
        """验证 JSON 文件内部结构符合预期。"""
        save_race_state(30, 20)
        with open(RACE_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "matches_needed" in data
        assert "matches_completed" in data
        assert "last_updated" in data
        assert data["matches_needed"] == 30
        assert data["matches_completed"] == 20
