# -*- coding: utf-8 -*-
"""
Interactive ROI Annotation Tool v2
===================================
Drag to draw boxes on game screenshot.
Outputs both full-screen % and CARD_CROP % coordinates.

Controls:
  Drag     = draw box
  R        = reset all boxes
  Q / ESC  = quit
"""

import sys
import os
import cv2
import numpy as np

os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import module_macro
import module_ocr

# Global state
drawing = False
start_x, start_y = 0, 0
current_rect = None
all_rects = []
base_image = None
img_w, img_h = 1600, 900
cursor_cx, cursor_cy = 0, 0
has_cursor = False
CROP_W = module_ocr.CARD_CROP_W
CROP_H = module_ocr.CARD_CROP_H


def mouse_callback(event, x, y, flags, param):
    global drawing, start_x, start_y, current_rect

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        start_x, start_y = x, y
        current_rect = None
    elif event == cv2.EVENT_MOUSEMOVE and drawing:
        current_rect = (start_x, start_y, x, y)
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        if abs(x - start_x) > 5 and abs(y - start_y) > 5:
            rx1 = min(start_x, x)
            ry1 = min(start_y, y)
            rx2 = max(start_x, x)
            ry2 = max(start_y, y)
            rect = (rx1, ry1, rx2, ry2)
            all_rects.append(rect)
            print_rect_info(rect, len(all_rects))
        current_rect = None


def print_rect_info(rect, idx):
    rx1, ry1, rx2, ry2 = rect
    rw = rx2 - rx1
    rh = ry2 - ry1

    # === Full-screen percentage (relative to 1600x900) ===
    fs_x1 = rx1 / img_w
    fs_y1 = ry1 / img_h
    fs_x2 = rx2 / img_w
    fs_y2 = ry2 / img_h

    print(f"\n{'='*60}")
    print(f"  [BOX #{idx}]  Pixels: ({rx1},{ry1}) -> ({rx2},{ry2})  [{rw}x{rh}]")
    print(f"{'='*60}")

    # Full-screen %
    print(f"\n  --- FULL SCREEN % (for raw_img / resized) ---")
    print(f"  Height: {fs_y1:.2f} -> {fs_y2:.2f}   (h*{fs_y1:.2f} : h*{fs_y2:.2f})")
    print(f"  Width:  {fs_x1:.2f} -> {fs_x2:.2f}   (w*{fs_x1:.2f} : w*{fs_x2:.2f})")
    print(f"  Code:  roi = image[int(h*{fs_y1:.2f}):int(h*{fs_y2:.2f}), int(w*{fs_x1:.2f}):int(w*{fs_x2:.2f})]")

    # CARD_CROP % (only if cursor was detected)
    if has_cursor:
        card_x1 = max(0, cursor_cx - CROP_W // 2)
        card_y1 = max(0, cursor_cy - CROP_H // 2)
        card_w = CROP_W
        card_h = CROP_H

        pct_x1 = (rx1 - card_x1) / card_w
        pct_y1 = (ry1 - card_y1) / card_h
        pct_x2 = (rx2 - card_x1) / card_w
        pct_y2 = (ry2 - card_y1) / card_h

        print(f"\n  --- CARD_CROP % (cursor={cursor_cx},{cursor_cy}) ---")
        print(f"  Height: {pct_y1:.2f} -> {pct_y2:.2f}   (card_h*{pct_y1:.2f} : card_h*{pct_y2:.2f})")
        print(f"  Width:  {pct_x1:.2f} -> {pct_x2:.2f}   (card_w*{pct_x1:.2f} : card_w*{pct_x2:.2f})")
        print(f"  Code:  roi = card[int(card_h*{pct_y1:.2f}):int(card_h*{pct_y2:.2f}), int(card_w*{pct_x1:.2f}):int(card_w*{pct_x2:.2f})]")

    print(f"{'='*60}")


def main():
    global base_image, cursor_cx, cursor_cy, has_cursor, all_rects, current_rect
    global img_w, img_h

    print("\n==================================================")
    print("   ROI Annotation Tool v2")
    print("   Outputs: full-screen % + CARD_CROP %")
    print("   Drag=draw  R=reset  Q/ESC=quit")
    print("==================================================\n")

    hwnd = module_macro.find_game_window()
    if not hwnd:
        print("[ERROR] Game window not found!")
        sys.exit(1)
    module_macro.force_foreground(hwnd)

    print("  3 seconds...")
    import time; time.sleep(3)

    resized, _, _, _, _ = module_macro.capture_screenshot(hwnd)
    if resized is None:
        print("[ERROR] Screenshot failed!")
        sys.exit(1)

    img_h, img_w = resized.shape[:2]
    print(f"  Image: {img_w}x{img_h}")

    cursor_pos = module_ocr.find_cursor_position(resized)
    if cursor_pos:
        cursor_cx, cursor_cy = cursor_pos
        has_cursor = True
        print(f"  Cursor: ({cursor_cx}, {cursor_cy})")
    else:
        has_cursor = False
        print("  [INFO] No cursor detected (CARD_CROP % disabled)")

    base_image = resized.copy()

    cv2.namedWindow("ROI Annotation Tool v2", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("ROI Annotation Tool v2", 1600, 900)
    cv2.setMouseCallback("ROI Annotation Tool v2", mouse_callback)

    colors = [
        (0, 255, 255), (255, 0, 255), (0, 165, 255),
        (255, 255, 0), (0, 255, 0), (0, 0, 255),
    ]

    while True:
        vis = base_image.copy()

        # Draw CARD_CROP if cursor detected
        if has_cursor:
            cx1 = max(0, cursor_cx - CROP_W // 2)
            cy1 = max(0, cursor_cy - CROP_H // 2)
            cx2 = min(img_w, cursor_cx + CROP_W // 2)
            cy2 = min(img_h, cursor_cy + CROP_H // 2)
            for i in range(cx1, cx2, 10):
                cv2.line(vis, (i, cy1), (min(i+5, cx2), cy1), (128,128,128), 1)
                cv2.line(vis, (i, cy2), (min(i+5, cx2), cy2), (128,128,128), 1)
            for i in range(cy1, cy2, 10):
                cv2.line(vis, (cx1, i), (cx1, min(i+5, cy2)), (128,128,128), 1)
                cv2.line(vis, (cx2, i), (cx2, min(i+5, cy2)), (128,128,128), 1)
            cv2.drawMarker(vis, (cursor_cx, cursor_cy), (0, 255, 0), cv2.MARKER_CROSS, 20, 1)

        # Draw saved rects
        for i, (rx1, ry1, rx2, ry2) in enumerate(all_rects):
            color = colors[i % len(colors)]
            cv2.rectangle(vis, (rx1, ry1), (rx2, ry2), color, 2)
            cv2.putText(vis, f"#{i+1}", (rx1+3, ry1-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # Draw current drag
        if current_rect:
            sx, sy, ex, ey = current_rect
            cv2.rectangle(vis, (sx, sy), (ex, ey), (0, 255, 0), 1)
            # Show live size
            dw, dh = abs(ex-sx), abs(ey-sy)
            cv2.putText(vis, f"{dw}x{dh}", (min(sx,ex)+5, min(sy,ey)-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        cv2.putText(vis, "Drag=draw | R=reset | Q=quit", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("ROI Annotation Tool v2", vis)
        key = cv2.waitKey(30) & 0xFF

        if key == ord('q') or key == 27:
            break
        elif key == ord('r'):
            all_rects.clear()
            print("\n  [RESET] All boxes cleared")

    cv2.destroyAllWindows()
    print("\nDone!")


if __name__ == "__main__":
    main()
