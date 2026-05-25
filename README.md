# 🏎️ FH6 AutoBot — Forza Horizon 6 全自动刷点挂机工具

> 基于 **计算机视觉 (OpenCV + Tesseract OCR)** 与 **虚拟手柄 (ViGEmBus)** 的
> Forza Horizon 6 全自动技能点无限循环系统。

---

## 📋 功能概述

本工具实现了 Forza Horizon 6 中技能点（Skill Points）的 **全自动闭环刷取**，
覆盖以下四个核心阶段，可无限循环运行：

| 阶段 | 状态常量 | 描述 |
|------|---------|------|
| 1️⃣ 刷技能点 | `STATE_FARM_POINTS` | OCR 扫描当前技能点 → 自动进入 EventLab 跑图刷满 999 |
| 2️⃣ 买车 | `STATE_BUY_CARS` | 五步视觉导航至 Car Collection → 批量购买 33 辆 Subaru Impreza 22B-STI |
| 3️⃣ 加技能点 | `STATE_UPGRADE_CARS` | 进入车库 → 逐辆选择带 NEW 标签的 Impreza → 消耗技能点升级技能树 |
| 4️⃣ 卖车 | `STATE_TRASH_CARS` | 进入车库 → 批量移除已升级完的 Impreza（保留 S2 主力车） |

---

## 🏗️ 项目架构

```
FH6_AutoBot/
├── main_bot.py               # 🚀 主程序入口（交互式菜单选择起始阶段）
├── module_macro.py            # 🔌 向后兼容包装（重新导出 macro/ 下所有函数）
├── macro/                     # 🎮 核心宏引擎包（从 module_macro.py 拆分）
│   ├── __init__.py            #    统一导出 + 主状态机循环 (run_master_bot_loop)
│   ├── core.py                #    基础设施：截图、日志、配置常量
│   ├── navigation.py          #    菜单导航、视觉刹车、返回车库
│   ├── purchase.py            #    5步 Impreza 购买导航 + 购买宏
│   ├── garage.py              #    车库网格操作：选车、删车、主力车导航
│   └── upgrade.py             #    车辆加点宏（含 Cannot Afford 弹窗检测）
├── module_farm_skills.py      # 🏁 EventLab 自动跑图模块（视觉状态机 + RT 加速）
├── module_ocr.py              # 👁️ 计算机视觉模块（OCR / 模板匹配 / 颜色检测）
├── utils.py                   # 🔧 公共工具（日志 / 窗口操作 / 手柄封装 / MSS 截图）
├── templates/                 # 📸 视觉模板图片（菜单标签 / 导航锚点 / 目标车辆）
└── image/options/             # 🖼️ 比赛选项菜单模板
```

---

## ⚙️ 依赖项

| 依赖 | 用途 |
|------|------|
| `opencv-python` (cv2) | 图像处理、模板匹配、颜色空间转换 |
| `pytesseract` | OCR 文字识别（需安装 Tesseract 引擎） |
| `numpy` | 数值计算、图像数组操作 |
| `mss` | 高性能屏幕截图 |
| `vgamepad` | 虚拟 Xbox 360 手柄驱动（需安装 ViGEmBus） |
| `colorama` | 终端彩色日志输出 |

### 前置要求

1. **Python 3.12+**
2. **Tesseract OCR** — [下载安装](https://github.com/tesseract-ocr/tesseract)
3. **ViGEmBus** 驱动 — [下载安装](https://github.com/ViGEm/ViGEmBus/releases)
4. 游戏需运行在 **窗口化** 或 **无边框窗口** 模式
5. 建议分辨率: **2560×1440**（模板基于此分辨率截取）

### 安装依赖

```bash
pip install opencv-python pytesseract numpy mss vgamepad colorama
```

---

## 🚀 使用方法

```bash
python main_bot.py
```

交互式菜单中选择 `[0]` 进入全自动循环，或选择 `[1]-[4]` 从指定阶段开始。

---

## 🔍 核心技术原理

### 视觉状态检测
- **模板匹配 (Template Matching)**: 使用 `cv2.matchTemplate` 对菜单标签、导航锚点进行识别
- **反差检测**: Forza 菜单的特点——当前激活标签的模板匹配分反而较低（因为高亮样式与模板不同）
- **PI 徽章颜色检测**: 通过 HSV 色彩空间检测 PI 徽章颜色区分车辆等级（蓝色 = S2 主力车，橙色 = B 级可删）

### OCR 识别
- **多策略投票**: 对同一区域使用 PSM 8/7/13 三种模式分别识别，取多数一致结果
- **OTSU 自适应阈值**: Available Points 读取使用 OTSU 自适应阈值，避免单位数被误加 0
- **零技能点保底**: 当数字 OCR 全部返回 0 时，使用无限制 OCR 检测 "No Skill Points Available" 文字

### 车库网格导航
- **打字机走位**: 逐列从上到下扫描 3 行 × N 列的车辆网格
- **像素取色判空**: 通过采样下方单元格的亮度和方差判断是否有车
- **NMS 去重**: 对模板匹配结果使用非极大值抑制，避免同一车辆被重复检测
- **Cannot Afford 弹窗检测**: 加点过程中实时检测技能点不足弹窗，自动按 A 关闭并停止购买

---

## 📝 许可证

本项目仅供学习与个人使用。
