# -*- coding: utf-8 -*-
"""
farm/ — EventLab 自动刷图包

包含 FarmStateMachine 视觉状态机，负责：
  菜单导航 → EventLab → 选车 → 比赛 → 终点检测 → 重启/退出
"""

from farm.skills import FarmStateMachine, main  # noqa: F401
