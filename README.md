[🇨🇳 中文版](README_zh-CN.md)

# 🏎️ FH6 AutoBot — Forza Horizon 6 Fully Automated AFK Farming Tool

[![CI](https://github.com/hypoxic127/FH6/actions/workflows/ci.yml/badge.svg)](https://github.com/hypoxic127/FH6/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-personal%20use-lightgrey)

> A fully automated, infinite-loop Skill Points farming system for
> Forza Horizon 6, powered by **Computer Vision (OpenCV + Tesseract OCR)**
> and **Virtual Gamepad (ViGEmBus)**.

---

## 📋 Feature Overview

This tool implements a **fully automated closed-loop Skill Points farm** in
Forza Horizon 6, covering the following four core stages in an infinite loop:

| Stage | State Constant | Description |
|-------|---------------|-------------|
| 1️⃣ Farm Skill Points | `STATE_FARM_POINTS` | OCR scans current skill points → auto-enters EventLab blueprint to farm up to 999 |
| 2️⃣ Buy Cars | `STATE_BUY_CARS` | Five-step visual navigation to Car Collection → batch-purchase 33 Subaru Impreza 22B-STIs |
| 3️⃣ Upgrade Cars | `STATE_UPGRADE_CARS` | Enter garage → select each Impreza with a NEW tag → spend skill points on skill tree |
| 4️⃣ Sell Cars | `STATE_TRASH_CARS` | Enter garage → batch-remove upgraded Imprezas (keeping the S2 main car) |

---

## 🏗️ Project Architecture

```
FH6_AutoBot/
├── main_bot.py                # 🚀 Main entry point (interactive menu to choose starting stage)
│
├── engine/                    # 🧠 Perception Engine Layer
│   ├── __init__.py            #    Package init (module docstring + backward-compat notes)
│   ├── ocr.py                 #    Computer vision (OCR / template matching / color detection)
│   ├── state_detect.py        #    Game state detector (color histogram + OCR hybrid)
│   ├── runtime.py             #    PyInstaller runtime path compatibility layer
│   └── utils.py               #    Utilities (logging / window ops / gamepad wrapper / MSS capture)
│
├── macro/                     # 🎮 Macro Operation Layer
│   ├── __init__.py            #    Unified exports (entry point for all public APIs)
│   ├── core.py                #    Infrastructure: screenshots, logging, config constants
│   ├── master_loop.py         #    Master state machine loop (run_master_bot_loop)
│   ├── navigation.py          #    Menu navigation, visual braking, return-to-garage
│   ├── purchase.py            #    5-step Impreza purchase navigation + purchase macro
│   ├── garage.py              #    Garage grid operations: select car, delete car, main car nav
│   └── upgrade.py             #    Car upgrade macro (with Cannot Afford popup detection)
│
├── farm/                      # 🏁 EventLab Farming
│   ├── __init__.py            #    Package init
│   └── skills.py              #    Visual state machine (auto-drive + RT boost + finish detection)
│
├── tools/                     # 🔧 Developer Utilities (not packaged into exe)
│   ├── debug_cars_roi.py      #    Quick screenshot + annotate car ROI regions
│   ├── tool_annotate_roi.py   #    Interactive drag-to-draw ROI annotation tool
│   ├── tool_calibrate_states.py  # State detection calibration (histogram/brightness capture)
│   └── tool_mask_lines.py     #    Mask boundary line placement tool
│
├── tests/                     # 🧪 Unit Tests (66 test cases)
│   ├── conftest.py            #    Fixtures + cross-platform mocks (Linux CI compatible)
│   ├── test_ocr.py            #    HSV constants / green-box detection / keyword matching
│   ├── test_farm_skills.py    #    Session calculation / checkpoint persistence
│   ├── test_purchase.py       #    Fuzzy word matching (edit distance / OCR tolerance)
│   ├── test_core.py           #    State constants / formula validation
│   └── test_utils.py          #    Logging functions / MSS singleton
│
├── debug/                     # 🐛 Debug output (screenshots, calibration data)
│
├── .github/workflows/
│   ├── ci.yml                 # ⚡ GitHub Actions CI (Ruff lint + pytest)
│   └── release.yml            # 📦 Automated release (PyInstaller build + GitHub Release)
│
├── build.py                   # 🔨 One-click PyInstaller build script
├── FH6AutoBot.spec            # 📋 PyInstaller packaging configuration
├── hook_utf8.py               # 🔤 PyInstaller runtime hook (Windows UTF-8 console fix)
├── setup.py                   # ⚙️ One-click environment setup script
├── requirements.txt           # 📋 Python dependency list
├── ruff.toml                  # 🔍 Ruff linter configuration
├── pytest.ini                 # 🧪 Pytest configuration
├── race_state.json            # 💾 Race checkpoint persistence (auto-generated)
└── play_archive.txt           # 📜 Session log archive
```

---

## ⚙️ Dependencies

| Dependency | Purpose |
|-----------|---------|
| `opencv-python` ≥ 4.8.0 | Image processing, template matching, color space conversion |
| `pytesseract` ≥ 0.3.10 | OCR text recognition (requires Tesseract engine installed) |
| `numpy` ≥ 1.24.0 | Numerical computing, image array operations |
| `mss` ≥ 9.0.0 | High-performance screen capture |
| `vgamepad` ≥ 0.1.0 | Virtual Xbox 360 gamepad driver (requires ViGEmBus installed) |
| `colorama` ≥ 0.4.6 | Colored terminal log output |

### Prerequisites

#### 🖥️ Software Environment
1. **Python 3.10+**
2. **Tesseract OCR** — [Download & Install](https://github.com/UB-Mannheim/tesseract/releases) (check "Add to PATH" during installation)
3. **ViGEmBus** driver — [Download & Install](https://github.com/ViGEm/ViGEmBus/releases) (restart required after installation)
4. The game must run in **Windowed** or **Borderless Windowed** mode
5. Recommended resolution: **2560×1440** (visual detection is calibrated at this resolution)

#### 🎮 In-Game Preparation
1. **Purchase the main car**: 1998 Subaru Impreza 22B-STI Version
2. **Install an S2-class tune**: Apply any S2-class tune to the car (PI badge should display as blue)
3. **Favorite the blueprint**: Search for and favorite blueprint share code `890169683` (used for EventLab auto-farming)

> ⚠️ The S2 blue PI badge on the main car is the key indicator the program uses to distinguish "keep" cars from "deletable" cars — make sure to apply the tune.

### One-Click Install

```bash
python setup.py
```

Automatically completes: Install Python dependencies → Detect Tesseract OCR → Detect ViGEmBus driver

---

## 🚀 Usage

### Run from Source

```bash
python main_bot.py
```

The interactive menu provides the following options:

| Option | Description | When to Use |
|--------|------------|-------------|
| `[0]` | 🔄 Auto loop (full 4-stage cycle) | From the main menu |
| `[1]` | 🏎️ Farm Skill Points | From the main menu |
| `[2]` | 🛒 Buy Cars | From the main menu |
| `[3]` | ⚡ Upgrade Cars | From the main menu |
| `[4]` | 🗑️ Sell Cars | From the garage with Subaru brand selected |
| `[5]` | ⏭️ Skip Buy (Farm → Upgrade → Sell loop) | From the main menu, when garage already has unupgraded cars |

### Build Standalone Executable

```bash
python build.py
```

Produces `dist/FH6AutoBot/FH6AutoBot.exe` — a portable executable that does not require Python installed. Tesseract OCR and ViGEmBus driver are still required on the target machine.

### Automated Release

Pushing a version tag (e.g. `v1.0.0`) triggers the GitHub Actions release workflow, which builds the exe on `windows-latest` and publishes a ZIP archive as a GitHub Release.

---

## 🧪 Testing & CI

### Run Tests Locally

```bash
# Install test dependencies
pip install pytest ruff

# Run unit tests (hardware-dependent tests are auto-skipped)
python -m pytest

# Lint & format check
python -m ruff check .
python -m ruff format --check .
```

### GitHub Actions

Every `push` and `pull_request` to the `main` branch automatically triggers the CI pipeline:

| Job | Description |
|-----|-------------|
| **Lint** | Ruff code check + format validation |
| **Test** | pytest runs 66 unit tests (ubuntu-latest, auto-mocks Windows dependencies) |

---

## 🔍 Core Technical Principles

### Visual State Detection
- **Color Histogram + OCR Hybrid Detection**: StateDetector combines color distribution features with OCR text recognition to determine the current game UI state
- **Inverse Detection**: A quirk of Forza menus — the currently active tab has a *lower* template match score (because the highlighted style differs from the template)
- **PI Badge Color Detection**: Uses HSV color space to detect PI badge color and distinguish car classes (blue = S2 main car, orange = B-class deletable)

### OCR Recognition
- **Multi-Strategy Voting**: For the same region, recognition is performed using PSM 8/7/13 modes separately, and the majority-consistent result is chosen
- **OTSU Adaptive Thresholding**: Available Points reading uses OTSU adaptive thresholding to prevent single-digit numbers from being erroneously padded with zeros
- **Zero Skill Points Fallback**: When all digit OCR results return 0, unrestricted OCR is used to detect the "No Skill Points Available" text

### Garage Grid Navigation
- **Typewriter Traversal**: Scans the 3-row × N-column vehicle grid column by column, top to bottom
- **Triple Verification Lock**: OCR car name keywords (2/3) + NEW yellow tag + LEGENDARY orange rarity
- **NMS Deduplication**: Non-Maximum Suppression is applied to template matching results to prevent duplicate detection of the same vehicle
- **Cannot Afford Popup Detection**: Monitors for the insufficient skill points popup in real-time during upgrades, auto-presses A to dismiss and stops purchasing

### Build & Packaging
- **PyInstaller One-Dir Mode**: `build.py` + `FH6AutoBot.spec` bundle all Python modules into a portable directory; vgamepad's `ViGEmClient.dll` is explicitly included as a data file
- **Runtime Path Layer**: `engine/runtime.py` provides unified path resolution for both development and frozen (exe) environments
- **UTF-8 Console Fix**: `hook_utf8.py` runtime hook ensures Chinese log output renders correctly on Windows consoles with non-UTF-8 defaults

---

## 📝 License

This project is for learning and personal use only.
