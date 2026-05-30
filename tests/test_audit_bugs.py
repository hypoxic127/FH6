# -*- coding: utf-8 -*-
"""
tests/test_audit_bugs.py — 审计报告 Bug 复现 & 回归测试
========================================================
每个测试在 **未修复** 代码上必须 FAIL，在 **修复后** 代码上必须 PASS。

覆盖范围:
  BUG-1  purchase.py  _detect_playing / _detect_campaign 使用旧模块名导入
  BUG-2  core.py      capture_screenshot 错误路径的 MSS 重置引用旧模块名
  BUG-3  garage.py    _scan_and_delete_cars 删车状态机 current_col 下溢
  EDGE-5 ocr.py       check_is_high_class PI 检测兜底返回 False 可能误删主力车
"""

import inspect
from unittest.mock import patch

import numpy as np
import pytest

# vgamepad 是 Windows 专用包（依赖 ViGEmBus 驱动），在 Linux CI 上不可用。
# 该文件中的测试通过 macro.purchase / macro.garage 间接导入 vgamepad，
# 因此在 vgamepad 不可用时跳过整个模块。
vgamepad = pytest.importorskip("vgamepad", reason="vgamepad requires Windows + ViGEmBus driver")


# ================================================================
# BUG-1: purchase.py _detect_playing / _detect_campaign
#         使用已不存在的 'module_state_detect' 模块名
# ================================================================


class TestBug1PurchaseImportPath:
    """验证 _detect_playing 和 _detect_campaign 的延迟导入路径正确。"""

    def test_detect_playing_no_module_not_found(self) -> None:
        """_detect_playing 调用时不应抛出 ModuleNotFoundError。"""
        from macro.purchase import _detect_playing

        with patch(
            "macro.purchase.capture_screenshot",
            return_value=(None, 0, 0, 0, 0),
        ):
            try:
                _detect_playing(None)
            except ModuleNotFoundError as exc:
                pytest.fail(f"BUG-1: _detect_playing 使用了错误的导入路径: {exc}")

    def test_detect_campaign_no_module_not_found(self) -> None:
        """_detect_campaign 调用时不应抛出 ModuleNotFoundError。"""
        from macro.purchase import _detect_campaign

        with patch(
            "macro.purchase.capture_screenshot",
            return_value=(None, 0, 0, 0, 0),
        ):
            try:
                _detect_campaign(None)
            except ModuleNotFoundError as exc:
                pytest.fail(f"BUG-1: _detect_campaign 使用了错误的导入路径: {exc}")

    def test_detect_playing_source_has_correct_import(self) -> None:
        """_detect_playing 源码中应引用 engine.state_detect。"""
        from macro.purchase import _detect_playing

        source: str = inspect.getsource(_detect_playing)
        assert "from module_state_detect" not in source, "BUG-1: _detect_playing 仍使用旧模块名 'module_state_detect'"
        assert "engine.state_detect" in source, "_detect_playing 应从 'engine.state_detect' 导入"

    def test_detect_campaign_source_has_correct_import(self) -> None:
        """_detect_campaign 源码中应引用 engine.state_detect。"""
        from macro.purchase import _detect_campaign

        source: str = inspect.getsource(_detect_campaign)
        assert "from module_state_detect" not in source, "BUG-1: _detect_campaign 仍使用旧模块名 'module_state_detect'"
        assert "engine.state_detect" in source, "_detect_campaign 应从 'engine.state_detect' 导入"


# ================================================================
# BUG-2: core.py capture_screenshot 异常处理中 MSS 重置
#         引用 'import utils' 而非 'engine.utils'
# ================================================================


class TestBug2CoreMssResetPath:
    """验证 capture_screenshot 的错误处理不再使用裸 'import utils'。"""

    def test_no_bare_utils_import(self) -> None:
        """capture_screenshot 源码中不应存在裸 'import utils'。"""
        from macro.core import capture_screenshot

        source: str = inspect.getsource(capture_screenshot)
        lines: list[str] = [line.strip() for line in source.split("\n")]

        bad_lines: list[str] = [
            line for line in lines if line == "import utils" or line.startswith("from utils import")
        ]
        assert not bad_lines, f"BUG-2: capture_screenshot 仍使用裸 'utils' 模块路径: {bad_lines}"


# ================================================================
# BUG-3: garage.py _scan_and_delete_cars
#         current_col -= 1 在 col=1 时下溢到 0/负数
# ================================================================


class TestBug3DeleteColUnderflow:
    """验证删车状态机的列号不会下溢。"""

    def test_no_unguarded_col_decrement(self) -> None:
        """_scan_and_delete_cars 中不应有裸 'current_col -= 1'。"""
        from macro.garage import _scan_and_delete_cars

        source: str = inspect.getsource(_scan_and_delete_cars)
        assert "current_col -= 1" not in source, (
            "BUG-3: _scan_and_delete_cars 存在未保护的 'current_col -= 1'，col=1 时会下溢到 0"
        )

    def test_col_clamp_logic_present(self) -> None:
        """修复后应使用 max(1, ...) 或等效防护。"""
        from macro.garage import _scan_and_delete_cars

        source: str = inspect.getsource(_scan_and_delete_cars)
        # 修复后应包含 max(1, current_col - 1) 或类似防护
        assert "max(1," in source, "BUG-3: _scan_and_delete_cars 缺少 max(1, ...) 列号下溢防护"


# ================================================================
# EDGE-5: ocr.py check_is_high_class
#         蓝/橙像素均为 0 时兜底返回 False → 可能误删主力车
# ================================================================


class TestEdge5PiDetectionConservative:
    """验证 PI 检测在无法判定时保守返回 True（跳过删除）。"""

    def test_ambiguous_pi_returns_true(self) -> None:
        """全黑图像（无蓝/橙像素）应返回 True（保守: 不删除）。"""
        from engine.ocr import check_is_high_class

        # 全黑 1600×900 图像 — PI 徽章区域无蓝色也无橙色
        black_image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        result: bool = check_is_high_class(black_image, 800, 450)

        assert result is True, "EDGE-5: check_is_high_class 在颜色不明确时返回 False，可能导致误删 S2 主力车"
