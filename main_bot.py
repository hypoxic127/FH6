# -*- coding: utf-8 -*-
"""
FORZA HORIZON 6 AUTOBOT — 主程序启动入口 (main_bot.py)
======================================================
本脚本作为整个自动化系统的入口点，提供交互式菜单让用户选择起始阶段。

四大阶段循环：
  刷技能点 → 买车 → 加技能点 → 卖车 → (循环)

使用方法:
    python main_bot.py

选择 [0] 进入全自动无限循环（默认从刷技能点开始），
选择 [1]-[4] 从指定阶段开始运行。
"""

from macro import (
    STATE_BUY_CARS,
    STATE_FARM_POINTS,
    STATE_TRASH_CARS,
    STATE_UPGRADE_CARS,
    run_master_bot_loop,
)


def show_start_menu():
    """
    显示起始阶段选择菜单。

    用户可以选择从哪个阶段开始运行状态机：
      [0] 自动循环 — 从 STATE_FARM_POINTS 开始完整四阶段循环(在菜单使用)
      [1] 刷技能点 — 进入 EventLab 自动跑图刷满 999 技能点(在菜单使用)
      [2] 买车      — 导航至 Car Collection → 批量购买 Subaru Impreza(在菜单使用)
      [3] 加技能点  — 进入车库 → 逐辆 Impreza 消耗技能点升级技能树(在菜单使用)
      [4] 卖车      — 进入车库 → 批量移除已升级完的 Impreza(在车库并且选中斯巴鲁品牌使用)

    返回:
        str 或 None: 对应的状态常量（如 STATE_FARM_POINTS），
                     返回 None 表示从默认的 FARM_POINTS 开始
    """
    print("\n" + "=" * 50)
    print("   FORZA HORIZON 6 AUTOBOT - 启动菜单")
    print("=" * 50)
    print()
    print("  [1] 🏎️  刷技能点  (STATE_FARM_POINTS) — 在菜单使用")
    print("       OCR 扫描当前技能点 → 自动跑 EventLab 刷满 999")
    print()
    print("  [2] 🛒  买车      (STATE_BUY_CARS) — 在菜单使用")
    print("       导航至 Car Collection → 批量购买 Subaru Impreza")
    print()
    print("  [3] ⚡  加技能点  (STATE_UPGRADE_CARS) — 在菜单使用")
    print("       进入车库 → 逐辆选择 Impreza 并消耗技能点升级")
    print()
    print("  [4] 🗑️  卖车      (STATE_TRASH_CARS) — 在车库 Subaru 页使用")
    print("       进入车库 → 批量移除已升级完的 Impreza")
    print()
    print("  [5] ⏭️  跳过买车  (刷点 → 加点 → 卖车 循环) — 在菜单使用")
    print("       跳过买车阶段，适用于车库已有未加点的车")
    print()
    print("  [0] 🔄  自动循环  (默认：从刷点开始完整循环) — 在菜单使用")
    print()
    print("=" * 50)

    # 建立选项编号到状态常量的映射关系
    state_map = {
        "0": None,  # 默认从 FARM_POINTS 开始
        "1": STATE_FARM_POINTS,
        "2": STATE_BUY_CARS,
        "3": STATE_UPGRADE_CARS,
        "4": STATE_TRASH_CARS,
        "5": STATE_FARM_POINTS,  # 跳过买车，从刷点开始循环
    }

    # 循环等待用户输入有效选项
    while True:
        choice = input("  请选择起始阶段 [0-5] (默认 0): ").strip()
        if choice == "":
            choice = "0"  # 空输入视为选择默认项
        if choice in state_map:
            selected = state_map[choice]
            skip_buy = choice == "5"
            # 状态常量到中文名称的映射（用于提示信息）
            names = {
                None: "自动循环 (从刷点开始)",
                STATE_FARM_POINTS: "刷技能点",
                STATE_BUY_CARS: "买车",
                STATE_UPGRADE_CARS: "加技能点",
                STATE_TRASH_CARS: "卖车",
            }
            if skip_buy:
                print("\n  ✅ 已选择: 跳过买车循环 (刷点 → 加点 → 卖车)")
            else:
                print(f"\n  ✅ 已选择: {names[selected]}")
            print()
            return selected, skip_buy
        else:
            print("  ❌ 无效选择，请输入 0-5 之间的数字。")


def _select_mode() -> str:
    """启动时让用户选择运行模式：WebUI 或控制台。

    返回:
        str: "web" 或 "console"
    """
    print("\n" + "=" * 50)
    print("   FH6-AFK — 启动模式选择")
    print("=" * 50)
    print()
    print("  [1] 🌐  Web UI 控制面板")
    print("       浏览器可视化操作，支持手机远程监控")
    print()
    print("  [2] 💻  终端控制台模式")
    print("       经典命令行交互，适合高级用户")
    print()
    print("=" * 50)

    while True:
        choice: str = input("  请选择模式 [1/2] (默认 1): ").strip()
        if choice in ("", "1"):
            return "web"
        if choice == "2":
            return "console"
        print("  ❌ 无效选择，请输入 1 或 2。")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FH6 AutoBot — 全自动挂机工具")
    parser.add_argument("--web", action="store_true", help="直接启动 Web UI（跳过模式选择）")
    parser.add_argument("--console", action="store_true", help="直接启动控制台（跳过模式选择）")
    parser.add_argument("--port", type=int, default=6800, help="Web UI 端口 (默认 6800)")
    args = parser.parse_args()

    # 优先级：命令行参数 > 交互选择
    if args.web:
        mode = "web"
    elif args.console:
        mode = "console"
    else:
        mode = _select_mode()

    if mode == "web":
        from web.server import start_server

        print(f"\n  🚀 正在启动 Web UI (http://localhost:{args.port}) ...\n")
        start_server(port=args.port)
    else:
        initial_state, skip_buy = show_start_menu()
        run_master_bot_loop(initial_state=initial_state, skip_buy=skip_buy)
