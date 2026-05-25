# -*- coding: utf-8 -*-
"""
module_macro.py — 向后兼容包装
==================================
所有功能已拆分到 macro/ 包目录下：
  - macro/core.py       基础设施（截图、日志、配置常量）
  - macro/navigation.py 菜单导航、视觉刹车、返回车库
  - macro/purchase.py   5步购买导航 + 购买宏
  - macro/garage.py     车库网格操作（选车、删车、主力车导航）
  - macro/upgrade.py    车辆加点宏

本文件仅做统一导出，使旧的 `import module_macro` 继续工作。
"""

# 导出所有公开函数和常量（保持向后兼容）
from macro import *
