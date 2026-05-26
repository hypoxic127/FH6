# -*- coding: utf-8 -*-
"""
快速测试: find_cursor_position 形状过滤修复
"""

import sys
import os
import time
import cv2
import numpy as np

# 强制 UTF-8 输出
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from colorama import init, Fore, Style

import module_macro
import module_ocr

init(autoreset=True)

def main():
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==================================================")
    print(f"   [TEST] find_cursor_position shape filter fix")
    print(f"   Prerequisite: Game on garage grid screen")
    print(f"{Fore.CYAN}{Style.BRIGHT}=================================================={Style.RESET_ALL}\n")

    # 1. Find game window
    hwnd = module_macro.find_game_window()
    if not hwnd:
        module_macro.log_error("Game window not found!")
        sys.exit(1)
    module_macro.force_foreground(hwnd)
    module_macro.log_success("Game window found")

    print(f"\n  {Fore.YELLOW}3 seconds before screenshot...{Style.RESET_ALL}")
    time.sleep(3)

    # 2. Test 3 screenshots
    for attempt in range(1, 4):
        print(f"\n{'='*60}")
        print(f"  [Screenshot {attempt}/3]")
        print(f"{'='*60}")

        resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
        if resized is None:
            module_macro.log_error("Screenshot failed!")
            time.sleep(1.0)
            continue

        h, w = resized.shape[:2]
        print(f"  Image size: {w}x{h}")

        # 3. Call find_cursor_position
        print(f"\n  {Fore.CYAN}--- find_cursor_position result ---{Style.RESET_ALL}")
        cursor_pos = module_ocr.find_cursor_position(resized)

        if cursor_pos is not None:
            cx, cy = cursor_pos
            print(f"\n  {Fore.GREEN}[OK] Cursor detected: (cx={cx}, cy={cy}){Style.RESET_ALL}")

            # 4. Test has_cell_below
            print(f"\n  {Fore.CYAN}--- has_cell_below result ---{Style.RESET_ALL}")
            has_below = module_ocr.has_cell_below(resized, cx, cy)
            status = f"{Fore.GREEN}[OK] has car" if has_below else f"{Fore.RED}[X] empty"
            print(f"  Below cell: {status}{Style.RESET_ALL}")

            # 5. Debug image
            debug_img = resized.copy()
            cv2.drawMarker(debug_img, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 40, 2)
            crop_w, crop_h = 175, 150
            cv2.rectangle(debug_img,
                          (max(0, cx - crop_w), max(0, cy - crop_h)),
                          (min(w, cx + crop_w), min(h, cy + crop_h)),
                          (0, 255, 0), 2)
            below_y = cy + 210
            if below_y < h - 30:
                cv2.drawMarker(debug_img, (cx, below_y), (0, 165, 255), cv2.MARKER_CROSS, 30, 2)
                cv2.rectangle(debug_img,
                              (max(0, cx - 20), max(0, below_y - 20)),
                              (min(w, cx + 20), min(h, below_y + 20)),
                              (0, 165, 255), 2)

            debug_path = f"debug_cursor_test_{attempt}.png"
            cv2.imwrite(debug_path, debug_img)
            print(f"\n  [SAVED] {debug_path}")

        else:
            print(f"\n  {Fore.RED}[FAIL] Cursor not detected: no valid contour{Style.RESET_ALL}")
            debug_path = f"debug_cursor_fail_{attempt}.png"
            cv2.imwrite(debug_path, resized)
            print(f"  [SAVED] {debug_path}")

        # 6. Show all green contours
        print(f"\n  {Fore.CYAN}--- All green contours ---{Style.RESET_ALL}")
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, module_ocr.HSV_GREEN_CURSOR_LOWER, module_ocr.HSV_GREEN_CURSOR_UPPER)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid = [c for c in contours if cv2.contourArea(c) >= 300]
        valid.sort(key=cv2.contourArea, reverse=True)

        print(f"  Total contours: {len(contours)}, Valid (area>=300): {len(valid)}")
        for i, c in enumerate(valid[:10]):
            x, y, cw, ch = cv2.boundingRect(c)
            area = cv2.contourArea(c)
            aspect = max(cw, ch) / max(min(cw, ch), 1)
            ccx, ccy = x + cw // 2, y + ch // 2

            pass_aspect = aspect <= 4.0
            pass_min_dim = min(cw, ch) >= 50
            pass_y_pos = ccy > 150
            all_pass = pass_aspect and pass_min_dim and pass_y_pos

            status = f"{Fore.GREEN}PASS" if all_pass else f"{Fore.RED}FAIL"
            reasons = []
            if not pass_aspect:
                reasons.append(f"ratio {aspect:.1f}>4")
            if not pass_min_dim:
                reasons.append(f"min_dim {min(cw,ch)}<50")
            if not pass_y_pos:
                reasons.append(f"y={ccy}<=150")
            reason_str = f" ({', '.join(reasons)})" if reasons else ""

            print(f"    [{i+1}] {cw}x{ch} at ({ccx},{ccy}) area={area:.0f} ratio={aspect:.1f} -> {status}{reason_str}{Style.RESET_ALL}")

        time.sleep(2.0)

    print(f"\n{Fore.GREEN}{Style.BRIGHT}Test complete!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
