# -*- coding: utf-8 -*-
"""conftest.py — 全局测试 fixtures 与配置"""

import os
import platform
import sys
import types
from unittest.mock import MagicMock

import pytest

# 将项目根目录加入 sys.path，确保 engine/farm/macro 可被导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==========================================
# 跨平台兼容：在 Linux CI 上 mock Windows-only 依赖
# ==========================================
# 以下模块仅在 Windows 上可用，在 ubuntu-latest CI 上不存在：
#   - ctypes.wintypes  (engine/utils.py 用于窗口操作)
#   - vgamepad         (farm/skills.py, macro/* 用于虚拟手柄)
#   - mss              (engine/utils.py 用于截图)
# 通过在 sys.modules 中预注入 mock，使 import 不报错，
# 测试中只验证纯逻辑函数，不调用硬件 API。

if platform.system() != "Windows":
    # mock ctypes.wintypes
    if "ctypes" not in sys.modules:
        sys.modules["ctypes"] = MagicMock()
    ctypes_mod = sys.modules["ctypes"]
    wintypes_mock = types.ModuleType("ctypes.wintypes")
    wintypes_mock.RECT = MagicMock()
    wintypes_mock.POINT = MagicMock()
    sys.modules["ctypes.wintypes"] = wintypes_mock
    # 确保 ctypes 子属性可用
    if not hasattr(ctypes_mod, "wintypes"):
        ctypes_mod.wintypes = wintypes_mock
    if not hasattr(ctypes_mod, "windll"):
        ctypes_mod.windll = MagicMock()

    # mock vgamepad
    vgamepad_mock = types.ModuleType("vgamepad")
    vgamepad_mock.VX360Gamepad = MagicMock()

    # 创建 XUSB_BUTTON 枚举 mock
    xusb_mock = MagicMock()
    for btn in [
        "XUSB_GAMEPAD_A",
        "XUSB_GAMEPAD_B",
        "XUSB_GAMEPAD_X",
        "XUSB_GAMEPAD_Y",
        "XUSB_GAMEPAD_START",
        "XUSB_GAMEPAD_BACK",
        "XUSB_GAMEPAD_LEFT_SHOULDER",
        "XUSB_GAMEPAD_RIGHT_SHOULDER",
        "XUSB_GAMEPAD_DPAD_UP",
        "XUSB_GAMEPAD_DPAD_DOWN",
        "XUSB_GAMEPAD_DPAD_LEFT",
        "XUSB_GAMEPAD_DPAD_RIGHT",
    ]:
        setattr(xusb_mock, btn, btn)
    vgamepad_mock.XUSB_BUTTON = xusb_mock
    sys.modules["vgamepad"] = vgamepad_mock

    # mock mss
    mss_mock = types.ModuleType("mss")
    mss_mock.MSS = MagicMock()
    sys.modules["mss"] = mss_mock

# 排除旧版测试脚本（仍使用已删除的 module_macro 导入）
collect_ignore_glob = ["tests/test_from_state.py", "tests/test_visualize.py"]


@pytest.fixture
def tmp_race_state(tmp_path: os.PathLike, monkeypatch: pytest.MonkeyPatch):
    """提供临时工作目录，防止测试污染项目根目录的 race_state.json。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path
