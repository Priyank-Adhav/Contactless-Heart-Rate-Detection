"""
HRV Analysis Module

Computes heart rate variability metrics from an array of inter-beat
intervals. Produces both time-domain (RMSSD, SDNN, pNN50) and
frequency-domain (LF/HF ratio) features.

Pipeline:
    peak_indices + fps
        → compute_ibi()        : convert peak positions to IBI in ms
        → clean_ibi()          : reject physiologically impossible values
        → compute_time_domain() : RMSSD, SDNN, pNN50, mean HR
        → compute_frequency_domain() : LF/HF ratio via Lomb-Scargle
        → HRVResult

See docs/modules/04_hrv_analysis.md for implementation details.
"""

import logging
from typing import List, Optional

import numpy as np
from scipy.signal import lombscargle

from src.models import HRVResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Convert peak indices → IBI in milliseconds
# ---------------------------------------------------------------------------

def compute_ibi(peak_indices: List[int], fps: float) -> List[float]:
    """Convert peak sample indices to inter-beat intervals in milliseconds.

    Each peak represents the moment a heartbeat was detected in the video
    signal.  The distance between consecutive peaks (in samples) divided
    by the sampling rate gives the time between beats.

    Example:
        peaks = [0, 25, 50]  at fps=30
        intervals_in_samples = [25, 25]
        intervals_in_seconds = [25/30, 25/30] = [0.833, 0.833]
        intervals_in_ms      = [833.3, 833.3]

    Args:
        peak_indices: List of integer sample indices where peaks occur.
        fps: Sampling rate of the BVP signal (frames per second).

    Returns:
        List of IBI values in milliseconds.  Length = len(peak_indices) - 1.
        Returns empty list if fewer than 2 peaks.
    """
    if len(peak_indices) < 2:
        logger.warning("Need at least 2 peaks to compute IBI, got %d", len(peak_indices))
        return []

    peaks = np.array(peak_indices)
    intervals_samples = np.diff(peaks)                # gaps in sample counts
    intervals_ms = (intervals_samples / fps) * 1000.0  # convert to milliseconds

    logger.debug("Computed %d IBIs from %d peaks (mean=%.1f ms)",
                 len(intervals_ms), len(peak_indices), np.mean(intervals_ms))

    return intervals_ms.tolist()


# ---------------------------------------------------------------------------
# Step 2: Artifact rejection — remove bad IBI values
# ---------------------------------------------------------------------------

def clean_ibi(
    ibi_ms: List[float],
    min_ibi: float = 300.0,
    max_ibi: float = 1500.0,
    max_change_pct: float = 0.3,
) -> List[float]:
    """Remove physiologically impossible IBI values.

    rPPG signals are noisy — the camera might miss a beat or detect a
    false peak.  This produces outlier IBIs that would corrupt our HRV
    metrics.  We apply two filters:

    1. **Absolute bounds**: Any IBI outside [300, 1500] ms is rejected.
       - 300 ms = 200 BPM  (maximum plausible heart rate)
       - 1500 ms = 40 BPM  (minimum plausible heart rate)

    2. **Relative change**: If an IBI jumps more than 30% from the
       previous accepted IBI, it's likely a missed/extra beat artifact.

    Args:
        ibi_ms: List of raw IBI values in milliseconds.
        min_ibi: Minimum plausible IBI (default 300 ms = 200 BPM).
        max_ibi: Maximum plausible IBI (default 1500 ms = 40 BPM).
        max_change_pct: Maximum allowed fractional change between
                        consecutive IBIs (default 0.3 = 30%).

    Returns:
        Cleaned list of IBI values.  May be shorter than input.
    """
    if len(ibi_ms) < 2:
        return list(ibi_ms)

    cleaned: List[float] = []

    # Accept the first value only if it's within absolute bounds
    if min_ibi <= ibi_ms[0] <= max_ibi:
        cleaned.append(ibi_ms[0])

    for i in range(1, len(ibi_ms)):
        val = ibi_ms[i]

        # Filter 1: absolute bounds
        if val < min_ibi or val > max_ibi:
            continue

        # Filter 2: relative change from last accepted value
        if cleaned:
            change = abs(val - cleaned[-1]) / cleaned[-1]
            if change > max_change_pct:
                continue

        cleaned.append(val)

    removed = len(ibi_ms) - len(cleaned)
    if removed > 0:
        logger.info("Artifact rejection removed %d of %d IBIs (%.0f%%)",
                     removed, len(ibi_ms), removed / len(ibi_ms) * 100)

    return cleaned


# ---------------------------------------------------------------------------
# Step 3: Time-domain HRV metrics
# ---------------------------------------------------------------------------

def compute_time_domain(ibi_ms: List[float]) -> dict:
    """Compute time-domain HRV metrics from cleaned IBI data.

    Returns a dict with:
        - rmssd:   Root Mean Square of Successive Differences
                   → measures beat-to-beat variability
        - sdnn:    Standard Deviation of all IBI values
                   → measures overall variability
        - pnn50:   % of consecutive IBI pairs differing by >50 ms
                   → measures frequency of large timing jumps
        - mean_hr: Average heart rate in BPM
                   → derived from mean IBI

    Args:
        ibi_ms: List of cleaned IBI values in milliseconds.

    Returns:
        Dict with keys: rmssd, sdnn, pnn50, mean_hr (all floats).
    """
    ibi = np.array(ibi_ms)
    diffs = np.diff(ibi)  # successive differences

    # RMSSD: √(mean(diffs²))
    rmssd = float(np.sqrt(np.mean(diffs ** 2)))

    # SDNN: standard deviation of all IBIs (ddof=1 for sample SD)
    sdnn = float(np.std(ibi, ddof=1))

    # pNN50: percentage of |diffs| > 50 ms
    if len(diffs) > 0:
        pnn50 = float(np.sum(np.abs(diffs) > 50) / len(diffs) * 100)
    else:
        pnn50 = 0.0

    # Mean HR: 60000 ms/min ÷ mean_IBI_ms = beats per minute
    mean_ibi = np.mean(ibi)
    mean_hr = float(60000.0 / mean_ibi) if mean_ibi > 0 else 0.0

    result = {
        "rmssd": round(rmssd, 2),
        "sdnn": round(sdnn, 2),
        "pnn50": round(pnn50, 2),
        "mean_hr": round(mean_hr, 1),
    }

    logger.debug("Time-domain metrics: %s", result)
    return result


# ---------------------------------------------------------------------------
# Step 4: Frequency-domain HRV metrics (Lomb-Scargle periodogram)
# ---------------------------------------------------------------------------

def compute_frequency_domain(ibi_ms: List[float]) -> Optional[float]:
    """Compute the LF/HF power ratio using a Lomb-Scargle periodogram.

    Why Lomb-Scargle?  IBI data is *unevenly sampled* — the time between
    data points varies.  Standard FFT assumes even sampling.  Lomb-Scargle
    is designed specifically for uneven data.

    Frequency bands (standard in HRV research):
        - LF (Low Frequency):  0.04 – 0.15 Hz  → mixed sympathetic/parasympathetic
        - HF (High Frequency): 0.15 – 0.40 Hz  → parasympathetic (relaxation)
        - LF/HF ratio > 2.0   → generally suggests sympathetic dominance (stress)

    Note: Frequency-domain analysis ideally requires 2-5 minutes of data.
    With 30 seconds, results are approximate but still useful for relative
    comparison.

    Args:
        ibi_ms: List of cleaned IBI values in milliseconds.

    Returns:
        LF/HF ratio as a float, or None if computation fails.
    """
    if len(ibi_ms) < 10:
        logger.warning("Too few IBIs (%d) for frequency analysis, need ≥10", len(ibi_ms))
        return None

    try:
        # Convert IBI from ms to seconds
        ibi_s = np.array(ibi_ms) / 1000.0

        # Build the cumulative time axis (when each beat occurred)
        times = np.cumsum(ibi_s)
        times -= times[0]  # start from zero

        # Center the data (Lomb-Scargle requires zero mean)
        ibi_centered = ibi_s - np.mean(ibi_s)

        # Create a frequency grid from 0.01 to 0.5 Hz
        freqs = np.linspace(0.01, 0.5, 500)
        angular_freqs = 2 * np.pi * freqs  # Lomb-Scargle uses angular frequencies

        # Compute the periodogram (power at each frequency)
        pgram = lombscargle(times, ibi_centered, angular_freqs, normalize=True)

        # Extract power in each band
        lf_mask = (freqs >= 0.04) & (freqs < 0.15)   # Low Frequency band
        hf_mask = (freqs >= 0.15) & (freqs < 0.40)   # High Frequency band

        lf_power = np.trapezoid(pgram[lf_mask], freqs[lf_mask])  # area under curve
        hf_power = np.trapezoid(pgram[hf_mask], freqs[hf_mask])

        # Avoid division by zero
        if hf_power < 1e-10:
            logger.warning("HF power near zero, cannot compute LF/HF ratio")
            return None

        lf_hf = float(lf_power / hf_power)
        logger.debug("Frequency-domain: LF=%.4f, HF=%.4f, LF/HF=%.2f",
                      lf_power, hf_power, lf_hf)
        return round(lf_hf, 2)

    except Exception as e:
        logger.error("Frequency-domain analysis failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Step 5: Main pipeline — chains everything together
# ---------------------------------------------------------------------------

def compute_hrv(peak_indices: List[int], fps: float) -> Optional[HRVResult]:
    """Full HRV computation pipeline.

    This is the main entry point that the rest of the system calls.
    It chains all the steps together:

        peak_indices → IBI → clean → time-domain + freq-domain → HRVResult

    Args:
        peak_indices: List of peak sample indices from the BVP signal
                      (provided by SignalResult.peak_indices).
        fps: Sampling rate of the video (frames per second).

    Returns:
        HRVResult with all computed metrics, or None if there is
        insufficient data (fewer than 5 clean IBIs after artifact
        rejection).
    """
    # Step 1: Convert peaks to IBI
    ibi_raw = compute_ibi(peak_indices, fps)
    if len(ibi_raw) < 5:
        logger.warning("Insufficient raw IBIs (%d), need at least 5", len(ibi_raw))
        return None

    # Step 2: Clean artifacts
    ibi_clean = clean_ibi(ibi_raw)
    if len(ibi_clean) < 5:
        logger.warning("Insufficient clean IBIs (%d) after artifact rejection", len(ibi_clean))
        return None

    # Step 3: Time-domain metrics
    td = compute_time_domain(ibi_clean)

    # Step 4: Frequency-domain metrics
    lf_hf = compute_frequency_domain(ibi_clean)

    # Step 5: Assemble result
    result = HRVResult(
        rmssd=td["rmssd"],
        sdnn=td["sdnn"],
        pnn50=td["pnn50"],
        lf_hf_ratio=lf_hf,
        mean_hr=td["mean_hr"],
        ibi_ms=ibi_clean,
    )

    logger.info(
        "HRV analysis complete: HR=%.1f BPM, RMSSD=%.1f ms, SDNN=%.1f ms, "
        "pNN50=%.1f%%, LF/HF=%s",
        result.mean_hr, result.rmssd, result.sdnn, result.pnn50,
        f"{result.lf_hf_ratio:.2f}" if result.lf_hf_ratio is not None else "N/A",
    )

    return result
