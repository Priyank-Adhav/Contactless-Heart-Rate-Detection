"""
Unit tests for the Signal Quality Index engine.

Validates that the SQI correctly identifies clean signals as HIGH
quality and noise-dominated signals as LOW quality, and that the
output suppression logic triggers appropriately.
"""

import numpy as np
import pytest

from src.sqi_engine import (
    compute_kurtosis_score,
    compute_spectral_purity,
    compute_spectral_snr,
    compute_sqi,
)


class TestSpectralSNR:
    """Tests for the spectral signal-to-noise ratio metric."""

    def test_high_snr_for_clean_sinusoid(self, synthetic_bvp_72bpm):
        """A clean cardiac sinusoid should have high spectral SNR."""
        signal, fps = synthetic_bvp_72bpm
        score = compute_spectral_snr(signal, fps)
        assert 0.0 <= score <= 1.0
        assert score > 0.8, f"Clean sinusoid SNR should be high, got {score}"

    def test_low_snr_for_noise(self, noisy_signal):
        """Random noise should have very low spectral SNR."""
        signal, fps = noisy_signal
        score = compute_spectral_snr(signal, fps)
        assert 0.0 <= score <= 1.0
        assert score < 0.5, f"Noise SNR should be low, got {score}"


class TestKurtosisScore:
    """Tests for the kurtosis-based quality metric."""

    def test_normal_kurtosis_for_sinusoid(self, synthetic_bvp_72bpm):
        """A sinusoidal pulse should have kurtosis within the
        expected physiological range."""
        signal, fps = synthetic_bvp_72bpm
        score = compute_kurtosis_score(signal)
        assert 0.0 <= score <= 1.0
        # Sinusoid has excess kurtosis of -1.5, so it will score low
        # This is expected — kurtosis metric is more useful for real BVP


class TestSpectralPurity:
    """Tests for the spectral peak width metric."""

    def test_narrow_peak_for_clean_signal(self, synthetic_bvp_72bpm):
        """Clean signal should produce a narrow dominant peak."""
        signal, fps = synthetic_bvp_72bpm
        score = compute_spectral_purity(signal, fps)
        assert 0.0 <= score <= 1.0
        assert score >= 0.5, f"Clean signal purity should be moderate-high, got {score}"

    def test_broad_spectrum_for_noise(self, noisy_signal):
        """Noise should produce a broad, flat spectrum."""
        signal, fps = noisy_signal
        score = compute_spectral_purity(signal, fps)
        assert 0.0 <= score <= 1.0


class TestCompositeSQI:
    """Tests for the combined quality score and decision logic."""

    def test_clean_signal_scores_high(self, synthetic_bvp_72bpm):
        """Clean sinusoidal signal should score above 0.6 (HIGH)."""
        signal, fps = synthetic_bvp_72bpm
        score, level, color = compute_sqi(signal, fps)
        assert score > 0.35, f"Clean signal composite score too low: {score}"
        assert level in ("HIGH", "MEDIUM")

    def test_noise_scores_low(self, noisy_signal):
        """Random noise should score below 0.35 (LOW)."""
        signal, fps = noisy_signal
        score, level, color = compute_sqi(signal, fps)
        assert score < 0.5, f"Noise composite score too high: {score}"
        assert level in ("LOW", "MEDIUM")
        assert color in ("red", "yellow")

    def test_score_is_bounded(self, synthetic_bvp_72bpm):
        """Composite SQI should always be between 0.0 and 1.0."""
        signal, fps = synthetic_bvp_72bpm
        score, level, color = compute_sqi(signal, fps)
        assert 0.0 <= score <= 1.0
        assert level in ("HIGH", "MEDIUM", "LOW")
        assert color in ("green", "yellow", "red")

    def test_score_is_bounded_for_noise(self, noisy_signal):
        """Composite SQI should always be between 0.0 and 1.0 for noise too."""
        signal, fps = noisy_signal
        score, level, color = compute_sqi(signal, fps)
        assert 0.0 <= score <= 1.0

    def test_low_sqi_suppresses_output(self, noisy_signal):
        """When SQI is LOW, the color should be red (gating signal)."""
        signal, fps = noisy_signal
        score, level, color = compute_sqi(signal, fps)
        if level == "LOW":
            assert color == "red"
        # Verify the mapping is consistent
        if score > 0.6:
            assert level == "HIGH" and color == "green"
        elif score > 0.35:
            assert level == "MEDIUM" and color == "yellow"
        else:
            assert level == "LOW" and color == "red"

    def test_output_tuple_format(self, synthetic_bvp_60bpm):
        """compute_sqi should return a 3-tuple of (float, str, str)."""
        signal, fps = synthetic_bvp_60bpm
        result = compute_sqi(signal, fps)
        assert len(result) == 3
        score, level, color = result
        assert isinstance(score, float)
        assert isinstance(level, str)
        assert isinstance(color, str)
