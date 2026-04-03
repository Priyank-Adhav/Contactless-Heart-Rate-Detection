"""
Unit tests for the ROI extraction module.

These tests validate face detection, landmark extraction, and green
channel signal output from the multi-ROI pipeline. Tests that require
a real video file are marked with pytest.mark.slow and skipped in
fast CI runs.
"""

import pytest


class TestExtractRoisFromVideo:
    """Tests for the file-based ROI extraction path."""

    @pytest.mark.skip(reason="Awaiting roi_extractor implementation")
    def test_returns_three_roi_signals(self, tmp_path):
        """extract_rois should return exactly three signal arrays
        (forehead, left cheek, right cheek)."""
        # from src.roi_extractor import extract_rois
        # result = extract_rois(str(test_video_path))
        # assert len(result.green_signals) == 3
        pass

    @pytest.mark.skip(reason="Awaiting roi_extractor implementation")
    def test_signal_length_matches_frame_count(self):
        """Each ROI signal length should equal the number of frames
        where a face was detected."""
        pass

    @pytest.mark.skip(reason="Awaiting roi_extractor implementation")
    def test_green_channel_values_in_valid_range(self):
        """Green channel spatial means should fall within [0, 255]."""
        pass

    @pytest.mark.skip(reason="Awaiting roi_extractor implementation")
    def test_face_not_detected_in_blank_frame(self):
        """A blank or faceless video should produce face_detected=False."""
        pass

    @pytest.mark.skip(reason="Awaiting roi_extractor implementation")
    def test_fps_matches_source_video(self):
        """Reported FPS should match the input video's frame rate."""
        pass


class TestExtractRoisFromWebcam:
    """Tests for the webcam-based ROI extraction path."""

    @pytest.mark.skip(reason="Awaiting roi_extractor implementation")
    def test_webcam_capture_returns_roi_result(self):
        """Webcam extraction should return a valid ROIResult with
        the correct duration of signal data."""
        pass
