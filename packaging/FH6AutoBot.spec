# -*- mode: python ; coding: utf-8 -*-
"""
FH6AutoBot.spec — PyInstaller 打包配置（优化版）
================================================
用法:
    pyinstaller packaging/FH6AutoBot.spec

生成: dist/FH6AutoBot.exe（--onefile 单文件模式）

优化策略:
    - 排除 PIL/Pillow（项目只用 OpenCV，不需要 Pillow）
    - 排除 OpenCV 视频编解码（ffmpeg DLL，不需要视频功能）
    - 排除 SSL/加密库（桌面自动化无网络需求）
    - 排除 scipy openblas（项目不需要高级线性代数）
    - 排除 pytest/setuptools 等开发工具
"""

import os
import importlib.util
import sys

block_cipher = None

# 项目根目录 — SPECPATH 指向 packaging/，需上溯一级到项目根
try:
    PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
    PACKAGING_DIR = os.path.abspath(SPECPATH)
except NameError:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
    PACKAGING_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

# 定位 vgamepad 包路径（不触发 __init__.py，避免 ViGEmBus 驱动连接）
_vgamepad_spec = importlib.util.find_spec("vgamepad")
_vgamepad_dir = os.path.dirname(_vgamepad_spec.origin)

a = Analysis(
    [os.path.join(PROJECT_ROOT, "main_bot.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # vgamepad 的 ViGEmClient.dll 通过 ctypes 加载，PyInstaller 无法自动检测
        # 必须保持原始目录结构: vgamepad/win/vigem/client/x64/ViGEmClient.dll
        (os.path.join(
            _vgamepad_dir,
            "win", "vigem", "client"
        ), os.path.join("vgamepad", "win", "vigem", "client")),
        # Web UI 静态文件
        (os.path.join(PROJECT_ROOT, "web", "static"), os.path.join("web", "static")),
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
        "web",
        "web.server",
        "web.state_manager",
        "engine.event_bus",
        "flask",
        "flask_socketio",
        "engineio",
        "socketio",
        "simple_websocket",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(PACKAGING_DIR, "hook_utf8.py")],
    excludes=[
        # === 不需要的 PIL 格式插件（通过 binary filter 移除大文件）===
        # PIL 核心 (PIL.Image) 需保留 — pytesseract 依赖它
        # 大格式插件 (_avif, _webp) 在下方 _exclude_binaries 中移除

        # === 不需要的标准库模块 ===
        "tkinter",             # GUI 框架
        "unittest",            # 测试框架
        "email",               # 邮件处理
        "html",                # HTML 解析
        "http",                # HTTP 客户端/服务器
        "xml",                 # XML 解析
        "xmlrpc",              # XML-RPC
        "pydoc",               # 文档生成
        "doctest",             # 文档测试
        "ftplib",              # FTP 客户端
        "imaplib",             # IMAP 客户端
        "smtplib",             # SMTP 客户端
        "poplib",              # POP3 客户端
        "nntplib",             # NNTP 客户端
        "telnetlib",           # Telnet 客户端
        "ssl",                 # SSL/TLS（无网络需求）
        "multiprocessing",     # 多进程（项目单进程）
        "concurrent",          # 并发框架
        "asyncio",             # 异步IO
        "curses",              # 终端 UI

        # === 不需要的开发工具 ===
        "setuptools",
        "pip",
        "pkg_resources",
        "pytest",
        "ruff",
        "tools",               # 本项目开发工具
        "tests",               # 本项目测试
        "setup",               # 本项目安装脚本
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# === 后处理: 移除不需要的大文件 ===
# 从 binaries 列表中排除 OpenCV ffmpeg DLL 和 OpenBLAS（共节省 ~47 MB）
_exclude_binaries = {
    "opencv_videoio_ffmpeg",     # 27 MB — 视频编解码，不需要
    "libcrypto",                 # 5 MB  — OpenSSL 加密库，不需要
    "libssl",                    # 0.8 MB — OpenSSL，不需要
    "_avif",                     # 7.5 MB — AVIF 图片格式（PIL），不需要
    "_webp",                     # 0.4 MB — WebP 格式（PIL），不需要
}

a.binaries = [
    (name, path, typecode)
    for name, path, typecode in a.binaries
    if not any(excl in name for excl in _exclude_binaries)
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
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
