# -*- coding: utf-8 -*-
"""
PyInstaller 运行时钩子 — 修复 Windows 控制台 UTF-8 编码
======================================================
PyInstaller 打包的 exe 在某些 Windows 系统上默认使用 cp1252 编码，
导致中文字符打印时抛出 UnicodeEncodeError。

本钩子在主脚本执行前设置 UTF-8 编码环境。
"""

import os
import sys

# 确保标准输出/错误流使用 UTF-8
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
