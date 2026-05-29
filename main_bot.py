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
    }

    # 循环等待用户输入有效选项
    while True:
        choice = input("  请选择起始阶段 [0-4] (默认 0): ").strip()
        if choice == "":
            choice = "0"  # 空输入视为选择默认项
        if choice in state_map:
            selected = state_map[choice]
            # 状态常量到中文名称的映射（用于提示信息）
            names = {
                None: "自动循环 (从刷点开始)",
                STATE_FARM_POINTS: "刷技能点",
                STATE_BUY_CARS: "买车",
                STATE_UPGRADE_CARS: "加技能点",
                STATE_TRASH_CARS: "卖车",
            }
            print(f"\n  ✅ 已选择: {names[selected]}")
            print()
            return selected
        else:
            print("  ❌ 无效选择，请输入 0-4 之间的数字。")


if __name__ == "__main__":
    # 显示菜单并获取用户选择的起始状态
    initial_state = show_start_menu()
    # 启动全自动主控状态机无限闭环
    # run_master_bot_loop 会按 刷点→买车→加点→卖车 的顺序无限循环
    run_master_bot_loop(initial_state=initial_state)
