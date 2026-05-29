# -*- coding: utf-8 -*-
"""
FH6 AutoBot — 一键环境安装脚本
================================
自动完成以下操作：
1. 安装 Python 依赖 (pip install -r requirements.txt)
2. 下载并解压 Tesseract OCR 到本地 tools/ 目录
3. 检测 ViGEmBus 驱动是否已安装

使用方法:
    python setup.py
"""

import os
import shutil
import subprocess
import sys
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(SCRIPT_DIR, "tools")
TESSERACT_DIR = os.path.join(TOOLS_DIR, "tesseract")
TESSERACT_EXE = os.path.join(TESSERACT_DIR, "tesseract.exe")

# Tesseract 便携版下载地址 (UB Mannheim 官方构建)
TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"


def print_header(title):
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}\n")


def install_pip_deps():
    """安装 Python 依赖"""
    print_header("步骤 1/3：安装 Python 依赖")
    req_file = os.path.join(SCRIPT_DIR, "requirements.txt")
    if not os.path.exists(req_file):
        print("  ❌ 未找到 requirements.txt")
        return False

    print("  正在执行 pip install -r requirements.txt ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req_file],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("  ✅ Python 依赖安装成功！")
        return True
    else:
        print(f"  ❌ 安装失败:\n{result.stderr}")
        return False


def check_tesseract():
    """检测 Tesseract OCR 是否可用"""
    print_header("步骤 2/3：检测 Tesseract OCR")

    # 1. 检查本地 tools/ 目录
    if os.path.exists(TESSERACT_EXE):
        print(f"  ✅ Tesseract 已存在: {TESSERACT_EXE}")
        return True

    # 2. 检查系统 PATH
    try:
        result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"  ✅ Tesseract 已在系统 PATH 中: {version}")
            return True
    except FileNotFoundError:
        pass

    # 3. 检查 Windows 常见安装路径
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            print(f"  ✅ Tesseract 已安装: {path}")
            return True

    # 未找到，提示手动安装
    print("  ⚠️ 未检测到 Tesseract OCR！")
    print()
    print("  请从以下地址下载安装 Tesseract OCR:")
    print("  https://github.com/UB-Mannheim/tesseract/releases")
    print()
    print("  安装时勾选 'Add to PATH' 选项，")
    print("  或安装到默认路径 C:\\Program Files\\Tesseract-OCR\\")
    return False


def check_vigembus():
    """检测 ViGEmBus 驱动是否已安装"""
    print_header("步骤 3/3：检测 ViGEmBus 驱动")

    # 检查 ViGEmBus 驱动文件
    vigem_paths = [
        r"C:\Program Files\ViGEm\ViGEmBus",
        r"C:\Program Files\Nefarius Software Solutions\ViGEmBus",
    ]
    for path in vigem_paths:
        if os.path.exists(path):
            print(f"  ✅ ViGEmBus 驱动已安装: {path}")
            return True

    # 尝试通过 vgamepad 检测
    try:
        import vgamepad as vg
        gamepad = vg.VX360Gamepad()
        del gamepad
        print("  ✅ ViGEmBus 驱动工作正常！（虚拟手柄测试通过）")
        return True
    except Exception:
        pass

    print("  ⚠️ 未检测到 ViGEmBus 驱动！")
    print()
    print("  请从以下地址下载安装 ViGEmBus:")
    print("  https://github.com/ViGEm/ViGEmBus/releases")
    print()
    print("  安装后需重启电脑。")
    return False


def main():
    print("\n" + "🏎️ " * 10)
    print("  FH6 AutoBot — 一键环境安装")
    print("🏎️ " * 10)

    results = {}
    results['pip'] = install_pip_deps()
    results['tesseract'] = check_tesseract()
    results['vigembus'] = check_vigembus()

    # 总结
    print_header("安装结果总结")
    for name, ok in results.items():
        status = "✅ 通过" if ok else "❌ 未通过"
        print(f"  {name:12s}  {status}")

    all_ok = all(results.values())
    print()
    if all_ok:
        print("  🎉 环境配置完成！可以运行 python main_bot.py 启动程序。")
    else:
        print("  ⚠️ 部分组件未安装，请按上方提示手动完成安装。")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
