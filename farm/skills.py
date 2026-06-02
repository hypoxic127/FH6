# -*- coding: utf-8 -*-
"""
FH6_AutoBot EventLab 自动跑图模块 (module_farm_skills.py)
=========================================================
本模块负责"刷技能点"阶段的全部逻辑：

  从暂停菜单出发，自动导航进入 EventLab -> 选择收藏蓝图赛事
  -> 选车 -> 开始比赛 -> 全程按住 RT 加速 -> 检测终点 -> 重启/退出

核心设计 - 视觉状态机 (Visual State Machine)：
  使用 StateDetector (OCR + HSV 颜色分析) 对每帧截图进行状态检测，
  识别当前处于游戏的哪个 UI 状态（菜单标签 / EventLab / 赛道 / 结算画面），
  然后根据状态执行对应的手柄操作。

额外功能:
  - OCR 读取技能点数字，支持断点续跑 (race_state.json)
  - 安全超时（12 小时上限）
  - Rate Event 弹窗自动关闭

架构说明 (P0-3 重构):
  原 main() 中 480 行的 while True 循环已拆分为 FarmStateMachine 类，
  每个状态处理逻辑独立为 <40 行的方法，提高可读性与可维护性。
"""

import datetime
import json
import math
import os
import time

import cv2
import numpy as np
import pytesseract
import vgamepad as vg
from colorama import Fore, Style

import engine.ocr as module_ocr
from engine.state_detect import get_detector
from engine.utils import (
    find_game_window,
    force_foreground,
    get_client_rect,
    get_mss,
    log_error,
    log_info,
    log_success,
    log_warning,
    press_button,
)

# ==========================================
# 辅助函数（无状态）
# ==========================================


def get_matches_needed(current_points: int) -> int:
    """根据当前技能点计算还需要跑多少场比赛。每场约 10 点，目标 999。"""
    max_points = 999
    points_per_match = 10
    matches_needed = math.ceil((max_points - current_points) / points_per_match)
    return 0 if matches_needed < 0 else matches_needed


def archive_match_to_file(match_num: int, remaining_matches: int) -> None:
    """将比赛完成记录归档到 play_archive.txt，包含时间戳和剩余场次。"""
    archive_path = "play_archive.txt"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
    except IOError as e:
        log_error(f"Failed to archive play count to file: {e}")


# ==========================================
# 比赛状态持久化（断点续跑）
# ==========================================

RACE_STATE_FILE = "race_state.json"


def save_race_state(matches_needed: int, matches_completed: int) -> None:
    """保存比赛进度到 JSON 文件，支持断点续跑。"""
    state = {
        "matches_needed": matches_needed,
        "matches_completed": matches_completed,
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(RACE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        log_info(f"Race state saved: {matches_needed} races remaining, {matches_completed} completed")
    except IOError as e:
        log_error(f"Failed to save race state: {e}")


def load_race_state() -> tuple[int, int, str] | None:
    """加载已保存的比赛进度，用于断点续跑。"""
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
    except (IOError, json.JSONDecodeError) as e:
        log_error(f"Failed to load race state: {e}")
        return None


def clear_race_state() -> None:
    """所有比赛完成后清除状态文件。"""
    try:
        if os.path.exists(RACE_STATE_FILE):
            os.remove(RACE_STATE_FILE)
            log_success(f"Race state file cleared ({RACE_STATE_FILE})")
    except OSError as e:
        log_error(f"Failed to clear race state file: {e}")


# ==========================================
# FarmStateMachine — 视觉状态机（P0-3 重构）
# ==========================================


class FarmStateMachine:
    """
    EventLab 自动跑图视觉状态机。

    将原 main() 中 480 行的 while-True 循环拆分为独立方法：
      - tick()                  → 单帧主入口
      - _handle_rate_popup()    → Rate Event 弹窗检测
      - _handle_racing()        → 比赛中（持续 RT + 检测终点）
      - _handle_race_end()      → 比赛结束结算
      - _handle_waiting_next()  → 等待 Next 结算画面
      - _handle_waiting_gameplay() → 等待回到自由漫游
      - _handle_startup_guard() → 启动安全守卫
      - _handle_outside_race_end() → 脚本重启时比赛结束检测
      - _handle_menu_state()    → 菜单状态机分发
    """

    def __init__(self, gamepad: vg.VX360Gamepad, hwnd: int | None, detector, sct) -> None:
        """初始化状态机。

        Args:
            gamepad: 虚拟手柄实例
            hwnd: 游戏窗口句柄
            detector: StateDetector 实例
            sct: MSS 截图实例
        """
        self.gamepad = gamepad
        self.hwnd = hwnd
        self.detector = detector
        self.sct = sct

        # 状态标志
        self.is_racing: bool = False
        self.entering_race: bool = False
        self.waiting_for_next: bool = False
        self.waiting_for_gameplay: bool = False
        self.points_scanned: bool = False

        # 计数器
        self.matches_needed: int = 0
        self.matches_completed: int = 0
        self.unknown_consecutive_count: int = 0
        self.last_points: int | None = None

        # 时间控制
        self.racing_print_timer: float = 0
        self.rect_update_timer: float = 0

        # 缓存的窗口客户区坐标
        self.cw: int = 2560
        self.ch: int = 1440
        self.cx: int = 0
        self.cy: int = 0

        # 标记是否应退出循环
        self.should_exit: bool = False

    def load_saved_state(self) -> None:
        """尝试加载已保存的比赛进度（仅恢复完成场次，技能点重新扫描）。"""
        saved_state = load_race_state()
        if saved_state is not None:
            _, self.matches_completed, last_updated = saved_state
            # 不设置 points_scanned = True，确保启动后先去 CARS 扫描最新技能点
            print(f"\n{Fore.CYAN}{Style.BRIGHT}==========================================")
            print("   [RESUMING FROM SAVED STATE]")
            print(f"   Matches Already Completed: {self.matches_completed}")
            print(f"   Last Updated: {last_updated}")
            print("   (Will scan CARS tab for fresh skill points)")
            print("==========================================\n")

    def _update_client_rect(self) -> None:
        """每 2 秒刷新一次窗口客户区坐标（避免每帧调用）。"""
        now = time.time()
        if now - self.rect_update_timer > 2.0:
            if self.hwnd:
                try:
                    self.cx, self.cy, self.cw, self.ch = get_client_rect(self.hwnd)
                except OSError as e:
                    log_warning(f"Failed to get client rect: {e}. Falling back to primary screen.")
            self.rect_update_timer = now

    def _capture_frame(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """截取游戏画面并缩放。

        Returns:
            (resized_1600x900, original_img) 或 (None, None)
        """
        try:
            monitor = {"top": self.cy, "left": self.cx, "width": self.cw, "height": self.ch}
            screenshot = self.sct.grab(monitor)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            resized = cv2.resize(img, (1600, 900), interpolation=cv2.INTER_AREA)
            return resized, img
        except Exception as e:
            log_error(f"Failed to capture screen: {e}")
            return None, None

    # ===================================================================
    #  弹窗检测
    # ===================================================================

    def _handle_rate_popup(self, resized: np.ndarray) -> bool:
        """检测并关闭 Rate Event 弹窗。返回 True 表示已处理。"""
        try:
            h_frame, w_frame = resized.shape[:2]
            banner_roi = resized[0 : int(h_frame * 0.15), :]
            hsv_banner = cv2.cvtColor(banner_roi, cv2.COLOR_BGR2HSV)
            ygmask = cv2.inRange(hsv_banner, np.array([25, 150, 200]), np.array([45, 255, 255]))
            yg_pixels = cv2.countNonZero(ygmask)
            if yg_pixels > 5000:
                gray_banner = cv2.cvtColor(banner_roi, cv2.COLOR_BGR2GRAY)
                _, thresh_banner = cv2.threshold(gray_banner, 100, 255, cv2.THRESH_BINARY_INV)
                banner_text = pytesseract.image_to_string(thresh_banner).strip().lower()
                if "rate" in banner_text or "event" in banner_text:
                    log_success(f"[Rate Event] Detected popup (yellow pixels: {yg_pixels}). Pressing A to dismiss...")
                    press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.0)
                    return True
        except Exception:
            pass
        return False

    # ===================================================================
    #  比赛状态处理
    # ===================================================================

    def _handle_racing(self, resized: np.ndarray) -> None:
        """比赛中：持续按住 RT + 扫描 RACE_END。"""
        self.gamepad.right_trigger(value=255)
        self.gamepad.update()

        if time.time() - self.racing_print_timer > 2.0:
            log_info("[RACING] Holding Right Trigger (RT) to accelerate... Scanning for race end...")
            self.racing_print_timer = time.time()

        racing_state = self.detector.detect(resized, mode="racing")
        if racing_state == "RACE_END":
            self._handle_race_end()

        time.sleep(0.1)

    def _handle_race_end(self) -> None:
        """比赛结束：释放 RT、更新计数器、决定重启或退出。"""
        self.gamepad.right_trigger(value=0)
        self.gamepad.update()
        time.sleep(0.5)

        self.matches_completed += 1
        remaining_matches = max(0, self.matches_needed - 1)
        archive_match_to_file(self.matches_completed, remaining_matches)

        print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
        print("   [MATCH PLAYED & SETTLED SUCCESSFULLY]  ")
        print(f"   Match Number Completed: {self.matches_completed}")
        print(f"   Original Matches Needed: {self.matches_needed}")
        print(f"   Remaining Matches Needed: {remaining_matches}")
        print("==========================================\n")

        self.matches_needed = remaining_matches
        save_race_state(self.matches_needed, self.matches_completed)

        if remaining_matches > 0:
            log_success(f"Race finished! {remaining_matches} races remaining, pressing X to restart race...")
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_X, delay=0)
            time.sleep(1.0)
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
            self.is_racing = False
            self.entering_race = True  # 防止过渡画面误识别为菜单标签（如 STORE）触发 RB
            time.sleep(3.0)
        else:
            log_success(f"Race finished! All {self.matches_completed} races completed! Pressing A to view rewards...")
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
            self.is_racing = False
            self.waiting_for_next = True
            log_info("Waiting for rewards screen to transition to Next screen...")

    def _handle_waiting_next(self, resized: np.ndarray) -> None:
        """等待 Next 结算画面，按 B 退出。"""
        next_state = self.detector.detect(resized, mode="racing")
        if next_state == "NEXT_SCREEN":
            log_success("Rewards settled! Detected Next screen. Pressing B to exit...")
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=0)
            self.waiting_for_next = False
            self.waiting_for_gameplay = True
            log_info("Waiting for game window to return to gameplay...")
        time.sleep(0.2)

    def _handle_waiting_gameplay(self, resized: np.ndarray) -> None:
        """等待回到自由漫游，按 START 打开暂停菜单。"""
        play_state = self.detector.detect(resized, mode="racing")
        if play_state == "PLAYING":
            log_success("Returned to gameplay! Pressing START to open pause menu...")
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=0)
            self.waiting_for_gameplay = False
            time.sleep(2.5)

            if self.matches_needed <= 0:
                clear_race_state()
                print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                print(f"{Fore.GREEN}{Style.BRIGHT}   [ALL TARGET MATCHES SUCCESSFULLY COMPLETED] ")
                print(f"{Fore.GREEN}{Style.BRIGHT}   Skill point goal has been successfully reached! ")
                print("   Returned to Menu successfully. ")
                print(f"{Fore.GREEN}{Style.BRIGHT}==========================================\n")
                self.should_exit = True
        time.sleep(0.2)

    # ===================================================================
    #  启动守卫和恢复逻辑
    # ===================================================================

    def _handle_startup_guard(self, resized: np.ndarray) -> bool:
        """如果启动时在自由漫游画面，自动按 START 打开菜单。返回 True 表示已处理。"""
        if not self.points_scanned and not self.is_racing and not self.waiting_for_gameplay:
            startup_state = self.detector.detect(resized, mode="racing")
            if startup_state == "PLAYING":
                log_success("[STARTUP SAFEGUARD] Detected gameplay screen. Pressing START to open pause menu...")
                press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=2.5)
                return True
        return False

    def _handle_outside_race_end(self, resized: np.ndarray) -> bool:
        """检测非比赛模式下的 RACE_END（脚本重启恢复场景）。返回 True 表示已处理。"""
        if self.points_scanned and not self.is_racing and not self.waiting_for_next and not self.waiting_for_gameplay:
            outside_state = self.detector.detect(resized, mode="racing")
            if outside_state == "RACE_END":
                log_success("Detected race end outside racing mode. Handling as race end...")
                self.matches_completed += 1
                remaining_matches = max(0, self.matches_needed - 1)
                archive_match_to_file(self.matches_completed, remaining_matches)

                print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                print("   [MATCH PLAYED & SETTLED SUCCESSFULLY]  ")
                print(f"   Match Number Completed: {self.matches_completed}")
                print(f"   Original Matches Needed: {self.matches_needed}")
                print(f"   Remaining Matches Needed: {remaining_matches}")
                print("==========================================\n")

                self.matches_needed = remaining_matches
                save_race_state(self.matches_needed, self.matches_completed)

                if remaining_matches > 0:
                    log_success(f"{remaining_matches} races remaining, pressing X to restart race...")
                    press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_X, delay=1.0)
                    press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                    self.entering_race = True  # 防止过渡画面误识别为菜单标签
                    time.sleep(3.0)
                else:
                    log_success(f"All {self.matches_completed} races completed! Pressing A to view rewards...")
                    press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
                    self.waiting_for_next = True
                    log_info("Waiting for Next screen...")
                return True
        return False

    # ===================================================================
    #  菜单状态处理
    # ===================================================================

    def _handle_menu_state(self, state: str, img: np.ndarray) -> None:
        """根据 StateDetector 返回的菜单状态执行对应操作。

        Args:
            state: 检测到的状态字符串
            img: 原始分辨率截图（供 OCR 使用）
        """
        if state != "UNKNOWN":
            self.unknown_consecutive_count = 0
            if self.waiting_for_gameplay:
                log_success("Successfully re-entered the game menu!")
                self.waiting_for_gameplay = False

        # 安全守卫：初始 OCR 扫描前不允许进入子菜单
        if not self.points_scanned:
            if state in ["EVENTLAB_MENU", "EVENTS_SUBMENU", "FAVORITES_LIST", "RACE_READY", "CAR_SELECT", "PRE_RACE"]:
                log_warning(
                    f"[SAFETY GUARD] Active state: {state}, but skill points NOT scanned yet! Pressing B to back out..."
                )
                press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.5)
                return

        if state == "CARS" and not self.entering_race:
            self._on_cars_tab(img)
        elif state in ["CAMPAIGN", "MY HORIZON", "ONLINE", "STORE"] and not self.entering_race:
            self._on_other_tab(state)
        elif state in ["CREATIVE_HUB", "CREATIVE HUB"] and not self.entering_race:
            self._on_creative_hub()
        elif state == "EVENTLAB_MENU":
            self._on_eventlab_menu()
        elif state == "EVENTS_SUBMENU":
            self._on_events_submenu()
        elif state == "FAVORITES_LIST":
            self._on_favorites_list()
        elif state in ["RACE_READY", "choose"]:
            self._on_race_ready()
        elif state == "CAR_SELECT":
            self._on_car_select()
        elif state == "PRE_RACE":
            self._on_pre_race()
        else:
            self._on_unknown(state)

    def _on_cars_tab(self, img: np.ndarray) -> None:
        """CARS 标签页：OCR 读取技能点并决定后续操作。"""
        print(f"{Fore.GREEN}{Style.BRIGHT}[STATE: CARS]{Style.RESET_ALL} Arrived at CARS tab! Scanning skill points...")
        detected_points = module_ocr.read_skill_points(img)
        if detected_points is not None:
            self.matches_needed = get_matches_needed(detected_points)
            print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
            print("   [SKILL POINTS SCAN SUCCESS on CARS TAB] ")
            print(f"   Current Points: {detected_points} / 999")
            print(f"   Matches Needed: {self.matches_needed} (10 pts/match)")
            print("==========================================\n")
            self.last_points = detected_points
            self.points_scanned = True
            save_race_state(self.matches_needed, self.matches_completed)

            if self.matches_needed <= 0:
                print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
                print("   [GOAL ALREADY REACHED] ")
                print(f"   Current points {detected_points} >= 999. No matches needed!")
                print("==========================================\n")
                self.should_exit = True
                return

            print(f"{Fore.YELLOW}[STATE: CARS]{Style.RESET_ALL} Shifting right (RB)...")
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
        else:
            if not self.points_scanned:
                log_warning(
                    "OCR failed to read skill points on CARS tab. Enforcing initial scan, retrying on next frame..."
                )
                time.sleep(0.5)
            else:
                log_warning(f"OCR failed. Using current matches_needed: {self.matches_needed}")
                print(f"{Fore.YELLOW}[STATE: CARS]{Style.RESET_ALL} Shifting right (RB)...")
                press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)

    def _on_other_tab(self, state: str) -> None:
        """非目标标签页：按 RB 翻页。"""
        print(f"{Fore.YELLOW}[STATE: {state}]{Style.RESET_ALL} Not in Creative Hub, shifting right (RB)...")
        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)

    def _on_creative_hub(self) -> None:
        """Creative Hub 标签页：进入 EventLab。"""
        if not self.points_scanned:
            print(
                f"{Fore.YELLOW}[STATE: CREATIVE HUB]{Style.RESET_ALL} "
                f"Initial points not scanned yet! "
                f"Bypassing, shifting right (RB)..."
            )
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)
        else:
            print(
                f"{Fore.GREEN}{Style.BRIGHT}"
                f"[STATE: CREATIVE_HUB]{Style.RESET_ALL} "
                f"Arrived at Creative Hub! Entering EventLab (A)..."
            )
            press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)

    def _on_eventlab_menu(self) -> None:
        """EventLab 菜单：选择 Play Event。"""
        print(
            f"{Fore.GREEN}{Style.BRIGHT}"
            f"[STATE: EVENTLAB_MENU]{Style.RESET_ALL} "
            f"Entering EventLab menu, selecting Play Event (A)..."
        )
        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=1.5)

    def _on_events_submenu(self) -> None:
        """Events 子菜单：按 RB 找 My Favorites。"""
        print(f"{Fore.YELLOW}[STATE: EVENTS_SUBMENU]{Style.RESET_ALL} Shifting right (RB) to find My Favorites...")
        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, delay=0.5)

    def _on_favorites_list(self) -> None:
        """My Favorites 列表：选中蓝图并进入。"""
        self.entering_race = True
        print(
            f"{Fore.GREEN}{Style.BRIGHT}"
            f"[STATE: FAVORITES_LIST]{Style.RESET_ALL} "
            f"Arrived at My Favorites! Selecting Event (A)..."
        )
        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)

    def _on_race_ready(self) -> None:
        """比赛类型选择：确保 Solo 选中并启动。"""
        print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
        print("   [STATE: RACE_READY] Arrived at Choose Race Type!")
        print("   Ensuring SOLO is selected and launching...")
        print("==========================================\n")

        for button in [vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT]:
            for _ in range(2):
                press_button(self.gamepad, button, delay=0.3)

        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
        print(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} SOLO selected! Transitioning to Car Selection...")
        time.sleep(1.5)

    def _on_car_select(self) -> None:
        """车辆选择：直接确认当前车辆。"""
        print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
        print("   [STATE: CAR_SELECT] Confirming current car (A)...")
        print("==========================================\n")
        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=3.0)

    def _on_pre_race(self) -> None:
        """赛事准备界面：按 A 开始比赛，切换到 racing 模式。"""
        print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================")
        print("   [STATE: PRE_RACE] Arrived at Pre-Race Lobby!")
        print("   Launching Start Race Event...")
        print("==========================================\n")

        press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_A, delay=0)
        log_success("Start Race Event selected! Transitioning to racing mode...")
        self.is_racing = True
        self.entering_race = False
        self.racing_print_timer = time.time()
        time.sleep(3.0)

    def _on_unknown(self, state: str) -> None:
        """UNKNOWN 状态：等待 UI 加载 + 自动恢复。"""
        self.unknown_consecutive_count += 1
        print(
            f"{Fore.BLUE}[STATE: {state}]{Style.RESET_ALL} "
            f"Waiting for UI to load... "
            f"[Consecutive: {self.unknown_consecutive_count}/5]"
        )

        if self.unknown_consecutive_count % 5 == 1:
            os.makedirs("debug", exist_ok=True)
            # 使用截图保存时需要重新截取
            try:
                resized, img = self._capture_frame()
                if img is not None:
                    cv2.imwrite("debug/unknown_state.png", img)
            except Exception:
                pass

        # 自动恢复
        if self.unknown_consecutive_count >= 15 and not self.waiting_for_gameplay:
            if self.unknown_consecutive_count % 15 == 0:
                log_warning(
                    f"  [AUTO-RECOVERY] 连续 {self.unknown_consecutive_count} 次 UNKNOWN，尝试按 B 退出卡住画面..."
                )
                press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_B, delay=1.0)
            if self.unknown_consecutive_count % 30 == 0:
                log_warning("  [AUTO-RECOVERY] 尝试按 Start 打开菜单...")
                press_button(self.gamepad, vg.XUSB_BUTTON.XUSB_GAMEPAD_START, delay=1.0)
            if self.unknown_consecutive_count % 60 == 0:
                log_warning("  [AUTO-RECOVERY] 尝试重新获取窗口焦点...")
                recovery_hwnd = find_game_window()
                if recovery_hwnd:
                    force_foreground(recovery_hwnd)
                time.sleep(2.0)

        # 诊断警告
        if self.unknown_consecutive_count >= 5 and not self.waiting_for_gameplay:
            log_warning("=" * 66)
            log_warning("  [DIAGNOSTIC WARNING: GAME SCREEN IS OBSCURED OR LOST FOCUS]")
            log_warning("  Please verify: game is windowed/borderless, not minimized, not covered.")
            log_warning("=" * 66)

        time.sleep(0.5)

    # ===================================================================
    #  主循环单帧处理
    # ===================================================================

    def tick(self) -> None:
        """处理单帧截图，驱动状态机转换。

        调用者应在 while-not-should_exit 循环中反复调用此方法。
        """
        self._update_client_rect()

        resized, img = self._capture_frame()
        if resized is None:
            time.sleep(0.5)
            return

        # Rate Event 弹窗
        if self._handle_rate_popup(resized):
            return

        # 比赛中
        if self.is_racing:
            self._handle_racing(resized)
            return

        # 等待 Next 画面
        if self.waiting_for_next:
            self._handle_waiting_next(resized)
            return

        # 等待回到自由漫游
        if self.waiting_for_gameplay:
            self._handle_waiting_gameplay(resized)
            return

        # 启动安全守卫
        if self._handle_startup_guard(resized):
            return

        # 脚本重启恢复
        if self._handle_outside_race_end(resized):
            return

        # 菜单状态机
        state = self.detector.detect(resized, mode="menu")
        self._handle_menu_state(state, img)


# ==========================================
# 入口函数（保持向后兼容）
# ==========================================


def main(gamepad: vg.VX360Gamepad | None = None) -> None:
    """
    EventLab 自动跑图入口。

    初始化 Tesseract / GamePad / Window 等依赖，然后委托给
    FarmStateMachine 驱动状态循环。
    """
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}==================================================")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}   FORZA HORIZON 6 AUTOMATED RACE ENTRY - STATE MACHINE")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    # 1. Initialize Tesseract
    module_ocr.setup_tesseract()

    print(f"\n{Fore.YELLOW}==================================================")
    print("   OCR-ONLY SKILL POINTS SCANNER")
    print("   (Must visit CARS menu tab to scan points initially)")
    print(f"=================================================={Style.RESET_ALL}")

    # 2. Initialize State Detector (单例)
    detector = get_detector()
    log_info("StateDetector initialized (Color Histogram + OCR hybrid)")

    # 3. Game Window Check & Activation
    hwnd = find_game_window()
    if hwnd:
        log_success("Forza Horizon 6 game window detected.")
        force_foreground(hwnd)
    else:
        log_warning("Forza Horizon 6 window not found! Running in fallback mode.")

    # 4. Gamepad Initialization
    owns_gamepad = False
    if gamepad is None:
        log_info("Initializing virtual Xbox 360 controller...")
        try:
            gamepad = vg.VX360Gamepad()
            owns_gamepad = True
            log_success("Virtual controller successfully initialized.")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize virtual controller: {e}") from e
    else:
        log_info("Reusing existing virtual controller from parent module.")

    # 倒计时（无自动聚焦时）
    if not hwnd:
        print()
        for i in range(5, 0, -1):
            print(
                f"\r{Fore.YELLOW}[WAIT]{Style.RESET_ALL} Please switch to the Forza Horizon 6 window... {i}s remaining",
                end="",
                flush=True,
            )
            time.sleep(1.0)
        print("\n")

    log_info("Starting Real-time Visual State Machine loop (Press Ctrl+C to terminate)...")

    # 5. 创建状态机并加载保存的进度
    sct = get_mss()
    fsm = FarmStateMachine(gamepad, hwnd, detector, sct)
    fsm.load_saved_state()

    max_runtime_hours = 12
    start_time = time.time()

    try:
        while not fsm.should_exit:
            elapsed_hours = (time.time() - start_time) / 3600
            if elapsed_hours >= max_runtime_hours:
                break
            fsm.tick()

        elapsed_hours = (time.time() - start_time) / 3600
        if elapsed_hours >= max_runtime_hours:
            raise RuntimeError(
                f"State Machine safety timeout: ran for {elapsed_hours:.1f} hours without completing all races."
            )
    finally:
        try:
            gamepad.right_trigger(value=0)
            gamepad.update()
            if owns_gamepad:
                gamepad.reset()
                gamepad.update()
                log_info("Virtual controller safely released.")
            else:
                log_info("RT released. Controller ownership retained by parent module.")
        except Exception:
            pass
        # 注意: 不关闭 sct (MSS 全局单例)


if __name__ == "__main__":
    main()
