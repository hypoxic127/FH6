# -*- coding: utf-8 -*-
"""
engine/runtime.py — PyInstaller 运行时路径兼容层
==================================================
PyInstaller 打包后，`__file__` 指向临时解压目录（`sys._MEIPASS`），
不是用户的工作目录。本模块提供统一的路径解析，确保：

  - 代码资源（只读）：从打包目录或项目源码目录加载
  - 用户数据（读写）：始终使用 exe 所在目录（非临时目录）
"""

import os
import sys


def get_base_dir() -> str:
    """获取项目根目录（代码资源所在位置）。

    PyInstaller 打包后返回 sys._MEIPASS（临时解压目录），
    开发模式下返回项目根目录。

    Returns:
        项目根目录的绝对路径
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后
        return sys._MEIPASS  # type: ignore[attr-defined]
    # 开发模式: engine/runtime.py -> 上级目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_user_dir() -> str:
    """获取用户数据目录（可读写，用于 race_state.json 等）。

    PyInstaller 打包后返回 exe 所在目录，
    开发模式下返回项目根目录。

    Returns:
        用户数据目录的绝对路径
    """
    if getattr(sys, "frozen", False):
        # exe 所在目录（用户可以在此放配置文件）
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen() -> bool:
    """判断是否在 PyInstaller 打包环境中运行。

    Returns:
        True 表示运行在打包的 exe 中
    """
    return getattr(sys, "frozen", False)
