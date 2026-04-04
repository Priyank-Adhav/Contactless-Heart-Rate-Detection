"""
Unit tests for the HRV analysis module.

Validates IBI-to-HRV computation for both time-domain and
frequency-domain metrics using synthetic inter-beat interval arrays
with known statistical properties.
"""

import numpy as np

from src.hrv_analyzer import (
    clean_ibi,
    compute_frequency_domain,
    compute_hrv,
    compute_ibi,
    compute_time_domain,
)


class TestIBIComputation:
    """Tests for converting peak indices to IBI arrays."""

    def test_ibi_from_evenly_spaced_peaks(self):
        """Evenly spaced peaks at 30 fps with 25-sample intervals
        should produce ~833 ms IBIs (72 BPM)."""
        # peaks every 25 samples at 30 fps → 25/30 = 0.8333 s = 833.3 ms
        peaks = list(range(0, 900, 25))  # 36 peaks
        ibi = compute_ibi(peaks, fps=30)

        assert len(ibi) == len(peaks) - 1
        assert abs(np.mean(ibi) - 833.3) < 5, (
            f"Expected mean IBI ~833.3 ms, got {np.mean(ibi):.1f} ms"
        )

    def test_ibi_length_is_peaks_minus_one(self):
        """Number of IBIs should be one less than the number of peaks."""
        peaks = [0, 30, 60, 90, 120]  # 5 peaks
        ibi = compute_ibi(peaks, fps=30)
        assert len(ibi) == 4  # 5 - 1

    def test_ibi_empty_for_single_peak(self):
        """A single peak cannot produce any IBI."""
        ibi = compute_ibi([100], fps=30)
        assert ibi == []

    def test_ibi_empty_for_no_peaks(self):
        """No peaks → no IBIs."""
        ibi = compute_ibi([], fps=30)
        assert ibi == []


class TestIBICleaning:
    """Tests for artifact rejection on IBI arrays.

    The artifact rejection threshold is 45% (max_change_pct=0.45).
    This is intentionally more permissive than the classical ECG value
    of 30%, because rPPG peak detection has ±1-2 sample jitter that
    produces natural IBI variance of 5-15% at typical heart rates.
    True artifacts (missed/double beats) produce changes of 80-100%
    and are still caught; the absolute bounds filter [300, 1500] ms
    handles the rest.
    """

    def test_removes_too_short_ibi(self):
        """IBI below 300 ms (>200 BPM) should be removed."""
        ibi = [800.0, 200.0, 810.0]  # 200 ms is too short
        cleaned = clean_ibi(ibi)
        assert 200.0 not in cleaned

    def test_removes_too_long_ibi(self):
        """IBI above 1500 ms (<40 BPM) should be removed."""
        ibi = [800.0, 2000.0, 810.0]  # 2000 ms is too long
        cleaned = clean_ibi(ibi)
        assert 2000.0 not in cleaned

    def test_removes_true_artifact_large_jump(self):
        """IBI that jumps >45% from previous (missed beat) should be removed.

        800 → 1450 ms is an 81% jump, well above the 45% threshold.
        This represents a genuinely missed beat, not rPPG jitter.
        """
        ibi = [800.0, 820.0, 1450.0, 810.0]
        cleaned = clean_ibi(ibi)
        assert 1450.0 not in cleaned, (
            "An 81% IBI jump should be rejected as a missed-beat artifact"
        )

    def test_preserves_moderate_jump_within_threshold(self):
        """IBI jump of ~37% should be retained under the 45% threshold.

        800 → 1100 ms is a 37.5% change. Under the old 30% threshold
        this was rejected, but rPPG jitter at typical frame rates can
        produce legitimate variance in this range. The new 45% threshold
        retains these beats to ensure sufficient IBIs reach HRV computation.
        """
        ibi = [800.0, 820.0, 1100.0, 810.0]
        cleaned = clean_ibi(ibi)
        assert 1100.0 in cleaned, (
            "A 37.5% IBI change is within the 45% rPPG jitter tolerance "
            "and should not be rejected"
        )

    def test_preserves_valid_ibi(self):
        """All-valid IBIs should pass through unchanged."""
        ibi = [800.0, 810.0, 795.0, 820.0, 805.0]
        cleaned = clean_ibi(ibi)
        assert cleaned == ibi


class TestHRVTimeDomain:
    """Tests for time-domain HRV metrics: RMSSD, SDNN, pNN50."""

    def test_rmssd_resting_within_normal_range(self, synthetic_ibi_resting):
        """Resting IBI (SD=40ms) should produce RMSSD in the 20-80 ms range."""
        metrics = compute_time_domain(synthetic_ibi_resting)
        assert 20 <= metrics["rmssd"] <= 80, (
            f"RMSSD={metrics['rmssd']} ms is outside expected 20-80 ms range"
        )

    def test_sdnn_resting_within_normal_range(self, synthetic_ibi_resting):
        """Resting IBI should produce SDNN near 40 ms (the generating SD)."""
        metrics = compute_time_domain(synthetic_ibi_resting)
        # The synthetic data was generated with SD=40, so SDNN should be close
        assert 20 <= metrics["sdnn"] <= 70, (
            f"SDNN={metrics['sdnn']} ms is outside expected 20-70 ms range"
        )

    def test_rmssd_stressed_lower_than_resting(
        self, synthetic_ibi_resting, synthetic_ibi_stressed
    ):
        """Stressed IBI (SD=15ms) should produce lower RMSSD than resting."""
        resting_metrics = compute_time_domain(synthetic_ibi_resting)
        stressed_metrics = compute_time_domain(synthetic_ibi_stressed)

        assert stressed_metrics["rmssd"] < resting_metrics["rmssd"], (
            f"Stressed RMSSD ({stressed_metrics['rmssd']}) should be < "
            f"Resting RMSSD ({resting_metrics['rmssd']})"
        )

    def test_pnn50_nonnegative(self, synthetic_ibi_resting):
        """pNN50 should always be between 0 and 100."""
        metrics = compute_time_domain(synthetic_ibi_resting)
        assert 0 <= metrics["pnn50"] <= 100

    def test_mean_hr_resting_in_normal_range(self, synthetic_ibi_resting):
        """Resting IBI (~857 ms mean) should give mean HR ~70 BPM."""
        metrics = compute_time_domain(synthetic_ibi_resting)
        assert 55 <= metrics["mean_hr"] <= 85, (
            f"Mean HR={metrics['mean_hr']} outside expected 55-85 BPM range"
        )


class TestHRVFrequencyDomain:
    """Tests for frequency-domain HRV metrics."""

    def test_lf_hf_ratio_is_positive(self, synthetic_ibi_resting):
        """LF/HF ratio should be a positive number when computable."""
        lf_hf = compute_frequency_domain(synthetic_ibi_resting)
        assert lf_hf is not None, "LF/HF should be computable for 35 IBIs"
        assert lf_hf > 0, f"LF/HF ratio should be positive, got {lf_hf}"

    def test_handles_short_ibi_array_gracefully(self):
        """With fewer than 10 IBIs, frequency analysis should return None."""
        short_ibi = [800.0, 810.0, 795.0, 820.0, 805.0]  # only 5 values
        lf_hf = compute_frequency_domain(short_ibi)
        assert lf_hf is None, "Should return None for <10 IBIs"


class TestComputeHRVPipeline:
    """Tests for the full compute_hrv() pipeline."""

    def test_returns_none_for_insufficient_peaks(self):
        """Fewer than 6 peaks → fewer than 5 IBIs → should return None."""
        result = compute_hrv([0, 30, 60], fps=30)  # only 3 peaks → 2 IBIs
        assert result is None

    def test_full_pipeline_returns_hrv_result(self):
        """End-to-end: evenly spaced peaks should produce a valid HRVResult."""
        # 36 peaks at 25-sample spacing at 30 fps → ~833 ms IBIs → ~72 BPM
        peaks = list(range(0, 900, 25))
        result = compute_hrv(peaks, fps=30)

        assert result is not None
        assert result.rmssd >= 0
        assert result.sdnn >= 0
        assert 0 <= result.pnn50 <= 100
        assert 60 <= result.mean_hr <= 85  # ~72 BPM expected
        assert len(result.ibi_ms) > 0

    def test_pipeline_with_resting_ibi_fixture(self, synthetic_ibi_resting):
        """Verify compute_time_domain + compute_frequency_domain produce
        a coherent set of metrics from resting IBI data."""
        td = compute_time_domain(synthetic_ibi_resting)
        lf_hf = compute_frequency_domain(synthetic_ibi_resting)

        # Sanity checks on the assembled result
        assert td["rmssd"] > 0
        assert td["sdnn"] > 0
        assert td["mean_hr"] > 0
        # LF/HF may or may not be computable, but shouldn't crash
        if lf_hf is not None:
            assert lf_hf > 0
