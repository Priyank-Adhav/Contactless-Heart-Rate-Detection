"""
Unit tests for the signal processing module.

Validates bandpass filtering, POS algorithm, CHROM algorithm, and
BPM extraction using synthetic signals with known cardiac frequencies.
"""

import numpy as np

from src.ensemble import fuse_signals
from src.signal_processor import (
    _green_to_synthetic_rgb,
    bandpass_filter,
    chrom_algorithm,
    detect_peaks,
    extract_bpm,
    normalize_signal,
    pos_algorithm,
)

# ── Helpers ──

def _make_rgb_signal(freq_hz, fps, duration, amplitude=0.5, baseline=140.0):
    """Create a synthetic RGB signal with a known cardiac frequency.

    The green channel carries the strongest cardiac component (matching
    real rPPG physics).  R and B carry weaker components.

    Args:
        freq_hz: Cardiac frequency in Hz (e.g., 1.2 for 72 BPM).
        fps: Sampling rate.
        duration: Duration in seconds.
        amplitude: Amplitude of the cardiac component.
        baseline: Baseline pixel intensity.

    Returns:
        Tuple of (rgb_array of shape (N, 3), fps).
    """
    N = int(fps * duration)
    t = np.linspace(0, duration, N, endpoint=False)
    cardiac = amplitude * np.sin(2 * np.pi * freq_hz * t)

    # Green has strongest cardiac, R and B have weaker
    R = baseline * 0.95 + cardiac * 0.3
    G = baseline + cardiac
    B = baseline * 0.98 + cardiac * 0.2

    rgb = np.column_stack([R, G, B])
    return rgb, fps


class TestBandpassFilter:
    """Tests for the Butterworth bandpass filter."""

    def test_passes_signal_within_band(self):
        """A 1.2 Hz sinusoid should pass through a 0.7-3.5 Hz filter
        with minimal attenuation."""
        fps = 30
        duration = 30
        N = fps * duration
        t = np.linspace(0, duration, N, endpoint=False)
        signal = np.sin(2 * np.pi * 1.2 * t)  # 1.2 Hz = in-band

        filtered = bandpass_filter(signal, fps)

        # Power should be largely preserved (at least 80%)
        input_power = np.mean(signal ** 2)
        output_power = np.mean(filtered ** 2)
        ratio = output_power / input_power
        assert ratio > 0.8, (
            f"In-band signal power ratio = {ratio:.3f}, expected > 0.8"
        )

    def test_attenuates_signal_outside_band(self):
        """A 10 Hz component should be heavily attenuated by the filter."""
        fps = 30
        duration = 30
        N = fps * duration
        t = np.linspace(0, duration, N, endpoint=False)
        signal = np.sin(2 * np.pi * 10.0 * t)  # 10 Hz = out-of-band

        filtered = bandpass_filter(signal, fps)

        input_power = np.mean(signal ** 2)
        output_power = np.mean(filtered ** 2)
        ratio = output_power / (input_power + 1e-10)
        assert ratio < 0.1, (
            f"Out-of-band signal power ratio = {ratio:.3f}, expected < 0.1"
        )

    def test_output_length_matches_input(self):
        """Filtered signal should have the same length as the input."""
        fps = 30
        N = 900
        signal = np.random.randn(N)
        filtered = bandpass_filter(signal, fps)
        assert len(filtered) == N

    def test_removes_dc_offset(self):
        """Filter should remove DC component (0 Hz)."""
        fps = 30
        N = 900
        t = np.linspace(0, 30, N, endpoint=False)
        signal = 100.0 + np.sin(2 * np.pi * 1.2 * t)  # large DC + cardiac

        filtered = bandpass_filter(signal, fps)
        assert abs(np.mean(filtered)) < 1.0, "DC should be removed"


class TestNormalizeSignal:
    """Tests for the rolling mean normalization."""

    def test_output_length_matches_input(self):
        """Normalized signal should have the same length as input."""
        signal = np.ones(100) * 140.0
        normalized = normalize_signal(signal, window_size=10)
        assert len(normalized) == len(signal)

    def test_constant_signal_normalizes_to_ones(self):
        """A constant signal divided by its mean should be ~1.0
        (ignoring edge effects from convolution)."""
        signal = np.ones(100) * 140.0
        normalized = normalize_signal(signal, window_size=10)
        # Edge effects affect the first/last (window_size/2) samples,
        # so only check the stable middle section
        middle = normalized[10:-10]
        np.testing.assert_allclose(middle, 1.0, atol=0.01)


class TestPOSAlgorithm:
    """Tests for the Plane-Orthogonal-to-Skin rPPG method."""

    def test_extracts_known_frequency(self):
        """POS output should contain a dominant frequency near 1.2 Hz
        when given a synthetic 72 BPM input."""
        rgb, fps = _make_rgb_signal(freq_hz=1.2, fps=30, duration=30)
        pulse = pos_algorithm(rgb, fps)

        # Check dominant frequency via FFT
        freqs = np.fft.rfftfreq(len(pulse), d=1.0 / fps)
        spectrum = np.abs(np.fft.rfft(pulse))

        # Restrict to cardiac range
        mask = (freqs >= 0.7) & (freqs <= 3.5)
        peak_freq = freqs[mask][np.argmax(spectrum[mask])]
        peak_bpm = peak_freq * 60

        assert abs(peak_bpm - 72) < 5, (
            f"POS dominant frequency = {peak_bpm:.1f} BPM, expected ~72"
        )

    def test_output_is_one_dimensional(self):
        """POS should reduce a 3-channel input to a single pulse signal."""
        rgb, fps = _make_rgb_signal(freq_hz=1.2, fps=30, duration=10)
        pulse = pos_algorithm(rgb, fps)

        assert pulse.ndim == 1
        assert len(pulse) == rgb.shape[0]

    def test_output_is_not_all_zeros(self):
        """POS should produce a non-trivial signal from valid input."""
        rgb, fps = _make_rgb_signal(freq_hz=1.2, fps=30, duration=10)
        pulse = pos_algorithm(rgb, fps)
        assert np.std(pulse) > 1e-8, "POS output should not be flat"


class TestCHROMAlgorithm:
    """Tests for the Chrominance-based rPPG method."""

    def test_extracts_known_frequency(self):
        """CHROM output should contain a dominant frequency near 1.2 Hz."""
        rgb, fps = _make_rgb_signal(freq_hz=1.2, fps=30, duration=30)
        pulse = chrom_algorithm(rgb, fps)

        freqs = np.fft.rfftfreq(len(pulse), d=1.0 / fps)
        spectrum = np.abs(np.fft.rfft(pulse))

        mask = (freqs >= 0.7) & (freqs <= 3.5)
        peak_freq = freqs[mask][np.argmax(spectrum[mask])]
        peak_bpm = peak_freq * 60

        assert abs(peak_bpm - 72) < 5, (
            f"CHROM dominant frequency = {peak_bpm:.1f} BPM, expected ~72"
        )

    def test_output_is_one_dimensional(self):
        """CHROM should reduce a 3-channel input to a single pulse signal."""
        rgb, fps = _make_rgb_signal(freq_hz=1.2, fps=30, duration=10)
        pulse = chrom_algorithm(rgb, fps)

        assert pulse.ndim == 1
        assert len(pulse) == rgb.shape[0]


class TestBPMExtraction:
    """Tests for FFT-based BPM estimation."""

    def test_correct_bpm_from_clean_signal(self, synthetic_bvp_72bpm):
        """A clean 1.2 Hz signal should yield BPM close to 72."""
        signal, fps = synthetic_bvp_72bpm
        bpm = extract_bpm(signal, fps)
        assert bpm is not None
        assert abs(bpm - 72) < 3, f"Expected ~72 BPM, got {bpm}"

    def test_bpm_within_physiological_range(self, noisy_signal):
        """Even with noisy input, reported BPM should be within
        the physiological range [42, 200] or None."""
        signal, fps = noisy_signal
        bpm = extract_bpm(signal, fps)
        if bpm is not None:
            assert 42 <= bpm <= 200, (
                f"BPM {bpm} is outside physiological range"
            )

    def test_correct_bpm_at_60bpm(self, synthetic_bvp_60bpm):
        """A clean 1.0 Hz signal should yield BPM close to 60."""
        signal, fps = synthetic_bvp_60bpm
        bpm = extract_bpm(signal, fps)
        assert bpm is not None
        assert abs(bpm - 60) < 3, f"Expected ~60 BPM, got {bpm}"

    def test_returns_none_for_empty_signal(self):
        """Empty or too-short signal should return None."""
        bpm = extract_bpm(np.array([]), fps=30)
        assert bpm is None


class TestPeakDetection:
    """Tests for heartbeat peak detection."""

    def test_peak_count_reasonable(self, synthetic_bvp_72bpm):
        """A 30-second signal at 72 BPM should have ~36 peaks."""
        signal, fps = synthetic_bvp_72bpm
        peaks = detect_peaks(signal, fps)
        # Allow 25-45 range due to edge effects
        assert 25 <= len(peaks) <= 45, (
            f"Expected ~36 peaks, got {len(peaks)}"
        )

    def test_peaks_are_sorted(self, synthetic_bvp_72bpm):
        """Peak indices should be in ascending order."""
        signal, fps = synthetic_bvp_72bpm
        peaks = detect_peaks(signal, fps)
        assert peaks == sorted(peaks)

    def test_empty_for_short_signal(self):
        """Very short signal should return empty peaks list."""
        peaks = detect_peaks(np.array([1.0, 0.0]), fps=30)
        assert len(peaks) == 0


class TestEnsembleFusion:
    """Tests for the SQI-weighted signal fusion."""

    def test_weighted_average_favors_high_sqi(self):
        """Higher-weight signal should dominate the fused output."""
        signal_a = np.ones(100)       # constant 1
        signal_b = np.ones(100) * 2   # constant 2

        # Give signal_b 10x more weight
        fused = fuse_signals([signal_a, signal_b], [0.1, 1.0])

        # Fused should be closer to signal_b (value 2)
        mean_fused = np.mean(fused)
        assert mean_fused > 1.5, (
            f"Fused mean={mean_fused:.2f}, should be closer to 2.0"
        )

    def test_equal_weights_gives_average(self):
        """Equal SQI scores should produce simple average."""
        signal_a = np.ones(100) * 2
        signal_b = np.ones(100) * 4

        fused = fuse_signals([signal_a, signal_b], [1.0, 1.0])
        np.testing.assert_allclose(fused, 3.0, atol=0.01)

    def test_zero_weights_returns_first(self):
        """All-zero weights should return the first candidate."""
        signal_a = np.ones(100) * 5
        signal_b = np.ones(100) * 10

        fused = fuse_signals([signal_a, signal_b], [0.0, 0.0])
        np.testing.assert_allclose(fused, 5.0, atol=0.01)

    def test_single_candidate(self):
        """Single candidate should be returned as-is."""
        signal = np.random.randn(100)
        fused = fuse_signals([signal], [0.8])
        np.testing.assert_allclose(fused, signal, atol=1e-10)


class TestSyntheticRGBConstruction:
    """Tests for green → RGB conversion."""

    def test_output_shape(self):
        """Output should be (N, 3) for N-element green input."""
        green = np.ones(100) * 140.0
        rgb = _green_to_synthetic_rgb(green)
        assert rgb.shape == (100, 3)

    def test_green_channel_preserved(self):
        """Green column should be the original signal."""
        green = np.random.randn(50) + 140
        rgb = _green_to_synthetic_rgb(green)
        np.testing.assert_allclose(rgb[:, 1], green)
