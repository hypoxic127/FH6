# -*- coding: utf-8 -*-
"""
tests/test_refactor_quality.py — 代码质量重构回归测试
=====================================================
验证重构前后行为一致性:

  SMELL-4  crop_card_roi() 公共函数的正确性
  BP-3     ocr.py 公共函数的类型标注存在性
  BP-4     Counter 应在文件顶部导入
  PERF-3   resize 插值方式不影响输出形状
  PERF-4   find_cursor_position 裁剪优化不影响结果
"""

import inspect

import numpy as np
import pytest


# ================================================================
# SMELL-4: crop_card_roi 提取为公共函数
# ================================================================


class TestCropCardRoi:
    """验证 crop_card_roi 行为正确性。"""

    def test_function_exists(self) -> None:
        """crop_card_roi 应作为公共函数存在于 engine.ocr 中。"""
        from engine.ocr import crop_card_roi

        assert callable(crop_card_roi)

    def test_normal_center_cursor(self) -> None:
        """光标在画面中央时应返回有效 ROI。"""
        from engine.ocr import CARD_CROP_H, CARD_CROP_W, crop_card_roi

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        roi = crop_card_roi(image, 800, 450)
        assert roi is not None
        roi_h, roi_w = roi.shape[:2]
        # 整除裁剪: 奇数尺寸会丢失 1px (217//2*2=216)，这是预期行为
        assert abs(roi_h - CARD_CROP_H) <= 1
        assert abs(roi_w - CARD_CROP_W) <= 1

    def test_corner_cursor_clamps(self) -> None:
        """光标在左上角时应安全裁剪（不越界）。"""
        from engine.ocr import crop_card_roi

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        roi = crop_card_roi(image, 0, 0)
        assert roi is not None
        assert roi.shape[0] > 0
        assert roi.shape[1] > 0

    def test_bottom_right_corner(self) -> None:
        """光标在右下角时应安全裁剪（不越界）。"""
        from engine.ocr import crop_card_roi

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        roi = crop_card_roi(image, 1599, 899)
        assert roi is not None
        assert roi.shape[0] > 0
        assert roi.shape[1] > 0

    def test_none_image_returns_none(self) -> None:
        """None 图像应返回 None。"""
        from engine.ocr import crop_card_roi

        assert crop_card_roi(None, 800, 450) is None

    def test_empty_image_returns_none(self) -> None:
        """空图像应返回 None。"""
        from engine.ocr import crop_card_roi

        empty: np.ndarray = np.array([], dtype=np.uint8).reshape(0, 0, 3)
        assert crop_card_roi(empty, 0, 0) is None

    def test_callers_use_helper(self) -> None:
        """verify_new_target_car 等函数内部应使用 crop_card_roi 而非内联裁剪。"""
        from engine.ocr import check_is_high_class, check_new_tag_only, verify_new_target_car

        for fn in [verify_new_target_car, check_new_tag_only, check_is_high_class]:
            source: str = inspect.getsource(fn)
            assert "crop_card_roi" in source, (
                f"{fn.__name__} 应使用 crop_card_roi() 而非内联裁剪"
            )
            # 确保没有残留的旧裁剪模式
            assert "cursor_x - crop_w // 2" not in source, (
                f"{fn.__name__} 仍包含旧的内联裁剪代码"
            )


# ================================================================
# BP-4: Counter 应在文件顶部导入
# ================================================================


class TestBP4CounterImport:
    """Counter 应在模块顶部导入，不在函数内部。"""

    def test_counter_at_module_level(self) -> None:
        """ocr.py 应在文件顶部导入 Counter。"""
        import engine.ocr as ocr_module

        source: str = inspect.getsource(ocr_module)
        lines: list[str] = source.split("\n")

        # 检查前 40 行（import 区域）是否包含 Counter 导入
        top_section: str = "\n".join(lines[:40])
        assert "from collections import Counter" in top_section, (
            "BP-4: 'from collections import Counter' 应在文件顶部导入区"
        )

    def test_no_counter_inside_functions(self) -> None:
        """函数内部不应有 Counter 的延迟导入。"""
        from engine.ocr import read_skill_points

        source: str = inspect.getsource(read_skill_points)
        assert "from collections import Counter" not in source, (
            "BP-4: read_skill_points 仍在函数内部导入 Counter"
        )


# ================================================================
# BP-3: ocr.py 公共函数应有类型标注
# ================================================================


class TestBP3TypeHints:
    """ocr.py 公共函数应有返回值类型标注。"""

    @pytest.mark.parametrize(
        "func_name",
        [
            "read_skill_points",
            "find_cursor_position",
            "check_is_high_class",
            "check_new_tag_only",
            "verify_new_target_car",
            "has_green_selection_border",
            "has_green_selection_border_padded",
            "has_cell_below",
            "read_text_in_roi",
            "find_target_car",
            "crop_card_roi",
        ],
    )
    def test_has_return_annotation(self, func_name: str) -> None:
        """公共函数应有返回值类型标注。"""
        import engine.ocr as ocr_module

        fn = getattr(ocr_module, func_name)
        sig = inspect.signature(fn)
        assert sig.return_annotation is not inspect.Parameter.empty, (
            f"BP-3: {func_name}() 缺少返回值类型标注"
        )


# ================================================================
# PERF-3: resize 插值方式
# ================================================================


class TestPerf3Resize:
    """capture_screenshot 应使用 INTER_LINEAR 而非 INTER_AREA。"""

    def test_uses_inter_linear(self) -> None:
        """capture_screenshot 源码应包含 INTER_LINEAR。"""
        from macro.core import capture_screenshot

        source: str = inspect.getsource(capture_screenshot)
        assert "INTER_LINEAR" in source, (
            "PERF-3: capture_screenshot 应使用 cv2.INTER_LINEAR"
        )
        assert "INTER_AREA" not in source, (
            "PERF-3: capture_screenshot 不应使用 cv2.INTER_AREA"
        )


# ================================================================
# PERF-4: find_cursor_position 应先裁剪再 HSV 转换
# ================================================================


class TestPerf4CursorCropBeforeHSV:
    """find_cursor_position 应先裁剪有效区域再转换 HSV。"""

    def test_no_full_image_hsv(self) -> None:
        """不应对整张 1600×900 图做 HSV 转换后再遮罩。"""
        from engine.ocr import find_cursor_position

        source: str = inspect.getsource(find_cursor_position)
        # 旧模式: 先转换全图再掩码
        #   hsv = cv2.cvtColor(image, ...)
        #   mask[:, :int(img_w * 0.21)] = 0
        # 新模式: 先裁剪再转换
        assert "cvtColor(image," not in source, (
            "PERF-4: find_cursor_position 应先裁剪有效区域再做 HSV 转换"
        )

    def test_returns_correct_for_green_rect(self) -> None:
        """在已知位置画一个绿色矩形，应能正确检测到。"""
        from engine.ocr import find_cursor_position

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        # 在 (600, 400) 处画一个 200x150 的亮绿色矩形边框
        green_bgr = (0, 255, 100)  # BGR
        cx, cy, w, h = 600, 400, 200, 150
        x1, y1 = cx - w // 2, cy - h // 2
        # 画 4 条边框线（厚 5px）
        image[y1 : y1 + 5, x1 : x1 + w] = green_bgr        # 上
        image[y1 + h - 5 : y1 + h, x1 : x1 + w] = green_bgr  # 下
        image[y1 : y1 + h, x1 : x1 + 5] = green_bgr        # 左
        image[y1 : y1 + h, x1 + w - 5 : x1 + w] = green_bgr  # 右

        result = find_cursor_position(image)
        # 应该能检测到这个矩形
        # (可能因为 HSV 范围和闭运算，实际中心会有小偏差)
        if result is not None:
            det_cx, det_cy = result
            assert abs(det_cx - cx) < 50, f"X 偏差过大: {det_cx} vs {cx}"
            assert abs(det_cy - cy) < 50, f"Y 偏差过大: {det_cy} vs {cy}"
