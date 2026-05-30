# 🏎️ FH6 AutoBot — Forza Horizon 6 Fully Automated AFK Farming Tool

[![CI](https://github.com/hypoxic127/FH6/actions/workflows/ci.yml/badge.svg)](https://github.com/hypoxic127/FH6/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-personal%20use-lightgrey)

> A fully automated, infinite-loop Skill Points farming system for
> Forza Horizon 6, powered by **Computer Vision (OpenCV + Tesseract OCR)**
> and **Virtual Gamepad (ViGEmBus)**.
>
> 基于 **计算机视觉 (OpenCV + Tesseract OCR)** 与 **虚拟手柄 (ViGEmBus)** 的
> Forza Horizon 6 全自动技能点无限循环系统。

---

## 📋 Feature Overview / 功能概述

This tool implements a **fully automated closed-loop Skill Points farm** covering four core stages in an infinite loop:

本工具实现了技能点的 **全自动闭环刷取**，覆盖以下四个核心阶段，可无限循环运行：

| Stage | State Constant | EN | 中文 |
|-------|---------------|-----|------|
| 1️⃣ | `STATE_FARM_POINTS` | OCR scans skill points → auto-enters EventLab to farm up to 999 | OCR 扫描技能点 → 自动进入 EventLab 刷满 999 |
| 2️⃣ | `STATE_BUY_CARS` | Five-step visual navigation → batch-purchase 33 Subaru Impreza 22B-STIs | 五步视觉导航 → 批量购买 33 辆 Subaru Impreza |
| 3️⃣ | `STATE_UPGRADE_CARS` | Select each Impreza with NEW tag → spend skill points | 逐辆选择 NEW 标签 Impreza → 消耗技能点升级 |
| 4️⃣ | `STATE_TRASH_CARS` | Batch-remove upgraded Imprezas (keeping S2 main car) | 批量移除已升级 Impreza（保留 S2 主力车） |

---

## 🏗️ Project Architecture / 项目架构

```
FH6_AutoBot/
├── main_bot.py                # 🚀 Entry point / 主程序入口
│
├── engine/                    # 🧠 Perception Engine / 感知引擎层
│   ├── ocr.py                 #    Computer vision (OCR + color detection)
│   ├── state_detect.py        #    Game state detector (histogram + OCR hybrid)
│   ├── runtime.py             #    PyInstaller runtime path resolution
│   └── utils.py               #    Logging / window ops / gamepad / MSS capture
│
├── macro/                     # 🎮 Macro Operations / 宏操作层
│   ├── core.py                #    Infrastructure: screenshots, logging, constants
│   ├── master_loop.py         #    Master state machine (run_master_bot_loop)
│   ├── navigation.py          #    Menu navigation, visual braking, return-to-garage
│   ├── purchase.py            #    5-step Impreza purchase navigation
│   ├── garage.py              #    Garage grid: select / delete / main car nav
│   └── upgrade.py             #    Car upgrade macro (Cannot Afford detection)
│
├── farm/                      # 🏁 EventLab Farming / 刷图层
│   └── skills.py              #    Visual state machine (auto-drive + finish detection)
│
├── packaging/                 # 📦 Build & Packaging / 打包构建
│   ├── build.py               #    One-click PyInstaller build script
│   ├── FH6AutoBot.spec        #    PyInstaller spec (--onefile mode)
│   └── hook_utf8.py           #    Runtime hook (Windows UTF-8 console fix)
│
├── tools/                     # 🔧 Dev Utilities / 开发工具 (not packaged)
├── tests/                     # 🧪 Unit Tests / 单元测试 (95 cases)
│
├── .github/workflows/
│   ├── ci.yml                 # ⚡ CI (Ruff lint + pytest)
│   └── release.yml            # 📦 Release (PyInstaller → GitHub Release)
│
├── setup.py                   # ⚙️ One-click environment setup
├── requirements.txt           # 📋 Python dependencies
├── ruff.toml                  # 🔍 Ruff linter config
└── pytest.ini                 # 🧪 Pytest config
```

---

## ⚙️ Dependencies / 依赖项

| Dependency | Purpose / 用途 |
|-----------|----------------|
| `opencv-python-headless` ≥ 4.8.0 | Image processing, color detection / 图像处理、颜色检测 |
| `pytesseract` ≥ 0.3.10 | OCR text recognition / OCR 文字识别 |
| `numpy` ≥ 1.24.0 | Numerical computing / 数值计算 |
| `mss` ≥ 9.0.0 | High-performance screen capture / 高性能截图 |
| `vgamepad` ≥ 0.1.0 | Virtual Xbox 360 gamepad / 虚拟手柄 (Windows only) |
| `colorama` ≥ 0.4.6 | Colored terminal output / 终端彩色日志 |

### Prerequisites / 前置要求

#### 🖥️ Software / 软件环境
1. **Python 3.10+**
2. **Tesseract OCR** — [Download / 下载](https://github.com/UB-Mannheim/tesseract/releases) (check "Add to PATH" / 安装时勾选 Add to PATH)
3. **ViGEmBus** driver — [Download / 下载](https://github.com/ViGEm/ViGEmBus/releases) (restart required / 安装后需重启)
4. Game must run in **Windowed** or **Borderless Windowed** mode / 游戏需运行在 **窗口化** 或 **无边框窗口** 模式
5. Recommended resolution / 建议分辨率: **2560×1440**

#### 🎮 In-Game Preparation / 游戏内准备
1. **Purchase main car / 购买主力车**: 1998 Subaru Impreza 22B-STI Version
2. **Install S2 tune / 安装 S2 级改装**: Apply any S2-class tune (PI badge = blue / PI 徽章显示蓝色)
3. **Favorite blueprint / 收藏蓝图**: Share code `890169683`

> ⚠️ The S2 blue PI badge is the key indicator to distinguish "keep" vs "deletable" cars.
>
> ⚠️ 主力车的 S2 蓝色 PI 徽章是程序区分"保留车"与"可删除车"的关键依据。

### One-Click Install / 一键安装

```bash
python setup.py
```

---

## 🚀 Usage / 使用方法

### Run from Source / 源码运行

```bash
python main_bot.py
```

| Option | EN | 中文 | When to Use / 使用场景 |
|--------|-----|------|----------------------|
| `[0]` | 🔄 Auto loop (full cycle) | 自动循环 | Main menu / 主菜单 |
| `[1]` | 🏎️ Farm Skill Points | 刷技能点 | Main menu / 主菜单 |
| `[2]` | 🛒 Buy Cars | 买车 | Main menu / 主菜单 |
| `[3]` | ⚡ Upgrade Cars | 加技能点 | Main menu / 主菜单 |
| `[4]` | 🗑️ Sell Cars | 卖车 | Garage (Subaru selected) / 车库斯巴鲁页 |
| `[5]` | ⏭️ Skip Buy | 跳过买车 | Main menu / 车库已有未加点的车 |

### Build Executable / 打包

```bash
python packaging/build.py
```

Produces `dist/FH6AutoBot.exe` — portable, no Python required. Tesseract & ViGEmBus still needed.

生成 `dist/FH6AutoBot.exe` — 无需 Python 即可运行，仍需 Tesseract OCR 和 ViGEmBus。

### Automated Release / 自动发布

Push a version tag (e.g. `v1.2.0`) → GitHub Actions builds exe → publishes to GitHub Release.

推送版本标签 → 自动构建 → 发布到 GitHub Release。

---

## 🧪 Testing & CI / 测试与 CI

```bash
pip install pytest ruff

python -m pytest                    # Run tests / 运行测试
python -m ruff check .              # Lint
python -m ruff format --check .     # Format check
```

| CI Job | Description / 描述 |
|--------|-------------------|
| **Lint** | Ruff check + format validation / 代码检查 + 格式校验 |
| **Test** | pytest 95 tests on ubuntu-latest / 95 个测试用例 |

---

## 🔍 Core Technical Principles / 核心技术原理

### Visual State Detection / 视觉状态检测
- **Histogram + OCR Hybrid** — StateDetector combines color distribution features with OCR / 颜色直方图 + OCR 混合检测
- **PI Badge Color Detection** — HSV color space: blue = S2 main car, orange = deletable / PI 徽章颜色区分车辆等级

### OCR Recognition / OCR 识别
- **Multi-PSM Voting** — PSM 8/7/13 modes, majority-consistent result wins / 多策略投票取多数一致结果
- **OTSU Adaptive Thresholding** — Prevents single-digit zero-padding errors / 自适应阈值避免误加 0
- **Zero Skill Points Fallback** — Detects "No Skill Points Available" text / 零技能点保底检测

### Garage Grid Navigation / 车库网格导航
- **Typewriter Traversal** — Column by column, top to bottom (3×N grid) / 打字机走位逐列扫描
- **Triple Verification** — OCR keywords (2/3) + NEW yellow tag + LEGENDARY orange rarity / 三重校验锁定
- **Cannot Afford Detection** — Auto-dismisses popup, stops purchasing / 弹窗检测自动关闭

### Build & Packaging / 构建与打包
- **PyInstaller --onefile** — Single 44MB exe / 单文件 44MB 可执行程序
- **Runtime Path Layer** — `engine/runtime.py` unified path resolution / 统一路径解析
- **UTF-8 Console Fix** — `hook_utf8.py` for Chinese log output on Windows / 中文日志控制台修复

---

## 📝 License / 许可证

This project is for learning and personal use only.

本项目仅供学习与个人使用。
