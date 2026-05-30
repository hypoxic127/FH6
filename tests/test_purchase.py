# -*- coding: utf-8 -*-
"""
tests/test_purchase.py — macro/purchase.py 单元测试

覆盖：
  - is_word_similar()  模糊词匹配（子串 + 编辑距离 + 符号容错）
"""

import pytest

from macro.purchase import is_word_similar


class TestIsWordSimilar:
    """模糊词匹配函数测试。"""

    # --- 完全匹配 ---
    def test_exact_match(self) -> None:
        assert is_word_similar("CARS", "CARS") is True

    def test_case_insensitive(self) -> None:
        assert is_word_similar("cars", "CARS") is True

    # --- 子串匹配 ---
    def test_target_in_ocr(self) -> None:
        """目标词包含在 OCR 输出中。"""
        assert is_word_similar("MY CARS PAGE", "CARS") is True

    def test_ocr_in_target_short_reject(self) -> None:
        """OCR 词太短（<3 字符）不应匹配。"""
        assert is_word_similar("CA", "CARS") is False

    def test_ocr_in_target_long_accept(self) -> None:
        """OCR 词 >= 3 字符且是目标子串 → 匹配。"""
        assert is_word_similar("CAR", "CARS") is True

    # --- 符号容错 ---
    def test_punctuation_tolerance(self) -> None:
        """OCR 误读的符号不影响匹配。"""
        assert is_word_similar("C.A.R.S", "CARS") is True

    def test_hyphen_tolerance(self) -> None:
        assert is_word_similar("MY-HORIZON", "MY HORIZON") is True

    # --- 编辑距离 ---
    def test_one_char_typo(self) -> None:
        """单字符 OCR 误读（GARS → CARS）应匹配（编辑距离=1）。"""
        assert is_word_similar("GARS", "CARS") is True

    def test_two_char_typo_short_word_reject(self) -> None:
        """短词 2 字符差距过大 → 不匹配。"""
        assert is_word_similar("GXRS", "CARS") is False

    def test_completely_different_reject(self) -> None:
        """完全不同的词不应匹配。"""
        assert is_word_similar("STORE", "CARS") is False

    def test_empty_strings(self) -> None:
        """空字符串边界情况。"""
        assert is_word_similar("", "CARS") is False
        # 注意: is_word_similar("X", "") / is_word_similar("", "") 返回 True
        # 因为 "" in "X" 和 "" in "" 均为 True — 这是 Python 子串语义
        # 实际调用场景中 target_keyword 永远非空，此边界无需防御

    # --- 真实 OCR 误读场景 ---
    def test_real_ocr_campaign(self) -> None:
        """CAMPAIGN 标签的典型 OCR 误读。"""
        assert is_word_similar("CAMPA1GN", "CAMPAIGN") is True

    def test_real_ocr_creative_hub(self) -> None:
        assert is_word_similar("CREATIVE HUB", "CREATIVE HUB") is True

    def test_real_ocr_eventlab(self) -> None:
        assert is_word_similar("EVENTLAB", "EVENTLAB") is True
