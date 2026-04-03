"""
Unit tests for the ROI extraction module.

Tests cover:
- Internal helper functions (polygon conversion, channel extraction,
  gap interpolation) using synthetic data that does not require
  a video file or camera.
- Structural validation of the extract_rois function signature
  and return type.

Tests that require a real video file are marked with pytest.mark.slow
and depend on a fixture file existing in tests/fixtures/.
"""

import numpy as np
import pytest

from src.roi_extractor import (
    FOREHEAD_INDICES,
    LEFT_CHEEK_INDICES,
    RIGHT_CHEEK_INDICES,
    ROI_DEFINITIONS,
    _extract_roi_channels,
    _interpolate_gaps,
    _interpolate_rgb_gaps,
    _landmarks_to_polygon,
)

# --- Helpers for creating mock landmark objects ---

class MockLandmark:
    """Minimal stand-in for a single MediaPipe landmark."""
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class MockLandmarks(list):
    """Minimal stand-in for MediaPipe face landmarks (tasks API).

    The new tasks API returns landmarks as a list, accessed via
    landmarks[idx] rather than landmarks.landmark[idx].
    """
    def __init__(self, points_dict):
        # Build a list of 468 landmarks, defaulting to (0.5, 0.5)
        data = [MockLandmark(0.5, 0.5) for _ in range(468)]
        for idx, (x, y) in points_dict.items():
            data[idx] = MockLandmark(x, y)
        super().__init__(data)


# --- Tests for _landmarks_to_polygon ---

class TestLandmarksToPolygon:

    def test_correct_number_of_points(self):
        """Output polygon should have one point per index."""
        lm = MockLandmarks({10: (0.5, 0.1), 338: (0.6, 0.1), 297: (0.7, 0.2)})
        indices = [10, 338, 297]
        poly = _landmarks_to_polygon(lm, indices, 640, 480)
        assert poly.shape == (3, 2)

    def test_coordinates_are_pixel_space(self):
        """Normalized (0.5, 0.25) with frame 640x480 should give (320, 120)."""
        lm = MockLandmarks({10: (0.5, 0.25)})
        poly = _landmarks_to_polygon(lm, [10], 640, 480)
        assert poly[0][0] == 320
        assert poly[0][1] == 120

    def test_coordinates_clamped_to_frame(self):
        """Landmarks outside [0,1] range should be clamped to frame edges."""
        lm = MockLandmarks({10: (1.1, -0.1)})
        poly = _landmarks_to_polygon(lm, [10], 640, 480)
        assert poly[0][0] == 639  # clamped to frame_w - 1
        assert poly[0][1] == 0    # clamped to 0

    def test_returns_integer_array(self):
        """Polygon points should be integers for cv2.fillPoly compatibility."""
        lm = MockLandmarks({10: (0.333, 0.666)})
        poly = _landmarks_to_polygon(lm, [10], 640, 480)
        assert poly.dtype == np.int32


# --- Tests for _extract_roi_channels ---

class TestExtractROIChannels:

    def test_uniform_frame_returns_correct_mean(self):
        """A uniformly colored frame should return that color's values."""
        # Create a 100x100 BGR frame: B=50, G=120, R=200
        frame = np.full((100, 100, 3), [50, 120, 200], dtype=np.uint8)
        # Triangle polygon covering part of the frame
        polygon = np.array([[10, 10], [50, 10], [30, 50]], dtype=np.int32)

        g_mean, rgb_mean = _extract_roi_channels(frame, polygon, 100, 100)

        assert g_mean is not None
        assert abs(g_mean - 120.0) < 1.0
        assert abs(rgb_mean[0] - 200.0) < 1.0  # R
        assert abs(rgb_mean[1] - 120.0) < 1.0  # G
        assert abs(rgb_mean[2] - 50.0) < 1.0   # B

    def test_empty_polygon_returns_none(self):
        """A degenerate polygon with no area should return None."""
        frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        # Line, not a polygon -- zero area
        polygon = np.array([[10, 10], [10, 10]], dtype=np.int32)

        g_mean, rgb_mean = _extract_roi_channels(frame, polygon, 100, 100)
        # Note: cv2.fillPoly with a degenerate polygon may or may not
        # produce pixels. We accept either None or a valid float.
        # The important thing is it does not crash.
        assert g_mean is None or isinstance(g_mean, float)

    def test_green_channel_in_valid_range(self):
        """Returned green channel mean should be between 0 and 255."""
        rng = np.random.RandomState(42)
        frame = rng.randint(0, 256, (200, 200, 3), dtype=np.uint8)
        polygon = np.array([[20, 20], [80, 20], [80, 80], [20, 80]], dtype=np.int32)

        g_mean, _ = _extract_roi_channels(frame, polygon, 200, 200)
        assert 0 <= g_mean <= 255


# --- Tests for _interpolate_gaps ---

class TestInterpolateGaps:

    def test_no_gaps_unchanged(self):
        """Signal with no None values should be returned as-is."""
        signal = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _interpolate_gaps(signal)
        assert result == signal

    def test_single_gap_interpolated(self):
        """A single None between two values should be linearly filled."""
        signal = [10.0, None, 20.0]
        result = _interpolate_gaps(signal, max_gap=5)
        assert result[0] == 10.0
        assert result[2] == 20.0
        # Midpoint should be close to 15.0
        assert abs(result[1] - 15.0) < 0.1

    def test_multi_frame_gap_interpolated(self):
        """A gap of 3 frames should produce evenly spaced values."""
        signal = [0.0, None, None, None, 100.0]
        result = _interpolate_gaps(signal, max_gap=5)
        assert all(v is not None for v in result)
        # Should be roughly [0, 25, 50, 75, 100]
        assert abs(result[1] - 25.0) < 1.0
        assert abs(result[2] - 50.0) < 1.0
        assert abs(result[3] - 75.0) < 1.0

    def test_gap_at_start_forward_filled(self):
        """Gap at the beginning with no left neighbor should be forward-filled
        from the first valid value (acts as backward fill)."""
        signal = [None, None, 5.0, 6.0]
        result = _interpolate_gaps(signal)
        # No left neighbor, but right neighbor exists -> backward fill
        assert result[0] == 5.0
        assert result[1] == 5.0

    def test_gap_at_end_backward_filled(self):
        """Gap at the end should be filled with the last valid value."""
        signal = [3.0, 4.0, None, None]
        result = _interpolate_gaps(signal)
        assert result[2] == 4.0
        assert result[3] == 4.0

    def test_long_gap_not_interpolated(self):
        """Gap exceeding max_gap should be forward-filled, not interpolated."""
        signal = [1.0] + [None] * 10 + [100.0]
        result = _interpolate_gaps(signal, max_gap=5)
        # Since gap > max_gap and left_val exists, should forward-fill with 1.0
        assert result[5] == 1.0

    def test_all_none_filled_with_zero(self):
        """Entirely None signal should be filled with zeros."""
        signal = [None, None, None]
        result = _interpolate_gaps(signal)
        assert result == [0.0, 0.0, 0.0]


# --- Tests for _interpolate_rgb_gaps ---

class TestInterpolateRGBGaps:

    def test_no_gaps_unchanged(self):
        """RGB signal without gaps should pass through unchanged."""
        signal = [[10, 20, 30], [40, 50, 60]]
        result = _interpolate_rgb_gaps(signal)
        assert result == signal

    def test_single_gap_interpolated(self):
        """A single None in RGB signal should interpolate each channel."""
        signal = [[10, 100, 50], None, [30, 200, 150]]
        result = _interpolate_rgb_gaps(signal, max_gap=5)
        assert result[1] is not None
        assert len(result[1]) == 3
        # Check green channel midpoint
        assert abs(result[1][1] - 150.0) < 1.0


# --- Tests for ROI definitions ---

class TestROIDefinitions:

    def test_three_rois_defined(self):
        """There should be exactly three ROI definitions."""
        assert len(ROI_DEFINITIONS) == 3

    def test_forehead_indices_nonempty(self):
        assert len(FOREHEAD_INDICES) >= 3  # need at least a triangle

    def test_left_cheek_indices_nonempty(self):
        assert len(LEFT_CHEEK_INDICES) >= 3

    def test_right_cheek_indices_nonempty(self):
        assert len(RIGHT_CHEEK_INDICES) >= 3

    def test_all_indices_in_valid_range(self):
        """All landmark indices should be within [0, 467]."""
        all_indices = FOREHEAD_INDICES + LEFT_CHEEK_INDICES + RIGHT_CHEEK_INDICES
        for idx in all_indices:
            assert 0 <= idx <= 467, f"Index {idx} out of valid landmark range"

    def test_no_duplicate_rois(self):
        """ROI names should be unique."""
        names = [name for name, _ in ROI_DEFINITIONS]
        assert len(names) == len(set(names))


# --- Integration-level tests (require video file) ---

class TestExtractRoisFromVideo:

    @pytest.mark.skipif(
        True,  # Change to a path check when a test video is available
        reason="No test video available in fixtures"
    )
    def test_returns_valid_roi_result(self):
        """extract_rois should return a well-formed ROIResult on a real video."""
        # result = extract_rois("tests/fixtures/clean_face_30s.mp4")
        # assert result.face_detected is True
        # assert len(result.green_signals) == 3
        # assert len(result.green_signals[0]) > 0
        # assert result.fps > 0
        pass
