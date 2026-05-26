# -*- coding: utf-8 -*-
"""
可视化所有检测函数的实际采样区域
"""

import sys
import os
import time
import cv2
import numpy as np

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

def draw_all_regions(image, cx, cy):
    """在截图上画出所有函数的检测区域"""
    vis = image.copy()
    h, w = vis.shape[:2]

    CROP_W = module_ocr.CARD_CROP_W  # 350
    CROP_H = module_ocr.CARD_CROP_H  # 300

    # 卡片裁剪区域的绝对坐标
    card_x1 = max(0, cx - CROP_W // 2)
    card_x2 = min(w, cx + CROP_W // 2)
    card_y1 = max(0, cy - CROP_H // 2)
    card_y2 = min(h, cy + CROP_H // 2)
    card_w = card_x2 - card_x1
    card_h = card_y2 - card_y1

    # ============================================
    # 1. CARD_CROP 总裁剪区 (白色虚线)
    # ============================================
    for i in range(0, card_w, 10):
        x = card_x1 + i
        cv2.line(vis, (x, card_y1), (min(x + 5, card_x2), card_y1), (255, 255, 255), 1)
        cv2.line(vis, (x, card_y2), (min(x + 5, card_x2), card_y2), (255, 255, 255), 1)
    for i in range(0, card_h, 10):
        y = card_y1 + i
        cv2.line(vis, (card_x1, y), (card_x1, min(y + 5, card_y2)), (255, 255, 255), 1)
        cv2.line(vis, (card_x2, y), (card_x2, min(y + 5, card_y2)), (255, 255, 255), 1)

    # ============================================
    # 2. check_new_tag_only: h65%-73%, w76%-87% (黄色)
    # ============================================
    new_y1 = card_y1 + int(card_h * 0.65)
    new_y2 = card_y1 + int(card_h * 0.73)
    new_x1 = card_x1 + int(card_w * 0.76)
    new_x2 = card_x1 + int(card_w * 0.87)
    cv2.rectangle(vis, (new_x1, new_y1), (new_x2, new_y2), (0, 255, 255), 2)  # 黄色
    cv2.putText(vis, "NEW tag (yellow)", (new_x1 + 2, new_y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    # ============================================
    # 3. check_is_high_class: h73%-82%, w67%-87% (紫色)
    # ============================================
    pi_y1 = card_y1 + int(card_h * 0.73)
    pi_y2 = card_y1 + int(card_h * 0.82)
    pi_x1 = card_x1 + int(card_w * 0.67)
    pi_x2 = card_x1 + int(card_w * 0.87)
    cv2.rectangle(vis, (pi_x1, pi_y1), (pi_x2, pi_y2), (255, 0, 255), 2)  # 紫色
    cv2.putText(vis, "PI badge (purple)", (pi_x1 + 2, pi_y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

    # ============================================
    # 4. has_cell_below: CARD_CROP h87%-153%, w13%-88% (橙色)
    # ============================================
    by1 = max(0, int(card_y1 + card_h * 0.87))
    by2 = min(h, int(card_y1 + card_h * 1.53))
    bx1 = max(0, int(card_x1 + card_w * 0.13))
    bx2 = min(w, int(card_x1 + card_w * 0.88))
    cv2.rectangle(vis, (bx1, by1), (bx2, by2), (0, 165, 255), 2)  # 橙色
    cv2.putText(vis, "cell_below (orange)", (bx2 + 5, by1 + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)

    # ============================================
    # 5. empty_slot: CARD_CROP h87%-153%, w13%-88% (红色)
    # ============================================
    ey1 = max(0, int(card_y1 + card_h * 0.87))
    ey2 = min(h, int(card_y1 + card_h * 1.53))
    ex1 = max(0, int(card_x1 + card_w * 0.13))
    ex2 = min(w, int(card_x1 + card_w * 0.88))
    # 红色虚线画在橙色内侧（偏移2px）以示区分
    for i in range(ey1, ey2, 8):
        cv2.line(vis, (ex1+3, i), (ex1+3, min(i+4, ey2)), (0, 0, 255), 1)
        cv2.line(vis, (ex2-3, i), (ex2-3, min(i+4, ey2)), (0, 0, 255), 1)
    for i in range(ex1, ex2, 8):
        cv2.line(vis, (i, ey1+3), (min(i+4, ex2), ey1+3), (0, 0, 255), 1)
        cv2.line(vis, (i, ey2-3), (min(i+4, ex2), ey2-3), (0, 0, 255), 1)
    cv2.putText(vis, "empty_slot (red dashed)", (ex1 + 5, ey2 + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    # ============================================
    # 6. 光标中心十字 (绿色)
    # ============================================
    cv2.drawMarker(vis, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 30, 2)
    cv2.putText(vis, f"cursor ({cx},{cy})", (cx + 20, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

    # ============================================
    # 图例
    # ============================================
    legend_x, legend_y = 10, h - 130
    legend_items = [
        ((255, 255, 255), "CARD_CROP 350x300 (white dashed)"),
        ((0, 255, 255),   "check_new_tag_only: h65-73%, w76-87% (yellow)"),
        ((255, 0, 255),   "check_is_high_class: h73-82%, w67-87% (purple)"),
        ((0, 165, 255),   "has_cell_below: h87-153%, w13-88% (orange)"),
        ((0, 0, 255),     "empty_slot: h87-153%, w13-88% (red dashed)"),
    ]
    # 半透明背景
    overlay = vis.copy()
    cv2.rectangle(overlay, (legend_x - 5, legend_y - 15),
                  (legend_x + 450, legend_y + len(legend_items) * 22 + 5),
                  (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, vis, 0.4, 0, vis)

    for i, (color, text) in enumerate(legend_items):
        y = legend_y + i * 22
        cv2.rectangle(vis, (legend_x, y), (legend_x + 15, y + 12), color, -1)
        cv2.putText(vis, text, (legend_x + 22, y + 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

    return vis


def main():
    print(f"\n{Fore.CYAN}==================================================")
    print(f"   [TEST] Draw all detection regions")
    print(f"=================================================={Style.RESET_ALL}\n")

    hwnd = module_macro.find_game_window()
    if not hwnd:
        module_macro.log_error("Game window not found!")
        sys.exit(1)
    module_macro.force_foreground(hwnd)

    print(f"  {Fore.YELLOW}3 seconds...{Style.RESET_ALL}")
    time.sleep(3)

    resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
    if resized is None:
        module_macro.log_error("Screenshot failed!")
        sys.exit(1)

    cursor_pos = module_ocr.find_cursor_position(resized)
    if cursor_pos is None:
        module_macro.log_error("Cursor not detected!")
        sys.exit(1)

    cx, cy = cursor_pos
    print(f"  Cursor: ({cx}, {cy})")

    result = draw_all_regions(resized, cx, cy)
    out_path = "debug_all_regions.png"
    cv2.imwrite(out_path, result)
    print(f"\n  {Fore.GREEN}[SAVED] {out_path}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}Done!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
