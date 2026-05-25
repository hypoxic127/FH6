# -*- coding: utf-8 -*-
"""
FH6_AutoBot EventLab 自动跑图模块 (module_farm_skills.py)
=========================================================
本模块负责"刷技能点"阶段的全部逻辑：

  从暂停菜单出发，自动导航进入 EventLab -> 选择收藏蓝图赛事
  -> 选车 -> 开始比赛 -> 全程按住 RT 加速 -> 检测终点 -> 重启/退出

核心设计 - 视觉状态机 (Visual State Machine):
  使用 cv2.matchTemplate 对每帧截图进行模板匹配，
  识别当前处于游戏的哪个 UI 状态（菜单标签 / EventLab / 赛道 / 结算画面），
  然后根据状态执行对应的手柄操作。

额外功能:
  - OCR 读取技能点数字，支持断点续跑 (race_state.json)
  - 安全超时（12 小时上限）
  - Rate Event 弹窗自动关闭
"""

import time
import os
import json
import cv2
import mss
import numpy as np
import vgamepad as vg
import ctypes
import math
from ctypes import wintypes
from colorama import Fore, Style
import module_ocr
from utils import (
    log_info, log_success, log_warning, log_error,
    find_game_window, force_foreground, get_client_rect,
    press_button, get_mss
)


def get_matches_needed(current_points):
    """根据当前技能点计算还需要跑多少场比赛。每场约 10 点，目标 999。"""
    max_points = 999
    points_per_match = 10
    matches_needed = math.ceil((max_points - current_points) / points_per_match)
    return 0 if matches_needed < 0 else matches_needed

def load_templates():
    """
    从 templates/ 目录加载所有视觉模板图片。
    模板分三类:
      1. 菜单标签模板 - 识别当前在哪个主菜单标签页
      2. 导航锚点模板 - 识别 EventLab/赛事选择/选车/赛前等子页面
      3. 赛事子菜单模板 - 识别 Events 子标签（Featured/My Favorites 等）
    """
    templates_dir = "templates"
    
    # 1. Standard Menu Tab templates
    menu_files = {
        "CAMPAIGN": "campaign.png",
        "CARS": "cars.png",
        "MY HORIZON": "my_horizon.png",
        "ONLINE": "online.png",
        "CREATIVE HUB": "creative_hub.png",
        "STORE": "store.png"
    }
    
    # 2. Navigation Anchor templates (Event.png used for FAVORITES_LIST)
    anchor_files = {
        "CREATIVE_HUB": "eventlab.png",
        "EVENTLAB_MENU": "Play_event.png",
        "FAVORITES_LIST": "Event.png",
        "RACE_READY": "choose.png",
        "CAR_SELECT": "my_cars.png",
        "CAR_DETAIL": "car_detail.png",
        "CAR_CARD": "car.png",
        "PRE_RACE": "start_race_event.png",
        "RACE_END": "end.png",
        "NEXT_SCREEN": "Next.png",
        "PLAYING": "playing.png"
    }
    
    # 3. Events Submenu Tab templates to identify being in Events submenu screen
    submenu_files = {
        "FEATURED": "Featured.png",
        "BEST_OF_THE_MON": "Best_of_the_mon.png",
        "POPULAR": "Popular.png",
        "NEW_AND_TREND": "New_and_trend.png",
        "NEW": "New.png",
        "FAVORITE_CREATOR": "Favorite_creator.png",
        "MY_FAVORITES": "My_favorites.png"
    }
    
    loaded_menus = {}
    log_info("Loading menu templates into memory...")
    for state, filename in menu_files.items():
        path = os.path.join(templates_dir, filename)
        if not os.path.exists(path):
            log_warning(f"Template for {state} not found at {path}!")
            continue
        img = cv2.imread(path)
        if img is None:
            log_error(f"Failed to read template image: {path}")
            continue
        loaded_menus[state] = img
        
    loaded_anchors = {}
    log_info("Loading navigation anchor templates into memory...")
    for state, filename in anchor_files.items():
        path = os.path.join(templates_dir, filename)
        if not os.path.exists(path):
            log_warning(f"Anchor template for {state} not found at {path}!")
            continue
        img = cv2.imread(path)
        if img is None:
            log_error(f"Failed to read anchor template image: {path}")
            continue
        loaded_anchors[state] = img
        log_success(f"Loaded anchor {state} from: {path}")
        
    loaded_submenu = {}
    log_info("Loading events submenu templates into memory...")
    for state, filename in submenu_files.items():
        path = os.path.join(templates_dir, filename)
        if not os.path.exists(path):
            log_warning(f"Submenu template for {state} not found at {path}!")
            continue
        img = cv2.imread(path)
        if img is None:
            log_error(f"Failed to read submenu template image: {path}")
            continue
        loaded_submenu[state] = img
        log_success(f"Loaded submenu tab {state} from: {path}")
        
    return loaded_menus, loaded_anchors, loaded_submenu

# Pre-defined constants for anchor matching (avoid recreating every call)
_ANCHOR_SKIP_SET = frozenset(["CAR_DETAIL", "CAR_CARD", "RACE_END", "NEXT_SCREEN", "PLAYING"])
_ANCHOR_THRESHOLDS = {
    "PRE_RACE": 0.80,
    "CAR_SELECT": 0.80,
    "FAVORITES_LIST": 0.80,
    "RACE_READY": 0.80,
    "EVENTLAB_MENU": 0.80,
    "CREATIVE_HUB": 0.80
}

def get_current_state(resized, loaded_menus, loaded_anchors, loaded_submenu):
    """
    基于模板匹配的实时游戏 UI 状态检测引擎。

    检测优先级: 导航锚点 > 赛事子菜单 > 主菜单标签
    主菜单标签使用 "反差法":当前激活的标签因高亮样式而匹配分较低。

    返回: 状态名称字符串 (如 'CARS', 'PRE_RACE', 'UNKNOWN' 等)
    """
    
    # 1. Try matching the high-priority anchors first
    anchor_scores = {}
    for state, template in loaded_anchors.items():
        if state in _ANCHOR_SKIP_SET:
            continue
        res = cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        anchor_scores[state] = max_val
        
    anchor_thresholds = _ANCHOR_THRESHOLDS
    
    # Check if any anchor matches its threshold
    # Sort anchor matches descending to find the best match
    best_anchor_state = None
    best_anchor_score = -1
    for state, score in anchor_scores.items():
        threshold = anchor_thresholds.get(state, 0.85)
        if score >= threshold and score > best_anchor_score:
            best_anchor_score = score
            best_anchor_state = state
            
    # Guard: Prevent selecting events on other tabs before MY FAVORITES is active.
    # If the Event card matches but the unselected "MY FAVORITES" tab is still visible on screen,
    # we are not actually on the "MY FAVORITES" tab yet. We must continue shifting right.
    if best_anchor_state == "FAVORITES_LIST" and "MY_FAVORITES" in loaded_submenu:
        res_my_fav = cv2.matchTemplate(resized, loaded_submenu["MY_FAVORITES"], cv2.TM_CCOEFF_NORMED)
        _, max_val_my_fav, _, _ = cv2.minMaxLoc(res_my_fav)
        if max_val_my_fav >= 0.85:
            log_warning(f"Event card matched (score: {best_anchor_score:.3f}), but unselected MY FAVORITES tab header is still visible (score: {max_val_my_fav:.3f}). Guard triggered: Shifting right to find active My Favorites tab.")
            best_anchor_state = None
            
    if best_anchor_state is not None:
        # Print diagnostic scores
        scores_str = ", ".join([f"{k}: {v:.3f} (th={anchor_thresholds.get(k, 0.85)})" for k, v in sorted(anchor_scores.items())])
        log_info(f"Anchor Matching Scores -> {scores_str} -> Matched Anchor: {best_anchor_state}")
        return best_anchor_state
        
    # 2. Check if we are on the Events Submenu screen
    submenu_scores = {}
    for state, template in loaded_submenu.items():
        res = cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        submenu_scores[state] = max_val
        
    high_submenu_matches = [state for state, score in submenu_scores.items() if score >= 0.85]
    if len(high_submenu_matches) > 0:
        submenu_scores_str = ", ".join([f"{k}: {v:.3f}" for k, v in sorted(submenu_scores.items())])
        log_info(f"Submenu Matching Scores -> {submenu_scores_str} -> Matched: EVENTS_SUBMENU (via {high_submenu_matches})")
        return "EVENTS_SUBMENU"
        
    # 3. Fall back to standard menu tab detection
    menu_scores = {}
    for state, template in loaded_menus.items():
        res = cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        menu_scores[state] = max_val
        
    # Verify if we are on the main tab menu screen at all
    # In a valid tab menu screen, at least 3 inactive templates should match highly (>= 0.85)
    high_matches = [state for state, score in menu_scores.items() if score >= 0.85]
    
    # Print matching scores for diagnostics (in a clean formatted way)
    menu_scores_str = ", ".join([f"{k}: {v:.3f}" for k, v in sorted(menu_scores.items())])
    log_info(f"Menu Matching Scores -> {menu_scores_str}")
    
    if len(high_matches) < 3:
        return "UNKNOWN"
        
    # The active tab is the one with a LOW match score among the menu tabs
    # We prioritize CAMPAIGN and CARS states
    if menu_scores.get("CAMPAIGN", 0) < 0.75 and menu_scores.get("CARS", 0) >= 0.85:
        return "CAMPAIGN"
    if menu_scores.get("CARS", 0) < 0.75 and menu_scores.get("CAMPAIGN", 0) >= 0.85:
        return "CARS"
        
    # Fallback/Check other states if active
    for state in ["MY HORIZON", "ONLINE", "CREATIVE HUB", "STORE"]:
        if menu_scores.get(state, 0) < 0.75:
            if state == "CREATIVE HUB":
                return "CREATIVE_HUB"
            return state
            
    return "UNKNOWN"

def archive_match_to_file(match_num, remaining_matches):
    """将比赛完成记录归档到 play_archive.txt，包含时间戳和剩余场次。"""
    import datetime
    archive_path = "play_archive.txt"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Generate a premium structured log entry
    log_entry = (
        f"============================================================\n"
        f"Timestamp: {timestamp}\n"
        f"Match Completed: #{match_num}\n"
        f"Remaining Matches Needed: {remaining_matches}\n"
        f"Status: SUCCESS (Archived & Settled)\n"
        f"============================================================\n\n"
    )
    
    try:
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        log_success(f"Archived play count to {archive_path}")
    except Exception as e:
        log_error(f"Failed to archive play count to file: {e}")

RACE_STATE_FILE = "race_state.json"

def save_race_state(matches_needed, matches_completed):
    """保存比赛进度到 JSON 文件，支持断点续跑。"""
    import datetime
    state = {
        "matches_needed": matches_needed,
        "matches_completed": matches_completed,
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(RACE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        log_info(f"Race state saved: {matches_needed} races remaining, {matches_completed} completed")
    except Exception as e:
        log_error(f"Failed to save race state: {e}")

def load_race_state():
    """加载已保存的比赛进度（剩余场次, 已完成场次, 最后更新时间），用于断点续跑。"""
    if not os.path.exists(RACE_STATE_FILE):
        return None
    try:
        with open(RACE_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        matches_needed = state.get("matches_needed", 0)
        matches_completed = state.get("matches_completed", 0)
        last_updated = state.get("last_updated", "unknown")
        if matches_needed > 0:
            return matches_needed, matches_completed, last_updated
        return None
    except Exception as e:
        log_error(f"Failed to load race state: {e}")
        return None

def clear_race_state():
    """所有比赛完成后清除状态文件，避免下次启动时误读取旧状态。"""
    try:
        if os.path.exists(RACE_STATE_FILE):
            os.remove(RACE_STATE_FILE)
            log_success(f"Race state file cleared ({RACE_STATE_FILE})")
    except Exception as e:
        log_error(f"Failed to clear race state file: {e}")

def main(gamepad=None):
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}   FORZA HORIZON 6 AUTOMATED RACE ENTRY - STATE MACHINE")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    # 1. Initialize Tesseract
    module_ocr.setup_tesseract()

    # OCR-Only Skill Points Scanner configuration
    print(f"\n{Fore.YELLOW}==================================================")
    print(f"   OCR-ONLY SKILL POINTS SCANNER")
    print(f"   (Must visit CARS menu tab to scan points initially)")
    print(f"=================================================={Style.RESET_ALL}")

    # 2. Load Templates
    menu_templates, anchor_templates, submenu_templates = load_templates()
    if not menu_templates and not anchor_templates and not submenu_templates:
        raise RuntimeError("No templates loaded. Cannot proceed with state machine!")

    # 3. Game Window Check & Activation
    hwnd = find_game_window()
    if hwnd:
        log_success("Forza Horizon 6 game window detected.")
        force_foreground(hwnd)
    else:
        log_warning("Forza Horizon 6 window not found! Running in fallback mode (user must focus the game manually).")

    # 4. Gamepad Initialization — reuse parent's gamepad if provided
    owns_gamepad = False
    if gamepad is None:
        log_info("Initializing virtual Xbox 360 controller...")
        try:
            gamepad = vg.VX360Gamepad()
            owns_gamepad = True
            log_success("Virtual controller successfully initialized.")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize virtual controller: {e}")
    else:
        log_info("Reusing existing virtual controller from parent module.")

    # Count down sleep to switch to the game window if not auto-focused
    if not hwnd:
        print()
        for i in range(5, 0, -1):
            print(f"\r{Fore.YELLOW}[WAIT]{Style.RESET_ALL} Please switch to the Forza Horizon 6 window... {i}s remaining", end="", flush=True)
            time.sleep(1.0)
        print("\n")

    log_info("Starting Real-time Visual State Machine loop (Press Ctrl+C to terminate)...")
    
    max_runtime_hours = 12  # Safety timeout: 12 hours max runtime
    start_time = time.time()
    last_points = None
    unknown_consecutive_count = 0
    is_racing = False
    racing_print_timer = 0
    matches_completed = 0
    waiting_for_next = False
    waiting_for_gameplay = False
    points_scanned = False
    matches_needed = 0
    
    # Try to load saved race state for resuming without OCR scan
    saved_state = load_race_state()
    if saved_state is not None:
        matches_needed, matches_completed, last_updated = saved_state
        points_scanned = True  # Skip OCR scanning since we have saved state
        print(f"\n{Fore.CYAN}{Style.BRIGHT}==========================================")
        print(f"   [RESUMING FROM SAVED STATE]")
        print(f"   Matches Remaining: {matches_needed}")
        print(f"   Matches Already Completed: {matches_completed}")
        print(f"   Last Updated: {last_updated}")
        print(f"   (Skipping OCR skill points scan)")
        print(f"==========================================\n")
    
    # Use shared MSS singleton to avoid duplicate GDI handles
    sct = get_mss()
    
    # Cache client rect (only update periodically, not every frame)
    cw, ch = 2560, 1440
    cx, cy = 0, 0
    rect_update_timer = 0
    
    try:
      while True:
        # Safety timeout check
        elapsed_hours = (time.time() - start_time) / 3600
        if elapsed_hours >= max_runtime_hours:
            break
        
        # Update client rect every 2 seconds instead of every frame
        now = time.time()
        if now - rect_update_timer > 2.0:
            if hwnd:
                try:
                    cx, cy, cw, ch = get_client_rect(hwnd)
                except Exception as e:
                    log_warning(f"Failed to get client rect: {e}. Falling back to primary screen.")
            rect_update_timer = now
        
        # Capture the game window client area
        try:
            monitor = {"top": cy, "left": cx, "width": cw, "height": ch}
            screenshot = sct.grab(monitor)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as e:
            log_error(f"Failed to capture screen: {e}")
            time.sleep(0.5)
            continue
        
        # Resize once per frame — all template matching uses this
        resized = cv2.resize(img, (1600, 900), interpolation=cv2.INTER_AREA)

        # === "Rate Event" popup detection ===
        # Detect the bright yellow-green banner at the top of screen.
        # If found, press A to select "Like" and dismiss the dialog.
        try:
            h_frame, w_frame = resized.shape[:2]
            # Check top 15% of screen for the distinctive yellow-green banner
            banner_roi = resized[0:int(h_frame * 0.15), :]
            hsv_banner = cv2.cvtColor(banner_roi, cv2.COLOR_BGR2HSV)
            # Bright yellow-green: H=25-45, S>150, V>200
            ygmask = cv2.inRange(hsv_banner, np.array([25, 150, 200]), np.array([45, 255, 255]))
            yg_pixels = cv2.countNonZero(ygmask)
            if yg_pixels > 5000:
                # Confirm via OCR: look for "rate" text
                gray_banner = cv2.cvtColor(banner_roi, cv2.COLOR_BGR2GRAY)
                _, thresh_banner = cv2.threshold(gray_banner, 100, 255, cv2.THRESH_BINARY_INV)
                import pytesseract
                banner_text = pytesseract.image_to_string(thresh_banner).strip().lower()
                if "rate" in banner_text or "event" in banner_text:
                    log_success(f"[Rate Event] Detected 'Rate Event' popup (yellow pixels: {yg_pixels}, text: '{banner_text}'). Pressing A to dismiss...")
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)
                    continue
        except Exception:
            pass

        # 0. If in racing mode, hold Right Trigger (RT) to accelerate and scan for RACE_END (end.png)
        if is_racing:
            # Continuously input RT (Right Trigger) fully
            gamepad.right_trigger(value=255)
            gamepad.update()
            
            # Throttle status printing to prevent spamming the console
            if time.time() - racing_print_timer > 2.0:
                log_info("[RACING] Holding Right Trigger (RT) to accelerate... Scanning for end.png...")
                racing_print_timer = time.time()
                
            if "RACE_END" in anchor_templates:
                res = cv2.matchTemplate(resized, anchor_templates["RACE_END"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                # Check for end.png match
                if max_val >= 0.85:
                    # Release Right Trigger
                    gamepad.right_trigger(value=0)
                    gamepad.update()
                    time.sleep(0.5)
                    
                    # Update match counters
                    matches_completed += 1
                    remaining_matches = max(0, matches_needed - 1)
                    
                    # Archive play count to persistent file
                    archive_match_to_file(matches_completed, remaining_matches)
                    
                    # Display match settlement statistics
                    print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                    print(f"   [MATCH PLAYED & SETTLED SUCCESSFULLY]  ")
                    print(f"   Match Number Completed: {matches_completed}            ")
                    print(f"   Original Matches Needed: {matches_needed}              ")
                    print(f"   Remaining Matches Needed: {remaining_matches}          ")
                    print(f"==========================================\n")
                    
                    matches_needed = remaining_matches
                    
                    # Persist race state for resume capability
                    save_race_state(matches_needed, matches_completed)
                    
                    if remaining_matches > 0:
                        # Still have races to run: press X to Restart Race directly
                        log_success(f"Race finished! Detected end.png (score: {max_val:.3f}). {remaining_matches} races remaining, pressing X to restart race...")
                        
                        press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_X, delay=0)
                        
                        # Press A to confirm restart
                        time.sleep(1.0)  # Wait for confirmation dialog
                        press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                        
                        # Exit racing mode, wait for PRE_RACE screen to appear
                        is_racing = False
                        time.sleep(3.0)  # Wait for PRE_RACE screen to load
                    else:
                        # Last race completed: press A to progress to rewards summary
                        log_success(f"Race finished! Detected end.png (score: {max_val:.3f}). All {matches_completed} races completed! Pressing A to view rewards...")
                        
                        press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                        
                        is_racing = False
                        waiting_for_next = True
                        log_info("Waiting for rewards screen to transition to Next screen (Next.png)...")
            else:
                log_warning("RACE_END template (end.png) is not loaded! Cannot detect race finish automatically.")
                
            time.sleep(0.1)
            continue

        # 0.3. If waiting for Next button (last race only), scan for Next.png (NEXT_SCREEN)
        if waiting_for_next:
            if "NEXT_SCREEN" in anchor_templates:
                res = cv2.matchTemplate(resized, anchor_templates["NEXT_SCREEN"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                # Check for Next.png match
                if max_val >= 0.85:
                    log_success(f"Rewards settled! Detected Next.png (score: {max_val:.3f}). All races completed! Pressing B to exit...")
                    
                    # Press B to exit rewards and return to gameplay
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=0)
                    
                    waiting_for_next = False
                    waiting_for_gameplay = True
                    log_info("Waiting for game window to return to gameplay (playing.png)...")
            else:
                log_warning("NEXT_SCREEN template (Next.png) is not loaded! Cannot detect rewards exit automatically.")
                
            time.sleep(0.2)
            continue

        # 0.5. If waiting for gameplay re-entry, scan for playing.png
        if waiting_for_gameplay:
            if "PLAYING" in anchor_templates:
                res = cv2.matchTemplate(resized, anchor_templates["PLAYING"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                # Check for playing.png match
                if max_val >= 0.85:
                    log_success(f"Returned to gameplay! Detected playing.png (score: {max_val:.3f}). Pressing START to open pause menu...")
                    
                    # Press START gamepad button to open pause menu
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=0)
                    
                    waiting_for_gameplay = False
                    time.sleep(2.5)  # Wait for pause menu to load
                    
                    # If all target matches have been completed, exit now that we have returned to the menu
                    if matches_needed <= 0:
                        clear_race_state()  # Clean up saved state
                        print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                        print(f"{Fore.GREEN}{Style.BRIGHT}   [ALL TARGET MATCHES SUCCESSFULLY COMPLETED] ")
                        print(f"{Fore.GREEN}{Style.BRIGHT}   Skill point goal has been successfully reached! ")
                        print(f"   Returned to Menu successfully. ")
                        print(f"{Fore.GREEN}{Style.BRIGHT}==========================================\n")
                        break
            else:
                log_warning("PLAYING template (playing.png) is not loaded! Cannot detect gameplay re-entry.")
                
            time.sleep(0.2)
            continue
            
        # Safeguard: If we just started (points_scanned is False) and we are in Free Roam (playing.png),
        # automatically press Menu/START to open the pause menu and begin navigation.
        if not points_scanned and not is_racing and not waiting_for_gameplay:
            if "PLAYING" in anchor_templates:
                res = cv2.matchTemplate(resized, anchor_templates["PLAYING"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= 0.85:
                    log_success(f"[STARTUP SAFEGUARD] Detected gameplay screen playing.png (score: {max_val:.3f}). Pressing START to open pause menu...")
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.5)  # Wait for pause menu to load
                    continue
        # 0.7. Detect end.png outside of racing mode (e.g. script restarted at race end screen)
        if points_scanned and not is_racing and not waiting_for_next and not waiting_for_gameplay:
            if "RACE_END" in anchor_templates:
                res = cv2.matchTemplate(resized, anchor_templates["RACE_END"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= 0.85:
                    log_success(f"Detected end.png outside racing mode (score: {max_val:.3f}). Handling as race end...")
                    
                    # Update match counters
                    matches_completed += 1
                    remaining_matches = max(0, matches_needed - 1)
                    
                    archive_match_to_file(matches_completed, remaining_matches)
                    
                    print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                    print(f"   [MATCH PLAYED & SETTLED SUCCESSFULLY]  ")
                    print(f"   Match Number Completed: {matches_completed}            ")
                    print(f"   Original Matches Needed: {matches_needed}              ")
                    print(f"   Remaining Matches Needed: {remaining_matches}          ")
                    print(f"==========================================\n")
                    
                    matches_needed = remaining_matches
                    save_race_state(matches_needed, matches_completed)
                    
                    if remaining_matches > 0:
                        log_success(f"{remaining_matches} races remaining, pressing X to restart race...")
                        press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_X, delay=1.0)
                        press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                        
                        # Let state machine detect PRE_RACE and start the race
                        time.sleep(3.0)
                    else:
                        log_success(f"All {matches_completed} races completed! Pressing A to view rewards...")
                        press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                        
                        waiting_for_next = True
                        log_info("Waiting for Next screen (Next.png)...")
                    continue
            
        # Detect Current State via Visual Matching (pass pre-resized image)
        state = get_current_state(resized, menu_templates, anchor_templates, submenu_templates)
        
        if state != "UNKNOWN":
            unknown_consecutive_count = 0
            if waiting_for_gameplay:
                log_success("Successfully re-entered the game menu!")
                waiting_for_gameplay = False
                
        # Enforce that skill points are scanned on the CARS tab initially before proceeding into any submenus.
        if not points_scanned:
            if state in ["EVENTLAB_MENU", "EVENTS_SUBMENU", "FAVORITES_LIST", "RACE_READY", "CAR_SELECT", "PRE_RACE"]:
                log_warning(f"[SAFETY GUARD] Active state: {state}, but skill points have NOT been scanned yet! Pressing B to back out to the main menu tabs...")
                press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.5)
                continue
            
        if state == "CARS":
            # State: CARS tab matched - perform OCR and update matches_needed
            print(f"{Fore.GREEN}{Style.BRIGHT}[STATE: CARS]{Style.RESET_ALL} Arrived at CARS tab! Scanning skill points...")
            detected_points = module_ocr.read_skill_points(img)
            if detected_points is not None:
                matches_needed = get_matches_needed(detected_points)
                print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                print(f"   [SKILL POINTS SCAN SUCCESS on CARS TAB] ")
                print(f"   Current Points: {detected_points} / 999                ")
                print(f"   Matches Needed: {matches_needed} (10 pts/match)       ")
                print(f"==========================================\n")
                last_points = detected_points
                points_scanned = True
                
                # Save initial race state for resume capability
                save_race_state(matches_needed, matches_completed)
                
                if matches_needed <= 0:
                    print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                    print(f"   [GOAL ALREADY REACHED] ")
                    print(f"   Current points {detected_points} >= 999. No matches needed!")
                    print(f"==========================================\n")
                    break
                
                # Shift right to proceed
                print(f"{Fore.YELLOW}[STATE: CARS]{Style.RESET_ALL} Shifting right (RB)... (向右翻页...)")
                press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
            else:
                if not points_scanned:
                    log_warning("OCR failed to read skill points on CARS tab. Enforcing initial scan, retrying on next frame...")
                    time.sleep(0.5)
                else:
                    log_warning(f"OCR failed to read skill points on CARS tab. Using current matches_needed: {matches_needed}")
                    print(f"{Fore.YELLOW}[STATE: CARS]{Style.RESET_ALL} Shifting right (RB)... (向右翻页...)")
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
            
        elif state in ["CAMPAIGN", "MY HORIZON", "ONLINE", "STORE"]:
            # State: Any top level tab menu that is not Creative Hub or CARS
            print(f"{Fore.YELLOW}[STATE: {state}]{Style.RESET_ALL} Not in Creative Hub, shifting right (RB)... (当前不在 Creative Hub，向右翻页...)")
            press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
            
        elif state in ["CREATIVE_HUB", "CREATIVE HUB"]:
            # State: Creative Hub tab matched
            if not points_scanned:
                print(f"{Fore.YELLOW}[STATE: CREATIVE HUB]{Style.RESET_ALL} Initial points not scanned yet! Bypassing Creative Hub, shifting right (RB) to reach CARS...")
                press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
            else:
                print(f"{Fore.GREEN}{Style.BRIGHT}[STATE: CREATIVE_HUB]{Style.RESET_ALL} Arrived at Creative Hub! Entering EventLab (A)... (已到达 Creative Hub，进入 EventLab...)")
                press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)
            
        elif state == "EVENTLAB_MENU":
            # State: EventLab menu matched
            print(f"{Fore.GREEN}{Style.BRIGHT}[STATE: EVENTLAB_MENU]{Style.RESET_ALL} Entering EventLab menu, selecting Play Event (A)... (进入 EventLab 菜单，选择 Play Event...)")
            press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)
            
        elif state == "EVENTS_SUBMENU":
            # State: Events sub-menu tabs list matched
            print(f"{Fore.YELLOW}[STATE: EVENTS_SUBMENU]{Style.RESET_ALL} On Events submenu, searching for My Favorites... Shifting right (RB)... (在赛事子菜单中，向右翻页寻找我的收藏...)")
            press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
            
        elif state == "FAVORITES_LIST":
            # State: My Favorites list matched and target Event card is visible
            print(f"{Fore.GREEN}{Style.BRIGHT}[STATE: FAVORITES_LIST]{Style.RESET_ALL} Arrived at My Favorites! Selecting Event (A)... (已到达我的收藏列表，选中并进入蓝图...)")
            press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)
            
        elif state in ["RACE_READY", "choose"]:
            # State: Race Blueprint Loaded & Ready (Choose Race Type screen active)
            print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
            print(f"   [STATE: RACE_READY] Arrived at Choose Race Type!       ")
            print(f"   Ensuring SOLO is selected and launching...             ")
            print(f"   (到达比赛类型选择界面，确保选中 SOLO 并开始比赛...)      ")
            print(f"==========================================\n")
            
            # Press Up twice and Left twice on D-pad to guarantee Solo (topmost or leftmost option) is selected
            for button in [vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT]:
                for _ in range(2):
                    press_button(gamepad, button, delay=0.3)
                
            # Press A to select Solo
            press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
            
            print(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} SOLO selected! Transitioning to Car Selection...")
            time.sleep(1.5)  # Wait for transition start
            
        elif state == "CAR_SELECT":
            # State: Car Selection screen is active
            print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
            print(f"   [STATE: CAR_SELECT] Arrived at Car Selection Screen!   ")
            print(f"   Checking if target car is selected...                 ")
            print(f"   (到达车辆选择界面，检查目标车辆是否已选中...)           ")
            print(f"==========================================\n")

            
            # Check matching for car stats panel
            res_det = cv2.matchTemplate(resized, anchor_templates["CAR_DETAIL"], cv2.TM_CCOEFF_NORMED)
            _, max_val_det, _, _ = cv2.minMaxLoc(res_det)
            
            # Check matching for car grid card
            res_card = cv2.matchTemplate(resized, anchor_templates["CAR_CARD"], cv2.TM_CCOEFF_NORMED)
            _, max_val_card, _, _ = cv2.minMaxLoc(res_card)
            
            log_info(f"Target Car Stats match: {max_val_det:.3f}, Card match: {max_val_card:.3f}")
            
            if max_val_det >= 0.85:
                log_success("Subaru Impreza 22B-STI matched via stats! Confirming selection (A)...")
                press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                
                print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                print(f"   Car Selected Successfully! Waiting for lobby...       ")
                print(f"==========================================\n")
                time.sleep(3.0)  # Wait for transition to start
            else:
                log_info("Subaru Impreza is not highlighted. Pressing D-pad Right to search...")
                press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, delay=1.2)  # Wait for selection focus animation and stats to load
                
        elif state == "PRE_RACE":
            # State: Pre-race Lobby screen is active
            print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
            print(f"   [STATE: PRE_RACE] Arrived at Pre-Race Lobby!           ")
            print(f"   Start Race Event identified as selected! Launching...  ")
            print(f"   (已到达赛事准备界面，识别到已选中 Start Race Event，直接进入...) ")
            print(f"==========================================\n")
            
            # Press A directly to enter Start Race Event
            press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
            
            log_success("Start Race Event selected successfully! Transitioning to racing mode...")
            is_racing = True
            racing_print_timer = time.time()
            time.sleep(3.0)  # Wait for transition start
            
        else:
            # For UNKNOWN state or transitioning/black screen
            unknown_consecutive_count += 1
            print(f"{Fore.BLUE}[STATE: {state}]{Style.RESET_ALL} Waiting for UI to load or screen to transition... (等待 UI 加载 or 黑屏结束...) [Consecutive: {unknown_consecutive_count}/5]")
            
            # Save debug screenshot only every 5th unknown to reduce I/O
            if unknown_consecutive_count % 5 == 1:
                os.makedirs("debug", exist_ok=True)
                cv2.imwrite("debug/unknown_state.png", img)
            
            # Auto-recovery: try to escape stuck screens
            if unknown_consecutive_count >= 15 and not waiting_for_gameplay:
                if unknown_consecutive_count % 15 == 0:
                    log_warning(f"  [AUTO-RECOVERY] 连续 {unknown_consecutive_count} 次 UNKNOWN，尝试按 B 退出卡住画面...")
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
                if unknown_consecutive_count % 30 == 0:
                    log_warning(f"  [AUTO-RECOVERY] 连续 {unknown_consecutive_count} 次 UNKNOWN，尝试按 Start 打开菜单...")
                    press_button(gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=1.0)
                if unknown_consecutive_count % 60 == 0:
                    log_warning(f"  [AUTO-RECOVERY] 连续 {unknown_consecutive_count} 次 UNKNOWN，尝试重新获取窗口焦点...")
                    import module_macro as _mm
                    _recovery_hwnd = _mm.find_game_window()
                    if _recovery_hwnd:
                        _mm.force_foreground(_recovery_hwnd)
                    time.sleep(2.0)

            # Provide high-visibility diagnostic warnings to help the user resolve focus/obscured screen issues
            if unknown_consecutive_count >= 5 and not waiting_for_gameplay:
                log_warning("==================================================================")
                log_warning("  [DIAGNOSTIC WARNING: GAME SCREEN IS OBSCURED OR LOST FOCUS]")
                log_warning("  The visual state machine is stuck at UNKNOWN.")
                log_warning("  Please verify the following:")
                log_warning("  1. Forza Horizon 6 MUST be running in windowed or borderless mode.")
                log_warning("  2. The game window MUST NOT be minimized (Iconic).")
                log_warning("  3. The game window MUST NOT be covered by VS Code or other windows.")
                log_warning("     (MSS captures exact screen coordinates; if covered, it captures the covering window!)")
                log_warning("  4. Saved diagnostic capture to: debug/unknown_state.png")
                log_warning("==================================================================")
                
            time.sleep(0.5)

      elapsed_hours = (time.time() - start_time) / 3600
      if elapsed_hours >= max_runtime_hours:
          raise RuntimeError(f"State Machine safety timeout: ran for {elapsed_hours:.1f} hours without completing all races.")
    finally:
        # 确保手柄资源在任何退出路径下都被安全处理
        try:
            gamepad.right_trigger(value=0)  # 释放 RT（防止车辆持续加速）
            gamepad.update()
            if owns_gamepad:
                # 仅当自己创建的手柄才完全重置（避免破坏父模块的手柄状态）
                gamepad.reset()
                gamepad.update()
                log_info("Virtual controller safely released.")
            else:
                log_info("RT released. Controller ownership retained by parent module.")
        except Exception:
            pass
        try:
            sct.close()                     # 关闭 MSS 截图上下文
        except Exception:
            pass

if __name__ == "__main__":
    main()
