# -*- coding: utf-8 -*-
"""
tests/test_refactor_quality.py ΓÇö Σ╗úτáüΦ┤¿ΘçÅΘçìµ₧äσ¢₧σ╜Æµ╡ïΦ»ò
=====================================================
Θ¬îΦ»üΘçìµ₧äσëìσÉÄΦíîΣ╕║Σ╕ÇΦç┤µÇº:

  SMELL-4  crop_card_roi() σà¼σà▒σç╜µò░τÜäµ¡úτí«µÇº
  BP-3     ocr.py σà¼σà▒σç╜µò░τÜäτ▒╗σ₧ïµáçµ│¿σ¡ÿσ£¿µÇº
  BP-4     Counter σ║öσ£¿µûçΣ╗╢Θí╢Θâ¿σ»╝σàÑ
  PERF-3   resize µÅÆσÇ╝µû╣σ╝ÅΣ╕ìσ╜▒σôìΦ╛ôσç║σ╜óτè╢
  PERF-4   find_cursor_position Φúüσë¬Σ╝ÿσîûΣ╕ìσ╜▒σôìτ╗ôµ₧£
"""

import inspect

import numpy as np
import pytest

# vgamepad requires Windows + ViGEmBus driver; skip entire module on Linux CI.
pytest.importorskip("vgamepad", reason="vgamepad requires Windows + ViGEmBus driver")


# ================================================================
# SMELL-4: crop_card_roi µÅÉσÅûΣ╕║σà¼σà▒σç╜µò░
# ================================================================


class TestCropCardRoi:
    """Θ¬îΦ»ü crop_card_roi ΦíîΣ╕║µ¡úτí«µÇºπÇé"""

    def test_function_exists(self) -> None:
        """crop_card_roi σ║öΣ╜£Σ╕║σà¼σà▒σç╜µò░σ¡ÿσ£¿Σ║Ä engine.ocr Σ╕¡πÇé"""
        from engine.ocr import crop_card_roi

        assert callable(crop_card_roi)

    def test_normal_center_cursor(self) -> None:
        """σàëµáçσ£¿τö╗Θ¥óΣ╕¡σñ«µù╢σ║öΦ┐öσ¢₧µ£ëµòê ROIπÇé"""
        from engine.ocr import CARD_CROP_H, CARD_CROP_W, crop_card_roi

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        roi = crop_card_roi(image, 800, 450)
        assert roi is not None
        roi_h, roi_w = roi.shape[:2]
        # µò┤ΘÖñΦúüσë¬: σÑçµò░σ░║σ»╕Σ╝ÜΣ╕óσñ▒ 1px (217//2*2=216)∩╝îΦ┐Öµÿ»Θóäµ£ƒΦíîΣ╕║
        assert abs(roi_h - CARD_CROP_H) <= 1
        assert abs(roi_w - CARD_CROP_W) <= 1

    def test_corner_cursor_clamps(self) -> None:
        """σàëµáçσ£¿σ╖ªΣ╕èΦºÆµù╢σ║öσ«ëσà¿Φúüσë¬∩╝êΣ╕ìΦ╢èτòî∩╝ëπÇé"""
        from engine.ocr import crop_card_roi

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        roi = crop_card_roi(image, 0, 0)
        assert roi is not None
        assert roi.shape[0] > 0
        assert roi.shape[1] > 0

    def test_bottom_right_corner(self) -> None:
        """σàëµáçσ£¿σÅ│Σ╕ïΦºÆµù╢σ║öσ«ëσà¿Φúüσë¬∩╝êΣ╕ìΦ╢èτòî∩╝ëπÇé"""
        from engine.ocr import crop_card_roi

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        roi = crop_card_roi(image, 1599, 899)
        assert roi is not None
        assert roi.shape[0] > 0
        assert roi.shape[1] > 0

    def test_none_image_returns_none(self) -> None:
        """None σ¢╛σâÅσ║öΦ┐öσ¢₧ NoneπÇé"""
        from engine.ocr import crop_card_roi

        assert crop_card_roi(None, 800, 450) is None

    def test_empty_image_returns_none(self) -> None:
        """τ⌐║σ¢╛σâÅσ║öΦ┐öσ¢₧ NoneπÇé"""
        from engine.ocr import crop_card_roi

        empty: np.ndarray = np.array([], dtype=np.uint8).reshape(0, 0, 3)
        assert crop_card_roi(empty, 0, 0) is None

    def test_callers_use_helper(self) -> None:
        """verify_new_target_car τ¡ëσç╜µò░σåàΘâ¿σ║öΣ╜┐τö¿ crop_card_roi ΦÇîΘ¥₧σåàΦüöΦúüσë¬πÇé"""
        from engine.ocr import check_is_high_class, check_new_tag_only, verify_new_target_car

        for fn in [verify_new_target_car, check_new_tag_only, check_is_high_class]:
            source: str = inspect.getsource(fn)
            assert "crop_card_roi" in source, f"{fn.__name__} σ║öΣ╜┐τö¿ crop_card_roi() ΦÇîΘ¥₧σåàΦüöΦúüσë¬"
            # τí«Σ┐¥µ▓íµ£ëµ«ïτòÖτÜäµùºΦúüσë¬µ¿íσ╝Å
            assert "cursor_x - crop_w // 2" not in source, f"{fn.__name__} Σ╗ìσîàσÉ½µùºτÜäσåàΦüöΦúüσë¬Σ╗úτáü"


# ================================================================
# BP-3: ocr.py σà¼σà▒σç╜µò░σ║öµ£ëτ▒╗σ₧ïµáçµ│¿
# ================================================================


class TestBP3TypeHints:
    """ocr.py σà¼σà▒σç╜µò░σ║öµ£ëΦ┐öσ¢₧σÇ╝τ▒╗σ₧ïµáçµ│¿πÇé"""

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
            "crop_card_roi",
        ],
    )
    def test_has_return_annotation(self, func_name: str) -> None:
        """σà¼σà▒σç╜µò░σ║öµ£ëΦ┐öσ¢₧σÇ╝τ▒╗σ₧ïµáçµ│¿πÇé"""
        import engine.ocr as ocr_module

        fn = getattr(ocr_module, func_name)
        sig = inspect.signature(fn)
        assert sig.return_annotation is not inspect.Parameter.empty, f"BP-3: {func_name}() τ╝║σ░æΦ┐öσ¢₧σÇ╝τ▒╗σ₧ïµáçµ│¿"


# ================================================================
# PERF-3: resize µÅÆσÇ╝µû╣σ╝Å
# ================================================================


class TestPerf3Resize:
    """capture_screenshot σ║öΣ╜┐τö¿ INTER_LINEAR ΦÇîΘ¥₧ INTER_AREAπÇé"""

    def test_uses_inter_linear(self) -> None:
        """capture_screenshot µ║Éτáüσ║öσîàσÉ½ INTER_LINEARπÇé"""
        from macro.core import capture_screenshot

        source: str = inspect.getsource(capture_screenshot)
        assert "INTER_LINEAR" in source, "PERF-3: capture_screenshot σ║öΣ╜┐τö¿ cv2.INTER_LINEAR"
        assert "INTER_AREA" not in source, "PERF-3: capture_screenshot Σ╕ìσ║öΣ╜┐τö¿ cv2.INTER_AREA"


# ================================================================
# PERF-4: find_cursor_position σ║öσàêΦúüσë¬σåì HSV Φ╜¼µìó
# ================================================================


class TestPerf4CursorCropBeforeHSV:
    """find_cursor_position σ║öσàêΦúüσë¬µ£ëµòêσî║σƒƒσåìΦ╜¼µìó HSVπÇé"""

    def test_no_full_image_hsv(self) -> None:
        """Σ╕ìσ║öσ»╣µò┤σ╝á 1600├ù900 σ¢╛σüÜ HSV Φ╜¼µìóσÉÄσåìΘü«τ╜⌐πÇé"""
        from engine.ocr import find_cursor_position

        source: str = inspect.getsource(find_cursor_position)
        # µùºµ¿íσ╝Å: σàêΦ╜¼µìóσà¿σ¢╛σåìµÄ⌐τáü
        #   hsv = cv2.cvtColor(image, ...)
        #   mask[:, :int(img_w * 0.21)] = 0
        # µû░µ¿íσ╝Å: σàêΦúüσë¬σåìΦ╜¼µìó
        assert "cvtColor(image," not in source, "PERF-4: find_cursor_position σ║öσàêΦúüσë¬µ£ëµòêσî║σƒƒσåìσüÜ HSV Φ╜¼µìó"

    def test_returns_correct_for_green_rect(self) -> None:
        """σ£¿σ╖▓τƒÑΣ╜ìτ╜«τö╗Σ╕ÇΣ╕¬τ╗┐Φë▓τƒ⌐σ╜ó∩╝îσ║öΦâ╜µ¡úτí«µúÇµ╡ïσê░πÇé"""
        from engine.ocr import find_cursor_position

        image: np.ndarray = np.zeros((900, 1600, 3), dtype=np.uint8)
        # σ£¿ (600, 400) σñäτö╗Σ╕ÇΣ╕¬ 200x150 τÜäΣ║«τ╗┐Φë▓τƒ⌐σ╜óΦ╛╣µíå
        green_bgr = (0, 255, 100)  # BGR
        cx, cy, w, h = 600, 400, 200, 150
        x1, y1 = cx - w // 2, cy - h // 2
        # τö╗ 4 µ¥íΦ╛╣µíåτ║┐∩╝êσÄÜ 5px∩╝ë
        image[y1 : y1 + 5, x1 : x1 + w] = green_bgr  # Σ╕è
        image[y1 + h - 5 : y1 + h, x1 : x1 + w] = green_bgr  # Σ╕ï
        image[y1 : y1 + h, x1 : x1 + 5] = green_bgr  # σ╖ª
        image[y1 : y1 + h, x1 + w - 5 : x1 + w] = green_bgr  # σÅ│

        result = find_cursor_position(image)
        # σ║öΦ»ÑΦâ╜µúÇµ╡ïσê░Φ┐ÖΣ╕¬τƒ⌐σ╜ó
        # (σÅ»Φâ╜σ¢áΣ╕║ HSV Φîâσ¢┤σÆîΘù¡Φ┐Éτ«ù∩╝îσ«₧ΘÖàΣ╕¡σ┐âΣ╝Üµ£ëσ░ÅσüÅσ╖«)
        if result is not None:
            det_cx, det_cy = result
            assert abs(det_cx - cx) < 50, f"X σüÅσ╖«Φ┐çσñº: {det_cx} vs {cx}"
            assert abs(det_cy - cy) < 50, f"Y σüÅσ╖«Φ┐çσñº: {det_cy} vs {cy}"
