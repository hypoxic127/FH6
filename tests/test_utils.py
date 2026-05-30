# -*- coding: utf-8 -*-
"""
tests/test_utils.py — engine/utils.py 单元测试

覆盖：
  - safe_print()  安全打印
  - 日志函数（log_info / log_success / log_warning / log_error）
  - reset_mss()  MSS 重置逻辑
"""

import pytest

from engine.utils import (
    get_mss,
    log_error,
    log_info,
    log_success,
    log_warning,
    reset_mss,
    safe_print,
)


class TestSafePrint:
    """safe_print 安全打印测试。"""

    def test_ascii_text(self, capsys: pytest.CaptureFixture) -> None:
        safe_print("hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_unicode_text(self, capsys: pytest.CaptureFixture) -> None:
        safe_print("你好世界 🎮")
        captured = capsys.readouterr()
        assert len(captured.out) > 0  # 不崩溃即可

    def test_empty_string(self, capsys: pytest.CaptureFixture) -> None:
        safe_print("")
        captured = capsys.readouterr()
        assert captured.out.strip() == ""


class TestLogFunctions:
    """日志函数不应崩溃且包含正确前缀。"""

    def test_log_info(self, capsys: pytest.CaptureFixture) -> None:
        log_info("test message")
        captured = capsys.readouterr()
        assert "INFO" in captured.out

    def test_log_success(self, capsys: pytest.CaptureFixture) -> None:
        log_success("test message")
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out

    def test_log_warning(self, capsys: pytest.CaptureFixture) -> None:
        log_warning("test message")
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_log_error(self, capsys: pytest.CaptureFixture) -> None:
        log_error("test message")
        captured = capsys.readouterr()
        assert "ERROR" in captured.out


class TestMssSingleton:
    """MSS 截图单例管理测试。"""

    @pytest.mark.hardware
    def test_get_mss_returns_instance(self) -> None:
        """get_mss() 应返回 MSS 实例（需要 Windows 桌面环境）。"""
        sct = get_mss()
        assert sct is not None

    @pytest.mark.hardware
    def test_get_mss_singleton(self) -> None:
        """多次调用应返回同一实例。"""
        sct1 = get_mss()
        sct2 = get_mss()
        assert sct1 is sct2

    @pytest.mark.hardware
    def test_reset_mss_clears(self) -> None:
        """reset 后再 get 应返回新实例。"""
        sct1 = get_mss()
        reset_mss()
        sct2 = get_mss()
        assert sct1 is not sct2
