# -*- coding: utf-8 -*-
"""
build.py — FH6 AutoBot 一键打包脚本
=====================================
将项目打包为独立可执行文件（无需安装 Python）。

用法:
    python build.py

输出: dist/FH6AutoBot/ 目录，包含 FH6AutoBot.exe 和所有依赖 DLL。

前置条件:
    - Python 3.10+
    - pip install pyinstaller
    - 已安装 requirements.txt 中的所有依赖

注意:
    - Tesseract OCR 不会打包进 exe，用户需自行安装或将 tesseract/ 放在 exe 同目录
    - ViGEmBus 驱动需用户提前安装（系统级驱动无法打包）
"""

import os
import shutil
import subprocess
import sys


def main() -> int:
    """执行 PyInstaller 打包流程。"""
    project_root: str = os.path.dirname(os.path.abspath(__file__))
    spec_file: str = os.path.join(project_root, "FH6AutoBot.spec")
    dist_dir: str = os.path.join(project_root, "dist")
    build_dir: str = os.path.join(project_root, "build")

    print("=" * 50)
    print("  FH6 AutoBot — 打包构建")
    print("=" * 50)
    print()

    # 检查 PyInstaller
    try:
        import PyInstaller  # noqa: F401

        print(f"  ✅ PyInstaller {PyInstaller.__version__} 已就绪")
    except ImportError:
        print("  ❌ PyInstaller 未安装，正在自动安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 清理旧构建
    for d in [build_dir, dist_dir]:
        if os.path.exists(d):
            print(f"  🧹 清理旧目录: {d}")
            shutil.rmtree(d)

    # 执行打包
    print()
    print("  🔨 正在打包...")
    print()

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-m", "PyInstaller", spec_file, "--noconfirm"],
        cwd=project_root,
    )

    if result.returncode != 0:
        print()
        print("  ❌ 打包失败！请检查上方错误输出。")
        return 1

    # 验证输出
    exe_path: str = os.path.join(dist_dir, "FH6AutoBot", "FH6AutoBot.exe")
    if os.path.exists(exe_path):
        size_mb: float = os.path.getsize(exe_path) / (1024 * 1024)
        print()
        print("=" * 50)
        print(f"  ✅ 打包成功！")
        print(f"  📦 输出路径: {os.path.join(dist_dir, 'FH6AutoBot')}")
        print(f"  📄 可执行文件: {exe_path}")
        print(f"  📏 文件大小: {size_mb:.1f} MB")
        print()
        print("  使用方法:")
        print("    1. 将 dist/FH6AutoBot/ 文件夹复制到目标电脑")
        print("    2. 确保目标电脑已安装 Tesseract OCR 和 ViGEmBus")
        print("    3. 双击 FH6AutoBot.exe 即可运行")
        print("=" * 50)
    else:
        print(f"  ⚠️ 未找到输出文件: {exe_path}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
