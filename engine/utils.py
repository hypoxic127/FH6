# -*- coding: utf-8 -*-
"""
FH6_AutoBot 公共工具模块 (utils.py)
====================================
提取 module_macro.py 和 module_farm_skills.py 共享的基础函数，包括：

  - 日志输出（带颜色的 INFO / SUCCESS / WARNING / ERROR）
  - 游戏窗口操作（查找窗口、强制前台、获取客户区坐标）
  - 虚拟手柄按键封装（按下→释放→延迟）
  - 屏幕截图单例（MSS，避免多个模块各自创建 GDI 句柄导致资源泄露）
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes

from colorama import Fore, Style, init

# ==========================================
# MSS 截图单例
# ==========================================
# 使用惰性初始化（Lazy Import），仅在第一次调用 get_mss() 时才导入 mss 库
# 并创建唯一的 MSS 实例。这样做的好处是：
# 1. 避免 module_macro.py 和 module_farm_skills.py 各自创建 MSS 实例导致 GDI 句柄泄露
# 2. 减少启动时间（mss 导入有一定开销）
_mss_instance = None


def get_mss():
    """
    获取共享的 MSS 截图单例。
    全局只创建一个 mss.MSS() 实例，所有模块共用，
    避免多次创建导致 Windows GDI 句柄资源耗尽。
    """
    global _mss_instance
    if _mss_instance is None:
        import mss

        _mss_instance = mss.MSS()
    return _mss_instance


def reset_mss() -> None:
    """
    安全重置 MSS 截图单例。

    当 GDI 句柄损坏或长时间运行后截图失败时调用此函数。
    会先尝试关闭现有实例，然后置空，下次调用 get_mss() 时自动重建。

    此函数是 _mss_instance 的唯一外部操作入口，
    避免其他模块直接操作私有属性。
    """
    global _mss_instance
    if _mss_instance is not None:
        try:
            _mss_instance.close()
        except Exception:
            pass  # close 失败也无所谓，置空即可
        _mss_instance = None
        log_info("MSS 截图实例已重置")


# 初始化 colorama（autoreset=True 使得每条 print 后自动重置颜色）
init(autoreset=True)


# ==========================================
# 日志输出
# ==========================================
# 所有日志函数都经过 safe_print 包装，以安全处理终端编码不支持的 Unicode 字符
# （如 Emoji 表情在某些 Windows 终端下会触发 UnicodeEncodeError）


def safe_print(msg):
    """
    安全打印函数：处理终端编码错误。
    当 stdout 不支持某些 Unicode 字符时，使用 replace 策略降级输出，
    避免因为单个 Emoji 导致整个程序崩溃。
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            enc = sys.stdout.encoding or "utf-8"
            print(msg.encode(enc, errors="replace").decode(enc))
        except Exception:
            pass


def log_info(msg):
    """输出 [INFO] 级别日志（青色前缀）"""
    safe_print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {msg}")


def log_success(msg):
    """输出 [SUCCESS] 级别日志（绿色前缀）"""
    safe_print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} {msg}")


def log_warning(msg):
    """输出 [WARNING] 级别日志（黄色前缀）"""
    safe_print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} {msg}")


def log_error(msg):
    """输出 [ERROR] 级别日志（红色前缀）"""
    safe_print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {msg}")


# ==========================================
# 游戏窗口操作
# ==========================================


def find_game_window():
    """
    查找 Forza Horizon 6 游戏窗口的句柄 (HWND)。

    查找策略（两级）：
    1. 优先使用 FindWindowW 按精确窗口标题查找（速度快）
    2. 如果找不到，使用 EnumWindows 遍历所有窗口，做模糊匹配
       （兼容窗口标题包含额外后缀的情况，如 "Forza Horizon 6 (Debug)"）

    返回:
        int: 窗口句柄 HWND，找不到时返回 None
    """
    # 策略 1：精确匹配标题
    hwnd = ctypes.windll.user32.FindWindowW(None, "Forza Horizon 6")
    if hwnd:
        return hwnd

    # 策略 2：模糊枚举所有窗口
    found_hwnd = [None]

    def foreach_window(h, lParam):
        length = ctypes.windll.user32.GetWindowTextLengthW(h)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
            if "forza horizon 6" in buff.value.lower():
                found_hwnd[0] = h
                return False  # 停止枚举
        return True  # 继续枚举

    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    EnumWindows(EnumWindowsProc(foreach_window), 0)
    return found_hwnd[0]


def force_foreground(hwnd):
    """
    将游戏窗口强制置于最前台并激活。

    Windows 有前台窗口保护机制：普通应用无法直接抢夺前台焦点。
    这里使用 ALT 键 trick 绕过限制：
    1. 先发送一个 ALT 按下事件（keybd_event 0x12）
    2. 在 ALT 按下期间调用 SetForegroundWindow
    3. 释放 ALT 键
    这样 Windows 会认为是用户通过 ALT+TAB 切换窗口，从而允许前台抢夺。

    如果窗口处于最小化状态（IsIconic），还会先恢复窗口。
    """
    log_info("正在将游戏窗口置于最前...")
    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # ALT 按下
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # ALT 释放
    if ctypes.windll.user32.IsIconic(hwnd):
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE: 从最小化恢复
    time.sleep(1.5)  # 等待窗口动画和渲染完成


def get_client_rect(hwnd):
    """
    获取游戏窗口客户区（Client Area）的屏幕绝对坐标。

    客户区是窗口中不包含标题栏和边框的内容区域，
    也就是实际显示游戏画面的区域。

    返回:
        tuple: (left_x, top_y, width, height) — 屏幕绝对坐标
    """
    rect = wintypes.RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
    # 将客户区左上角 (0,0) 转换为屏幕坐标
    point_tl = wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point_tl))
    return point_tl.x, point_tl.y, rect.right, rect.bottom


# ==========================================
# 手柄操作
# ==========================================


def press_button(gamepad, button, delay=0.5):
    """
    按下并释放虚拟手柄按钮（模拟单次按键操作）。

    流程：
    1. press_button → update（按下）
    2. sleep 0.15 秒（模拟人手按键的最短持续时间）
    3. release_button → update（释放）
    4. sleep delay 秒（等待游戏 UI 响应）

    参数:
        gamepad: vgamepad.VX360Gamepad 实例
        button:  vgamepad 按钮常量（如 XUSB_GAMEPAD_A, XUSB_GAMEPAD_B 等）
        delay:   释放按钮后的等待时间（秒），默认 0.5 秒，
                 较长的 delay 用于等待游戏界面过渡动画完成
    """
    gamepad.press_button(button=button)
    gamepad.update()
    time.sleep(0.15)  # 按键最短保持时间
    gamepad.release_button(button=button)
    gamepad.update()
    time.sleep(delay)  # 按键后等待 UI 响应
