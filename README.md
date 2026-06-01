# 🏎️ FH6 AutoBot — A Never-Ending AFK Farming Machine

**🌐 Language: English | [中文](README_zh-CN.md)**

[![CI](https://github.com/hypoxic127/FH6-AFK/actions/workflows/ci.yml/badge.svg)](https://github.com/hypoxic127/FH6-AFK/actions/workflows/ci.yml)
[![Release](https://github.com/hypoxic127/FH6-AFK/actions/workflows/release.yml/badge.svg)](https://github.com/hypoxic127/FH6-AFK/actions/workflows/release.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078d4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/license-Personal%20Use-f5c542)

> A fully automated, infinite-loop Skill Points farming system for **Forza Horizon 6**.
> Powered by **Computer Vision (OpenCV + Tesseract OCR)** and **Virtual Gamepad (ViGEmBus)**, achieving **zero human intervention** closed-loop farming.
> Comes with a **Cyberpunk-styled Web UI** dashboard for remote monitoring and one-click control.

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [🔄 Workflow](#-workflow)
- [🛠️ Tech Stack](#️-tech-stack)
- [🚀 Getting Started](#-getting-started)
- [📖 Usage](#-usage)
- [📁 Project Structure](#-project-structure)
- [🧪 Testing & CI](#-testing--ci)
- [🔍 Technical Details](#-technical-details)
- [🤝 Contributing](#-contributing)
- [📝 License](#-license)

---

## ✨ Features

| Feature | Description |
|:--------|:------------|
| 🔁 **4-Stage Auto Loop** | Farm → Buy → Upgrade → Sell, infinite loop, sleep & farm |
| 👁️ **Computer Vision State Machine** | Color histogram + OCR hybrid detection, identifies 10+ game UI states |
| 🎮 **Virtual Gamepad** | ViGEmBus simulates Xbox 360 controller, native-level input |
| 🖥️ **Web UI Dashboard** | Glassmorphism UI + real-time logs + QR code mobile monitoring |
| ⏹️ **Instant Stop** | Thread injection technology, bot stops immediately on button click |
| 🎰 **Super Wheelspin Counter** | Automatically tracks upgrade macro executions |
| 📦 **One-Click Build** | PyInstaller single-file `.exe`, no Python required |
| 🧪 **95 Test Cases** | Ruff linting + Pytest coverage, GitHub Actions CI |

---

## 🔄 Workflow

```
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  🏎️ Farm     │────▶│  🛒 Buy      │────▶│  ⚡ Upgrade  │────▶│  🗑️ Sell     │
    │ Skill Points│     │    Cars     │     │    Cars     │     │    Cars     │
    └──────┬──────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
           │                                                           │
           │                    ♻️ Infinite Loop                       │
           └───────────────────────────────────────────────────────────┘
```

| Stage | State Constant | Description |
|:-----:|:---------------|:------------|
| 1️⃣ | `STATE_FARM_POINTS` | OCR scans skill points → auto-enters EventLab to farm up to 999 |
| 2️⃣ | `STATE_BUY_CARS` | Five-step visual navigation → batch-purchase 33 Subaru Impreza 22B-STIs |
| 3️⃣ | `STATE_UPGRADE_CARS` | Select each car with NEW tag → spend skill points on skill tree |
| 4️⃣ | `STATE_TRASH_CARS` | Batch-remove upgraded Imprezas (keeping S2 main car) |

---

## 🛠️ Tech Stack

| Category | Technology | Purpose |
|:---------|:-----------|:--------|
| **Vision Engine** | OpenCV, Tesseract OCR | Image processing, text recognition, color detection |
| **Numerics** | NumPy | Histogram comparison, image matrix operations |
| **Screen Capture** | MSS | High-performance cross-platform screenshots |
| **Gamepad** | VGamepad + ViGEmBus | Virtual Xbox 360 controller input |
| **Web Server** | Flask + Flask-SocketIO | Real-time Web UI control panel |
| **Frontend** | Vanilla JS + CSS3 | Glassmorphism dashboard, WebSocket live logs |
| **Testing** | Pytest + Ruff | Unit testing + code quality checks |
| **Packaging** | PyInstaller | One-click single-file executable build |
| **CI/CD** | GitHub Actions | Automated testing + Release publishing |

---

## 🚀 Getting Started

### 📋 Prerequisites

> ⚠️ The following software must be installed before running

| Software | Version | Download | Notes |
|:---------|:--------|:---------|:------|
| **Python** | 3.10+ | [python.org](https://www.python.org/downloads/) | Check "Add to PATH" during install |
| **Tesseract OCR** | 5.x | [Download](https://github.com/UB-Mannheim/tesseract/releases) | Check "Add to PATH" during install |
| **ViGEmBus** | Latest | [Download](https://github.com/ViGEm/ViGEmBus/releases) | **Reboot required** after install |

### 📥 Installation

```bash
# 1. Clone the repository
git clone https://github.com/hypoxic127/FH6-AFK.git
cd FH6-AFK

# 2. One-click install (auto-creates venv + installs dependencies)
python setup.py

# 3. Launch (Web UI mode)
python main_bot.py --web
```

### 🎮 In-Game Preparation

Before starting the bot, ensure the following:

1. **Game language must be set to English** — OCR depends on English text
2. **Windowed mode** — Windowed or Borderless Windowed (recommended: 2560×1440)
3. **Purchase main car** — `1998 Subaru Impreza 22B-STI Version`
4. **Install S2 tune** — Any S2-class tune (PI badge = blue)
5. **Favorite the EventLab blueprint** — Share code `890169683`

> **⚠️ Important:** The S2 **blue PI badge** on the main car is the sole indicator the program uses to distinguish "keep" vs "deletable" cars. Make sure your main car has an S2 tune applied.

---

## 📖 Usage

### 🌐 Web UI Mode (Recommended)

```bash
python main_bot.py --web              # Default port 6800
python main_bot.py --web --port 8080  # Custom port
```

Open `http://localhost:6800` in your browser to access the control panel:

- 🎯 **Live Status** — Current stage, loop count, runtime, super wheelspin count
- 🔄 **Progress Bar** — Visual 4-stage progress indicator
- ⚙️ **Stage Selector** — Start from any stage via dropdown
- 📜 **Live Log Terminal** — Syntax-highlighted real-time log stream
- 📱 **QR Remote Monitoring** — Scan QR code to monitor from your phone

### 💻 Terminal Mode

```bash
python main_bot.py
```

| Option | Function | When to Use |
|:------:|:---------|:------------|
| `[0]` | 🔄 Auto loop (full cycle) | Main menu — full 4-stage infinite loop |
| `[1]` | 🏎️ Farm Skill Points | Main menu — enter EventLab |
| `[2]` | 🛒 Buy Cars | Main menu — batch purchase Imprezas |
| `[3]` | ⚡ Upgrade Cars | Main menu — spend skill points |
| `[4]` | 🗑️ Sell Cars | In garage, Subaru brand selected |
| `[5]` | ⏭️ Skip Buy loop | When garage already has un-upgraded cars |

### 📦 Build Executable

```bash
python packaging/build.py
```

Produces `dist/FH6AutoBot.exe` — portable, no Python needed (Tesseract & ViGEmBus still required).

> **💡 Tip:** Push a git tag (e.g. `git tag v1.2.0 && git push --tags`) to auto-trigger GitHub Actions build and publish to the Releases page.

---

## 📁 Project Structure

```
FH6_AutoBot/
│
├── main_bot.py                 # 🚀 Entry point (Terminal / Web UI)
│
├── engine/                     # 🧠 Perception Engine
│   ├── ocr.py                  #    Computer vision (OCR + color detection)
│   ├── state_detect.py         #    Game state detector (histogram + OCR hybrid)
│   ├── event_bus.py            #    Event bus (log/state push to Web UI)
│   ├── runtime.py              #    PyInstaller runtime path resolution
│   └── utils.py                #    Logging / window ops / gamepad / MSS capture
│
├── macro/                      # 🎮 Macro Operations
│   ├── master_loop.py          #    Master state machine (4-stage loop engine)
│   ├── core.py                 #    Infrastructure: screenshots, logging, constants
│   ├── navigation.py           #    Menu navigation / visual braking / return-to-garage
│   ├── purchase.py             #    5-step Impreza purchase navigation
│   ├── garage.py               #    Garage grid: select / delete / main car nav
│   └── upgrade.py              #    Upgrade macro (Cannot Afford detection)
│
├── farm/                       # 🏁 EventLab Farming
│   └── skills.py               #    Visual state machine (auto-drive + finish detection)
│
├── web/                        # 🌐 Web UI Control Panel
│   ├── server.py               #    Flask + SocketIO server
│   ├── state_manager.py        #    Global state manager
│   └── static/                 #    Frontend assets
│       ├── index.html          #      Dashboard page
│       ├── style.css           #      Cyberpunk theme styles
│       └── app.js              #      WebSocket client logic
│
├── packaging/                  # 📦 Build & Packaging
│   ├── build.py                #    One-click PyInstaller build script
│   ├── FH6AutoBot.spec         #    PyInstaller spec (--onefile)
│   └── hook_utf8.py            #    Runtime hook (Windows UTF-8 fix)
│
├── tests/                      # 🧪 Unit Tests (95 cases)
├── tools/                      # 🔧 Dev utilities (not packaged)
│
├── .github/workflows/
│   ├── ci.yml                  #    CI (Ruff check + Pytest)
│   └── release.yml             #    Release (PyInstaller → GitHub Release)
│
├── setup.py                    # ⚙️ One-click environment setup
├── requirements.txt            # 📋 Python dependencies
├── ruff.toml                   # 🔍 Ruff linter config
└── pytest.ini                  # 🧪 Pytest config
```

---

## 🧪 Testing & CI

```bash
# Run all tests
python -m pytest

# Lint check
python -m ruff check .

# Format check
python -m ruff format --check .
```

| CI Job | Trigger | Description |
|:-------|:--------|:------------|
| **Lint** | Push / PR | Ruff lint + format validation |
| **Test** | Push / PR | 95 test cases (ubuntu-latest) |
| **Release** | `v*` tag | PyInstaller build → GitHub Release |

---

## 🔍 Technical Details

### 👁️ Visual State Detection

- **Histogram + OCR Hybrid** — `StateDetector` uses color distribution features for fast candidate screening, then OCR for precise verification
- **PI Badge Color Detection** — HSV color space analysis: blue = S2 main car (keep), orange = deletable

### 🔤 OCR Strategy

- **PSM 7 Single-Line Mode** — Uses Tesseract PSM 7 for clean single-line digit recognition
- **OTSU Adaptive Thresholding** — Prevents single-digit zero-padding errors
- **Zero Skill Points Fallback** — Detects "No Skill Points Available" text

### 🎯 Garage Grid Navigation

- **Typewriter Traversal** — Column by column, top to bottom (3×N grid)
- **Triple Verification** — OCR keywords (2/3 match) + NEW yellow tag + LEGENDARY orange rarity
- **Cannot Afford Detection** — Auto-dismisses popup, stops purchasing

### 📦 Build & Packaging

- **PyInstaller --onefile** — Single ~44MB executable
- **Runtime Path Layer** — `engine/runtime.py` unified path resolution (dev/packaged dual-mode)
- **UTF-8 Console Fix** — `hook_utf8.py` resolves Chinese log garbling on Windows

---

## 🤝 Contributing

Contributions are welcome! Please follow this workflow:

1. **Fork** this repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a **Pull Request**

### Development Standards

- 🐍 Code style: PEP 8 (enforced by Ruff)
- 🏷️ Commit format: [Conventional Commits](https://www.conventionalcommits.org/) (`feat` / `fix` / `docs` / `refactor` / `chore`)
- ✅ All PRs must pass CI checks (Lint + Test)

---

## 📝 License

This project is for **learning and personal use** only.

---

**If this project helps you, please give it a ⭐ Star!**

Made with ❤️ by [hypoxic127](https://github.com/hypoxic127)
