# -*- coding: utf-8 -*-
"""
web/server.py — Flask + SocketIO Web 控制面板服务器
====================================================
提供实时日志推送、状态监控和远程控制功能。

启动方式::

    python main_bot.py --web          # 启动 Web UI 模式
    python main_bot.py --web --port 9000  # 自定义端口
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Any

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from engine.event_bus import get_bus
from engine.runtime import get_base_dir
from web.state_manager import get_state_manager

# 抑制 Flask/Werkzeug 的请求日志（否则刷屏）
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# ==========================================
# Flask 应用 + SocketIO
# ==========================================
_static_dir: str = os.path.join(get_base_dir(), "web", "static")
_app: Flask = Flask(
    __name__,
    static_folder=_static_dir,
    static_url_path="/static",
)
_app.config["SECRET_KEY"] = "fh6-autobot-web-ui"

_socketio: SocketIO = SocketIO(
    _app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# Bot 线程引用
_bot_thread: threading.Thread | None = None
_bot_stop_event: threading.Event = threading.Event()


# ==========================================
# HTTP 路由
# ==========================================
@_app.route("/")
def index() -> str:
    """返回主页 HTML。"""
    return send_from_directory(_app.static_folder, "index.html")


# ==========================================
# WebSocket 事件处理
# ==========================================
@_socketio.on("connect")
def handle_connect() -> None:
    """客户端连接时推送当前状态和最近日志。"""
    manager = get_state_manager()
    _socketio.emit("state_update", manager.get_state())
    for log_entry in manager.get_recent_logs():
        _socketio.emit("log", log_entry)


@_socketio.on("start_bot")
def handle_start_bot(data: dict[str, Any] | None = None) -> None:
    """启动 bot 线程。"""
    global _bot_thread
    if _bot_thread and _bot_thread.is_alive():
        _socketio.emit("error", {"msg": "Bot 已在运行中"})
        return

    if data is None:
        data = {}

    initial_state = data.get("initial_state")
    skip_buy = data.get("skip_buy", False)

    _bot_stop_event.clear()

    def _run_bot() -> None:
        """在子线程中运行 bot 主循环。"""
        try:
            bus = get_bus()
            bus.emit("bot_started", {"initial_state": initial_state or "STATE_FARM_POINTS"})

            from macro import run_master_bot_loop

            run_master_bot_loop(initial_state=initial_state, skip_buy=skip_buy)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            get_bus().emit("log", {"level": "error", "msg": f"Bot 异常退出: {e}"})
        finally:
            get_bus().emit("bot_stopped", {})

    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="bot-worker")
    _bot_thread.start()
    _socketio.emit("bot_status", {"running": True})


@_socketio.on("stop_bot")
def handle_stop_bot() -> None:
    """停止 bot 线程（通过设置停止标志）。"""
    _bot_stop_event.set()
    get_bus().emit("bot_stopped", {})
    _socketio.emit("bot_status", {"running": False})
    get_bus().emit("log", {"level": "warning", "msg": "⛔ Bot 已被 Web UI 手动停止"})


@_socketio.on("get_state")
def handle_get_state() -> None:
    """客户端请求最新状态。"""
    _socketio.emit("state_update", get_state_manager().get_state())


# ==========================================
# 事件总线 → WebSocket 广播桥接
# ==========================================
def _bridge_events() -> None:
    """将事件总线的事件桥接到 WebSocket 广播。"""
    bus = get_bus()

    def _on_log(data: dict[str, Any]) -> None:
        _socketio.emit("log", data)

    def _on_state_change(data: dict[str, Any]) -> None:
        _socketio.emit("state_update", get_state_manager().get_state())

    def _on_bot_started(data: dict[str, Any]) -> None:
        _socketio.emit("bot_status", {"running": True})
        _socketio.emit("state_update", get_state_manager().get_state())

    def _on_bot_stopped(data: dict[str, Any]) -> None:
        _socketio.emit("bot_status", {"running": False})
        _socketio.emit("state_update", get_state_manager().get_state())

    bus.on("log", _on_log)
    bus.on("state_change", _on_state_change)
    bus.on("bot_started", _on_bot_started)
    bus.on("bot_stopped", _on_bot_stopped)


# ==========================================
# 公共 API
# ==========================================
def _get_local_ip() -> str:
    """获取本机局域网 IP 地址。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_server(port: int = 6800) -> None:
    """启动 Web UI 服务器。

    Args:
        port: HTTP 监听端口，默认 6800
    """
    # 初始化状态管理器（订阅事件总线）
    get_state_manager()
    # 桥接事件到 WebSocket
    _bridge_events()

    local_ip = _get_local_ip()
    from engine.utils import safe_print

    safe_print("")
    safe_print("=" * 55)
    safe_print("   🌐 FH6 AutoBot — Web UI 控制面板")
    safe_print("=" * 55)
    safe_print("")
    safe_print(f"   本机访问:   http://localhost:{port}")
    safe_print(f"   局域网访问: http://{local_ip}:{port}")
    safe_print("   手机扫码或输入上方地址即可远程监控")
    safe_print("")
    safe_print("=" * 55)
    safe_print("")

    _socketio.run(_app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
