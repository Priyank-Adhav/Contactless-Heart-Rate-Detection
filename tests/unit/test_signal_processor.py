"""
Unit tests for the signal processing module.

Validates bandpass filtering, POS algorithm, CHROM algorithm, and
BPM extraction using synthetic signals with known cardiac frequencies.
"""

import numpy as np

from src.signal_processor import bandpass_filter, chrom_algorithm, extract_bpm, pos_algorithm


class TestBandpassFilter:
    """Tests for the Butterworth bandpass filter."""

    def test_passes_signal_within_band(self):
        """A 1.2 Hz sinusoid should pass through a 0.7-3.5 Hz filter
        with minimal attenuation."""
        fps = 30
        duration = 10
        t = np.linspace(0, duration, int(fps * duration), endpoint=False)
        signal = np.sin(2 * np.pi * 1.2 * t)
        filtered = bandpass_filter(signal, fps)
        # Check that the signal is not heavily attenuated
        assert np.std(filtered) > 0.8 * np.std(signal)

    def test_attenuates_signal_outside_band(self):
        """A 10 Hz component should be heavily attenuated by the filter."""
        fps = 30
        duration = 10
        t = np.linspace(0, duration, int(fps * duration), endpoint=False)
        signal = np.sin(2 * np.pi * 10 * t)
        filtered = bandpass_filter(signal, fps)
        # Check that the signal is heavily attenuated
        assert np.std(filtered) < 0.15 * np.std(signal)

    def test_output_length_matches_input(self):
        """Filtered signal should have the same length as the input."""
        signal = np.random.randn(300)
        fps = 30
        filtered = bandpass_filter(signal, fps)
        assert len(filtered) == len(signal)


class TestPOSAlgorithm:
    """Tests for the Plane-Orthogonal-to-Skin rPPG method."""

    def test_extracts_known_frequency(self, synthetic_bvp_72bpm):
        """POS output should contain a dominant frequency near 1.2 Hz
        when given a synthetic 72 BPM input."""
        signal, fps = synthetic_bvp_72bpm
        # Create synthetic RGB
        rgb = np.column_stack([signal * 0.95, signal, signal * 0.98])
        bvp = pos_algorithm(rgb, fps)
        bpm = extract_bpm(bvp, fps)
        assert bpm is not None
        assert abs(bpm - 72) < 5  # Allow some tolerance

    def test_output_is_one_dimensional(self):
        """POS should reduce a 3-channel input to a single pulse signal."""
        fps = 30
        num_samples = 300
        rgb = np.random.randn(num_samples, 3)
        bvp = pos_algorithm(rgb, fps)
        assert bvp.ndim == 1
        assert len(bvp) == num_samples


class TestCHROMAlgorithm:
    """Tests for the Chrominance-based rPPG method."""

    def test_extracts_known_frequency(self, synthetic_bvp_72bpm):
        """CHROM output should contain a dominant frequency near 1.2 Hz."""
        signal, fps = synthetic_bvp_72bpm
        rgb = np.column_stack([signal * 0.95, signal, signal * 0.98])
        bvp = chrom_algorithm(rgb, fps)
        bpm = extract_bpm(bvp, fps)
        assert bpm is not None
        assert abs(bpm - 72) < 5

    def test_output_is_one_dimensional(self):
        """CHROM should reduce a 3-channel input to a single pulse signal."""
        fps = 30
        num_samples = 300
        rgb = np.random.randn(num_samples, 3)
        bvp = chrom_algorithm(rgb, fps)
        assert bvp.ndim == 1
        assert len(bvp) == num_samples


class TestBPMExtraction:
    """Tests for FFT-based BPM estimation."""

    def test_correct_bpm_from_clean_signal(self, synthetic_bvp_72bpm):
        """A clean 1.2 Hz signal should yield BPM close to 72."""
        signal, fps = synthetic_bvp_72bpm
        bpm = extract_bpm(signal, fps)
        assert bpm is not None
        assert abs(bpm - 72) < 3

    def test_bpm_within_physiological_range(self, noisy_signal):
        """Even with noisy input, reported BPM should be clamped
        to the physiological range [40, 200]."""
        signal, fps = noisy_signal
        bpm = extract_bpm(signal, fps)
        if bpm is not None:
            assert 42 <= bpm <= 200

    def test_correct_bpm_at_60bpm(self, synthetic_bvp_60bpm):
        """A clean 1.0 Hz signal should yield BPM close to 60."""
        signal, fps = synthetic_bvp_60bpm
        bpm = extract_bpm(signal, fps)
        assert bpm is not None
        assert abs(bpm - 60) < 3
