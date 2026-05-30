[🇬🇧 English](README.md)

# 🏎️ FH6 AutoBot — Forza Horizon 6 全自动刷点挂机工具

[![CI](https://github.com/hypoxic127/FH6/actions/workflows/ci.yml/badge.svg)](https://github.com/hypoxic127/FH6/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-personal%20use-lightgrey)

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
├── main_bot.py                # 🚀 主程序入口（交互式菜单选择起始阶段）
│
├── engine/                    # 🧠 感知引擎层
│   ├── __init__.py            #    包初始化（模块说明 + 向后兼容注释）
│   ├── ocr.py                 #    计算机视觉（OCR / 模板匹配 / 颜色检测）
│   ├── state_detect.py        #    游戏状态检测器（颜色直方图 + OCR 混合）
│   ├── runtime.py             #    PyInstaller 运行时路径兼容层
│   └── utils.py               #    公共工具（日志 / 窗口操作 / 手柄封装 / MSS 截图）
│
├── macro/                     # 🎮 宏操作层
│   ├── __init__.py            #    统一导出（所有公开 API 的入口）
│   ├── core.py                #    基础设施：截图、日志、配置常量
│   ├── master_loop.py         #    主控状态机循环 (run_master_bot_loop)
│   ├── navigation.py          #    菜单导航、视觉刹车、返回车库
│   ├── purchase.py            #    5步 Impreza 购买导航 + 购买宏
│   ├── garage.py              #    车库网格操作：选车、删车、主力车导航
│   └── upgrade.py             #    车辆加点宏（含 Cannot Afford 弹窗检测）
│
├── farm/                      # 🏁 EventLab 刷图
│   ├── __init__.py            #    包初始化
│   └── skills.py              #    视觉状态机（自动跑图 + RT 加速 + 终点检测）
│
├── tools/                     # 🔧 开发者工具（不打包进 exe）
│   ├── debug_cars_roi.py      #    快速截图 + 标注车辆 ROI 区域
│   ├── tool_annotate_roi.py   #    交互式拖拽绘框 ROI 标注工具
│   ├── tool_calibrate_states.py  # 状态检测校准工具（直方图/亮度值采集）
│   └── tool_mask_lines.py     #    遮罩边界线放置工具
│
├── tests/                     # 🧪 单元测试（66 用例）
│   ├── conftest.py            #    Fixtures + 跨平台 mock（Linux CI 兼容）
│   ├── test_ocr.py            #    HSV 常量 / 绿框检测 / 关键词匹配
│   ├── test_farm_skills.py    #    场次计算 / 断点续跑持久化
│   ├── test_purchase.py       #    模糊词匹配（编辑距离 / OCR 容错）
│   ├── test_core.py           #    状态常量 / 公式校验
│   └── test_utils.py          #    日志函数 / MSS 单例
│
├── debug/                     # 🐛 调试输出（截图、校准数据）
│
├── .github/workflows/
│   ├── ci.yml                 # ⚡ GitHub Actions CI（Ruff lint + pytest）
│   └── release.yml            # 📦 自动发布（PyInstaller 构建 + GitHub Release）
│
├── build.py                   # 🔨 一键 PyInstaller 打包脚本
├── FH6AutoBot.spec            # 📋 PyInstaller 打包配置
├── hook_utf8.py               # 🔤 PyInstaller 运行时钩子（Windows UTF-8 控制台修复）
├── setup.py                   # ⚙️ 一键环境安装脚本
├── requirements.txt           # 📋 Python 依赖列表
├── ruff.toml                  # 🔍 Ruff 代码检查配置
├── pytest.ini                 # 🧪 Pytest 配置
├── race_state.json            # 💾 跑图断点持久化文件（自动生成）
└── play_archive.txt           # 📜 历史运行日志存档
```

---

## ⚙️ 依赖项

| 依赖 | 用途 |
|------|------|
| `opencv-python` ≥ 4.8.0 | 图像处理、模板匹配、颜色空间转换 |
| `pytesseract` ≥ 0.3.10 | OCR 文字识别（需安装 Tesseract 引擎） |
| `numpy` ≥ 1.24.0 | 数值计算、图像数组操作 |
| `mss` ≥ 9.0.0 | 高性能屏幕截图 |
| `vgamepad` ≥ 0.1.0 | 虚拟 Xbox 360 手柄驱动（需安装 ViGEmBus） |
| `colorama` ≥ 0.4.6 | 终端彩色日志输出 |

### 前置要求

#### 🖥️ 软件环境
1. **Python 3.10+**
2. **Tesseract OCR** — [下载安装](https://github.com/UB-Mannheim/tesseract/releases)（安装时勾选 Add to PATH）
3. **ViGEmBus** 驱动 — [下载安装](https://github.com/ViGEm/ViGEmBus/releases)（安装后需重启）
4. 游戏需运行在 **窗口化** 或 **无边框窗口** 模式
5. 建议分辨率: **2560×1440**（视觉检测基于此分辨率校准）

#### 🎮 游戏内准备
1. **购买主力车**: 1998 Subaru Impreza 22B-STI Version
2. **安装 S2 级改装**: 对该车安装任意 S2 级改装方案（PI 徽章显示蓝色）
3. **收藏蓝图**: 搜索并收藏蓝图代码 `890169683`（用于 EventLab 自动跑图刷技能点）

> ⚠️ 主力车的 S2 蓝色 PI 徽章是程序区分"保留车"与"可删除车"的关键依据，请务必完成改装。

### 一键安装

```bash
python setup.py
```

自动完成：安装 Python 依赖 → 检测 Tesseract OCR → 检测 ViGEmBus 驱动

---

## 🚀 使用方法

### 源码运行

```bash
python main_bot.py
```

交互式菜单提供以下选项：

| 选项 | 说明 | 使用场景 |
|------|------|---------|
| `[0]` | 🔄 自动循环（完整四阶段闭环） | 在主菜单使用 |
| `[1]` | 🏎️ 刷技能点 | 在主菜单使用 |
| `[2]` | 🛒 买车 | 在主菜单使用 |
| `[3]` | ⚡ 加技能点 | 在主菜单使用 |
| `[4]` | 🗑️ 卖车 | 在车库并选中斯巴鲁品牌时使用 |
| `[5]` | ⏭️ 跳过买车（刷点 → 加点 → 卖车循环） | 在主菜单使用，车库已有未加点的车 |

### 打包为独立可执行文件

```bash
python build.py
```

生成 `dist/FH6AutoBot/FH6AutoBot.exe` — 无需安装 Python 即可运行的便携版。目标电脑仍需安装 Tesseract OCR 和 ViGEmBus 驱动。

### 自动发布

推送版本标签（如 `v1.0.0`）会触发 GitHub Actions Release 工作流，自动在 `windows-latest` 上构建 exe 并发布 ZIP 压缩包到 GitHub Release。

---

## 🧪 测试与 CI

### 本地运行测试

```bash
# 安装测试依赖
pip install pytest ruff

# 运行单元测试（自动跳过硬件依赖测试）
python -m pytest

# 代码检查
python -m ruff check .
python -m ruff format --check .
```

### GitHub Actions

每次 `push` 和 `pull_request` 到 `main` 分支会自动触发 CI 流水线：

| Job | 内容 |
|-----|------|
| **Lint** | Ruff 代码检查 + 格式校验 |
| **Test** | pytest 运行 66 个单元测试（ubuntu-latest，自动 mock Windows 依赖） |

---

## 🔍 核心技术原理

### 视觉状态检测
- **颜色直方图 + OCR 混合检测**: StateDetector 融合颜色分布特征与 OCR 文字识别，判定当前游戏 UI 状态
- **反差检测**: Forza 菜单的特点——当前激活标签的模板匹配分反而较低（因为高亮样式与模板不同）
- **PI 徽章颜色检测**: 通过 HSV 色彩空间检测 PI 徽章颜色区分车辆等级（蓝色 = S2 主力车，橙色 = B 级可删）

### OCR 识别
- **多策略投票**: 对同一区域使用 PSM 8/7/13 三种模式分别识别，取多数一致结果
- **OTSU 自适应阈值**: Available Points 读取使用 OTSU 自适应阈值，避免单位数被误加 0
- **零技能点保底**: 当数字 OCR 全部返回 0 时，使用无限制 OCR 检测 "No Skill Points Available" 文字

### 车库网格导航
- **打字机走位**: 逐列从上到下扫描 3 行 × N 列的车辆网格
- **三重校验锁定**: OCR 车名关键词 (2/3) + NEW 黄色标签 + LEGENDARY 橙色稀有度
- **NMS 去重**: 对模板匹配结果使用非极大值抑制，避免同一车辆被重复检测
- **Cannot Afford 弹窗检测**: 加点过程中实时检测技能点不足弹窗，自动按 A 关闭并停止购买

### 构建与打包
- **PyInstaller One-Dir 模式**: `build.py` + `FH6AutoBot.spec` 将所有 Python 模块打包为便携目录；vgamepad 的 `ViGEmClient.dll` 作为数据文件显式包含
- **运行时路径层**: `engine/runtime.py` 为开发模式和打包（exe）环境提供统一的路径解析
- **UTF-8 控制台修复**: `hook_utf8.py` 运行时钩子确保中文日志在默认非 UTF-8 的 Windows 控制台上正确显示

---

## 📝 许可证

本项目仅供学习与个人使用。
