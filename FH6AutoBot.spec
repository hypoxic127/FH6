# -*- mode: python ; coding: utf-8 -*-
"""
FH6AutoBot.spec — PyInstaller 打包配置
=======================================
用法:
    pyinstaller FH6AutoBot.spec

生成: dist/FH6AutoBot/ 目录（--onedir 模式）
包含: 所有 Python 模块，不包含 Tesseract/ViGEmBus（需用户自行安装）
"""

import os
import sys

block_cipher = None

# 项目根目录 — SPECPATH 由 PyInstaller 注入，指向 .spec 文件所在目录
try:
    PROJECT_ROOT = os.path.abspath(SPECPATH)
except NameError:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(sys.argv[0]))

a = Analysis(
    [os.path.join(PROJECT_ROOT, "main_bot.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # vgamepad 的 ViGEmClient.dll 通过 ctypes 加载，PyInstaller 无法自动检测
        # 必须保持原始目录结构: vgamepad/win/vigem/client/x64/ViGEmClient.dll
        (os.path.join(
            os.path.dirname(__import__("vgamepad").__file__),
            "win", "vigem", "client"
        ), os.path.join("vgamepad", "win", "vigem", "client")),
    ],
    hiddenimports=[
        "engine",
        "engine.ocr",
        "engine.utils",
        "engine.runtime",
        "engine.state_detect",
        "farm",
        "farm.skills",
        "macro",
        "macro.core",
        "macro.garage",
        "macro.master_loop",
        "macro.navigation",
        "macro.purchase",
        "macro.upgrade",
        "vgamepad",
        "vgamepad.win",
        "vgamepad.win.vigem_commons",
        "mss",
        "mss.windows",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(PROJECT_ROOT, "hook_utf8.py")],
    excludes=[
        # 不需要打包的模块（减小体积）
        "tkinter",
        "unittest",
        "email",
        "html",
        "http",
        "xml",
        "pydoc",
        "doctest",
        "tools",           # 开发工具不打包
        "tests",           # 测试不打包
        "setup",           # 安装脚本不打包
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # --onedir 模式
    name="FH6AutoBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,            # 需要终端输出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FH6AutoBot",
)
