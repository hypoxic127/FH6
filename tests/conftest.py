# -*- coding: utf-8 -*-
"""conftest.py — 全局测试 fixtures 与配置"""

import os
import sys

import pytest

# 将项目根目录加入 sys.path，确保 engine/farm/macro 可被导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 排除旧版测试脚本（仍使用已删除的 module_macro 导入）
collect_ignore_glob = ["tests/test_from_state.py", "tests/test_visualize.py"]


@pytest.fixture
def tmp_race_state(tmp_path: os.PathLike, monkeypatch: pytest.MonkeyPatch):
    """提供临时工作目录，防止测试污染项目根目录的 race_state.json。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path
