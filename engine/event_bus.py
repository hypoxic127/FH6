# -*- coding: utf-8 -*-
"""
engine/event_bus.py — 全局事件总线（发布/订阅）
================================================
线程安全的事件分发中心，用于将 bot 内部事件（日志、状态变更、统计更新）
广播给 Web UI 等外部消费者，而不侵入业务逻辑。

用法::

    from engine.event_bus import get_bus

    # 订阅
    get_bus().on("log", lambda data: print(data["msg"]))

    # 发布
    get_bus().emit("log", {"level": "info", "msg": "hello"})
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class EventBus:
    """线程安全的发布/订阅事件总线。

    支持多个监听器订阅同一事件类型，emit 时按注册顺序同步调用。
    所有操作通过 threading.Lock 保证线程安全。
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def on(self, event: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """注册事件监听器。

        Args:
            event: 事件名称（如 "log", "state_change"）
            callback: 回调函数，接收一个 dict 参数
        """
        with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """移除事件监听器。

        Args:
            event: 事件名称
            callback: 要移除的回调函数
        """
        with self._lock:
            if event in self._listeners:
                try:
                    self._listeners[event].remove(callback)
                except ValueError:
                    pass

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """发布事件，通知所有监听器。

        任何监听器的异常不会中断其他监听器的执行。

        Args:
            event: 事件名称
            data: 事件数据字典，None 时传递空字典
        """
        if data is None:
            data = {}
        data.setdefault("timestamp", time.time())

        with self._lock:
            listeners = list(self._listeners.get(event, []))

        for callback in listeners:
            try:
                callback(data)
            except Exception:
                pass  # 监听器异常不影响其他监听器


# ==========================================
# 全局单例
# ==========================================
_bus: EventBus | None = None
_bus_lock: threading.Lock = threading.Lock()


def get_bus() -> EventBus:
    """获取全局事件总线单例。"""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus
