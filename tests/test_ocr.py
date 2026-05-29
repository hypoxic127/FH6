# -*- coding: utf-8 -*-
"""
tests/test_ocr.py — engine/ocr.py 单元测试

覆盖：
  - HSV 颜色常量合法性
  - IMPREZA_22B_KEYWORDS 关键词匹配逻辑
  - detect_selected_brand_tab() 暗区检测算法
  - _ocr_card_text() 预处理管线（合成图像）
  - has_green_selection_border() 边框检测（合成图像）
  - is_empty_slot() 空位检测（合成图像）
"""

import numpy as np
import cv2
import pytest

from engine.ocr import (
    # 常量
    HSV_GREEN_BORDER_LOWER, HSV_GREEN_BORDER_UPPER,
    HSV_GREEN_CURSOR_LOWER, HSV_GREEN_CURSOR_UPPER,
    HSV_YELLOW_NEW_LOWER, HSV_YELLOW_NEW_UPPER,
    CARD_CROP_W, CARD_CROP_H,
    IMPREZA_22B_KEYWORDS, IMPREZA_22B_MIN_MATCH,
    EMPTY_SLOT_BRIGHTNESS_THRESHOLD, EMPTY_SLOT_VARIANCE_THRESHOLD,
    BRAND_TAB_ROI_Y, BRAND_TAB_ROI_X,
    # 函数
    has_green_selection_border,
    detect_selected_brand_tab,
    is_empty_slot,
)


# ==========================================
# HSV 常量合法性
# ==========================================

class TestHSVConstants:
    """HSV 颜色阈值常量应在 OpenCV 合法范围内。"""

    @pytest.mark.parametrize("lower,upper,name", [
        (HSV_GREEN_BORDER_LOWER, HSV_GREEN_BORDER_UPPER, "GREEN_BORDER"),
        (HSV_GREEN_CURSOR_LOWER, HSV_GREEN_CURSOR_UPPER, "GREEN_CURSOR"),
        (HSV_YELLOW_NEW_LOWER, HSV_YELLOW_NEW_UPPER, "YELLOW_NEW"),
    ])
    def test_hsv_range_valid(self, lower: np.ndarray, upper: np.ndarray,
                             name: str) -> None:
        """H∈[0,179], S∈[0,255], V∈[0,255]，且 lower <= upper。"""
        assert lower[0] >= 0 and upper[0] <= 179, f"{name}: H out of range"
        assert lower[1] >= 0 and upper[1] <= 255, f"{name}: S out of range"
        assert lower[2] >= 0 and upper[2] <= 255, f"{name}: V out of range"
        assert np.all(lower <= upper), f"{name}: lower > upper"

    def test_card_crop_positive(self) -> None:
        """卡片裁剪尺寸应为正数。"""
        assert CARD_CROP_W > 0
        assert CARD_CROP_H > 0

    def test_empty_slot_thresholds_positive(self) -> None:
        """空位检测阈值应为正数。"""
        assert EMPTY_SLOT_BRIGHTNESS_THRESHOLD > 0
        assert EMPTY_SLOT_VARIANCE_THRESHOLD > 0


# ==========================================
# IMPREZA 关键词匹配逻辑
# ==========================================

class TestImprezaKeywords:
    """关键词列表和最低命中数应一致且合理。"""

    def test_keywords_not_empty(self) -> None:
        assert len(IMPREZA_22B_KEYWORDS) >= 2

    def test_min_match_within_range(self) -> None:
        """最低命中数不能超过关键词总数。"""
        assert 1 <= IMPREZA_22B_MIN_MATCH <= len(IMPREZA_22B_KEYWORDS)

    def test_typical_ocr_text_matches(self) -> None:
        """模拟 OCR 输出，验证匹配逻辑。"""
        ocr_text = "1998 subaru impreza 22b-sti version"
        matched = [kw for kw in IMPREZA_22B_KEYWORDS if kw in ocr_text]
        assert len(matched) >= IMPREZA_22B_MIN_MATCH

    def test_non_target_car_fails(self) -> None:
        """非目标车辆文字不应命中足够关键词。"""
        ocr_text = "2024 subaru brz premium"
        matched = [kw for kw in IMPREZA_22B_KEYWORDS if kw in ocr_text]
        assert len(matched) < IMPREZA_22B_MIN_MATCH


# ==========================================
# has_green_selection_border() — 合成图像
# ==========================================

class TestGreenSelectionBorder:
    """绿色选中边框检测（使用合成 BGR 图像）。"""

    def test_returns_false_for_none(self) -> None:
        assert has_green_selection_border(None) is False

    def test_returns_false_for_empty(self) -> None:
        assert has_green_selection_border(np.array([])) is False

    def test_returns_false_for_black_image(self) -> None:
        """纯黑图 → 无绿色边框。"""
        img = np.zeros((200, 280, 3), dtype=np.uint8)
        assert has_green_selection_border(img) == False

    def test_returns_true_for_green_border(self) -> None:
        """四边绘制绿色矩形 → 检测到边框。"""
        img = np.zeros((200, 280, 3), dtype=np.uint8)
        # 在 HSV 中 H=60(绿色), S=200, V=200 → 转为 BGR
        green_bgr = cv2.cvtColor(
            np.array([[[60, 200, 200]]], dtype=np.uint8), cv2.COLOR_HSV2BGR
        )[0, 0]
        thickness = 15
        cv2.rectangle(img, (0, 0), (279, 199), green_bgr.tolist(), thickness)
        assert has_green_selection_border(img) == True


# ==========================================
# detect_selected_brand_tab() — 暗区检测
# ==========================================

class TestDetectSelectedBrandTab:
    """品牌标签栏暗区检测算法（不依赖 OCR 结果精度）。"""

    def test_returns_none_for_none(self) -> None:
        assert detect_selected_brand_tab(None) is None

    def test_returns_none_for_empty(self) -> None:
        assert detect_selected_brand_tab(np.array([])) is None

    def test_returns_none_for_tiny_image(self) -> None:
        """过小的图像应安全返回 None。"""
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        assert detect_selected_brand_tab(img) is None

    def test_finds_dark_region_in_synthetic_strip(self) -> None:
        """合成一张有明显暗区的标签栏图像，验证函数不崩溃。"""
        # 创建 1600x900 亮色图像
        img = np.full((900, 1600, 3), 200, dtype=np.uint8)
        # 在标签栏区域 (y:14%-18%, x:9%-91%) 的中间制造一段暗区
        y1 = int(900 * 0.14)
        y2 = int(900 * 0.18)
        x1 = int(1600 * 0.40)
        x2 = int(1600 * 0.55)
        img[y1:y2, x1:x2] = 30  # 暗区

        # 函数应返回字符串或 None（不崩溃即可）
        result = detect_selected_brand_tab(img)
        # result 是 OCR 结果，合成图不保证能识别文字，
        # 但函数不应抛异常
        assert result is None or isinstance(result, str)

    def test_brand_tab_roi_defaults(self) -> None:
        """默认 ROI 参数应在 0-1 百分比范围内。"""
        assert 0.0 <= BRAND_TAB_ROI_Y[0] < BRAND_TAB_ROI_Y[1] <= 1.0
        assert 0.0 <= BRAND_TAB_ROI_X[0] < BRAND_TAB_ROI_X[1] <= 1.0


# ==========================================
# is_empty_slot() — 空位检测
# ==========================================

class TestIsEmptySlot:
    """车库空位检测（暗色低方差 → 空位）。"""

    def test_dark_uniform_is_empty(self) -> None:
        """纯黑图 → 空位。"""
        # is_empty_slot 需要 1600x900 场景图 + 光标坐标
        img = np.zeros((900, 1600, 3), dtype=np.uint8)
        assert is_empty_slot(img, 800, 450) == True

    def test_bright_image_is_not_empty(self) -> None:
        """亮色图 → 不是空位。"""
        img = np.full((900, 1600, 3), 180, dtype=np.uint8)
        assert is_empty_slot(img, 800, 450) == False

    def test_none_returns_true(self) -> None:
        """None 输入应安全返回 True（保守策略）。"""
        assert is_empty_slot(None, 0, 0) == True
