# -*- coding: utf-8 -*-
"""
web/state_manager.py — Bot 运行状态聚合器
==========================================
订阅事件总线，维护 bot 的实时运行状态快照。
Web UI 通过此模块获取当前状态，新连接时可回放最近日志。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from engine.event_bus import get_bus


class StateManager:
    """Bot 运行状态聚合器。

    聚合以下状态信息：
    - current_state: 当前阶段 (STATE_FARM_POINTS 等)
    - loop_count: 循环次数
    - skill_points: 当前技能点
    - bot_running: bot 是否正在运行
    - start_time: 启动时间戳
    - recent_logs: 最近 N 条日志（供新连接回放）
    """

    MAX_LOG_HISTORY: int = 500

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._state: dict[str, Any] = {
            "current_state": "IDLE",
            "loop_count": 0,
            "skill_points": 0,
            "cars_bought": 0,
            "cars_upgraded": 0,
            "bot_running": False,
            "start_time": None,
            "uptime_seconds": 0,
        }
        self._logs: deque[dict[str, Any]] = deque(maxlen=self.MAX_LOG_HISTORY)
        self._subscribe()

    def _subscribe(self) -> None:
        """订阅事件总线中的所有相关事件。"""
        bus = get_bus()
        bus.on("log", self._on_log)
        bus.on("state_change", self._on_state_change)
        bus.on("stats_update", self._on_stats_update)
        bus.on("bot_started", self._on_bot_started)
        bus.on("bot_stopped", self._on_bot_stopped)

    def _on_log(self, data: dict[str, Any]) -> None:
        """处理日志事件。"""
        with self._lock:
            self._logs.append(data)

    def _on_state_change(self, data: dict[str, Any]) -> None:
        """处理状态变更事件。"""
        with self._lock:
            if "state" in data:
                self._state["current_state"] = data["state"]
            if "loop_count" in data:
                self._state["loop_count"] = data["loop_count"]

    def _on_stats_update(self, data: dict[str, Any]) -> None:
        """处理统计更新事件。"""
        with self._lock:
            for key in ("skill_points", "cars_bought", "cars_upgraded"):
                if key in data:
                    self._state[key] = data[key]

    def _on_bot_started(self, data: dict[str, Any]) -> None:
        """处理 bot 启动事件。"""
        with self._lock:
            self._state["bot_running"] = True
            self._state["start_time"] = data.get("timestamp", time.time())
            self._state["current_state"] = data.get("initial_state", "STATE_FARM_POINTS")

    def _on_bot_stopped(self, data: dict[str, Any]) -> None:
        """处理 bot 停止事件。"""
        with self._lock:
            self._state["bot_running"] = False

    def get_state(self) -> dict[str, Any]:
        """获取当前状态快照。"""
        with self._lock:
            state = dict(self._state)
            if state["bot_running"] and state["start_time"]:
                state["uptime_seconds"] = int(time.time() - state["start_time"])
            return state

    def get_recent_logs(self, count: int = 200) -> list[dict[str, Any]]:
        """获取最近 N 条日志。"""
        with self._lock:
            return list(self._logs)[-count:]

    def clear_logs(self) -> None:
        """清空日志历史。"""
        with self._lock:
            self._logs.clear()


# ==========================================
# 全局单例
# ==========================================
_manager: StateManager | None = None
_manager_lock: threading.Lock = threading.Lock()


def get_state_manager() -> StateManager:
    """获取全局状态管理器单例。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = StateManager()
    return _manager
