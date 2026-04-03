"""
Signal Processing Module

Implements POS and CHROM rPPG algorithms for extracting the blood
volume pulse from raw green channel time-series data. Includes
bandpass filtering, signal normalization, BPM extraction via FFT,
peak detection, and the full processing pipeline orchestrator.

Pipeline:
    ROIResult (green/RGB signals + fps)
        → preprocess (detrend + bandpass + normalize)
        → POS algorithm × 3 ROIs     → 3 candidates
        → CHROM algorithm × 3 ROIs   → 3 candidates
        → SQI scoring (6 candidates)
        → ensemble fusion → 1 fused BVP
        → FFT → BPM
        → peak detection → peak_indices
        → SignalResult

See docs/modules/02_signal_processing.md for implementation details.
"""

import logging
from typing import List, Optional

import numpy as np
from scipy.signal import butter, detrend, filtfilt, find_peaks

from src.models import ROIResult, SignalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1a: Bandpass filter
# ---------------------------------------------------------------------------

def bandpass_filter(signal: np.ndarray, fps: float,
                    low: float = 0.7, high: float = 3.5,
                    order: int = 4) -> np.ndarray:
    """Apply a zero-phase Butterworth bandpass filter.

    The passband [0.7, 3.5] Hz corresponds to [42, 210] BPM, covering
    all physiological heart rates including stressed/exercising states.

    Why zero-phase?  A normal filter shifts the signal in time (phase
    distortion).  `filtfilt` runs the filter forward then backward,
    cancelling the phase shift.  This is critical for accurate peak
    detection downstream.

    Args:
        signal: 1D numpy array of the input signal.
        fps: Sampling rate in Hz (frames per second).
        low: Lower cutoff frequency in Hz (default 0.7 = 42 BPM).
        high: Upper cutoff frequency in Hz (default 3.5 = 210 BPM).
        order: Filter order (default 4, good balance of sharpness/stability).

    Returns:
        Filtered 1D numpy array, same length as input.
    """
    nyquist = fps / 2.0
    low_norm = low / nyquist
    high_norm = high / nyquist

    # Clamp to valid range (0, 1) exclusive for butter
    low_norm = max(low_norm, 1e-5)
    high_norm = min(high_norm, 1.0 - 1e-5)

    b, a = butter(order, [low_norm, high_norm], btype='band')
    return filtfilt(b, a, signal)


# ---------------------------------------------------------------------------
# Step 1b: Moving average normalization
# ---------------------------------------------------------------------------

def normalize_signal(signal: np.ndarray, window_size: int) -> np.ndarray:
    """Divide signal by its local mean to remove amplitude modulation.

    When lighting changes slowly (e.g., someone walks past a lamp), the
    overall signal level shifts.  Dividing by a rolling average removes
    this slow modulation while preserving the fast cardiac oscillation.

    Args:
        signal: 1D numpy array.
        window_size: Number of samples for the rolling mean window.
                     Typically ~1.5 seconds of samples (e.g., 45 at 30 fps).

    Returns:
        Normalized 1D numpy array, same length as input.
    """
    kernel = np.ones(window_size) / window_size
    local_mean = np.convolve(signal, kernel, mode='same')
    local_mean[local_mean < 1e-8] = 1e-8  # prevent division by zero
    return signal / local_mean


# ---------------------------------------------------------------------------
# Step 2: POS Algorithm (Wang et al., 2017)
# ---------------------------------------------------------------------------

def pos_algorithm(rgb_signal: np.ndarray, fps: float,
                  window_seconds: float = 1.6) -> np.ndarray:
    """Extract pulse signal using the POS (Plane-Orthogonal-to-Skin) method.

    How it works:
        1. Take a sliding window of RGB data
        2. Normalize each window by its mean (temporal normalization)
        3. Project onto a plane orthogonal to the skin-tone direction:
           S1 = G - B
           S2 = G + B - 2R
        4. Adaptively combine: h = S1 + alpha * S2
           where alpha = std(S1) / std(S2)
        5. Overlap-add all windows to get the final pulse signal

    The key insight: blood volume changes affect R, G, B differently
    than motion or lighting.  This projection isolates the blood signal.

    Args:
        rgb_signal: Numpy array of shape (N, 3), columns are [R, G, B].
        fps: Sampling rate in Hz.
        window_seconds: Sliding window length in seconds (default 1.6s).

    Returns:
        1D numpy array of the extracted pulse signal, length N.
    """
    N = rgb_signal.shape[0]
    window = int(window_seconds * fps)
    pulse = np.zeros(N)

    for start in range(0, N - window, 1):
        end = start + window
        segment = rgb_signal[start:end, :]

        # Temporal normalization: divide each channel by its mean
        mean = np.mean(segment, axis=0)
        if np.any(mean < 1e-8):
            continue
        normalized = segment / mean

        # Projection onto the plane orthogonal to skin-tone
        S1 = normalized[:, 1] - normalized[:, 2]           # G - B
        S2 = (normalized[:, 1] + normalized[:, 2]
              - 2.0 * normalized[:, 0])                     # G + B - 2R

        # Adaptive combination: weight S2 by the ratio of standard deviations
        alpha = np.std(S1) / (np.std(S2) + 1e-8)
        h = S1 + alpha * S2

        # Overlap-add: accumulate the zero-meaned window contribution
        pulse[start:end] += h - np.mean(h)

    return pulse


# ---------------------------------------------------------------------------
# Step 3: CHROM Algorithm (de Haan & Jeanne, 2013)
# ---------------------------------------------------------------------------

def chrom_algorithm(rgb_signal: np.ndarray, fps: float,
                    window_seconds: float = 1.6) -> np.ndarray:
    """Extract pulse signal using the CHROM (Chrominance-based) method.

    How it works:
        1. Take a sliding window of RGB data
        2. Normalize by window mean (temporal normalization)
        3. Compute chrominance signals:
           Xs = 3R - 2G
           Ys = 1.5R + G - 1.5B
        4. Adaptively combine: h = Xs - alpha * Ys
           where alpha = std(Xs) / std(Ys)
        5. Overlap-add all windows

    CHROM uses a different color model than POS.  It separates the
    pulsatile signal from specular reflections using chrominance
    (color-difference) channels.

    Args:
        rgb_signal: Numpy array of shape (N, 3), columns are [R, G, B].
        fps: Sampling rate in Hz.
        window_seconds: Sliding window length in seconds.

    Returns:
        1D numpy array of the extracted pulse signal, length N.
    """
    N = rgb_signal.shape[0]
    window = int(window_seconds * fps)
    pulse = np.zeros(N)

    for start in range(0, N - window, 1):
        end = start + window
        segment = rgb_signal[start:end, :]

        mean = np.mean(segment, axis=0)
        if np.any(mean < 1e-8):
            continue
        normalized = segment / mean

        # Chrominance projections
        Xs = 3.0 * normalized[:, 0] - 2.0 * normalized[:, 1]   # 3R - 2G
        Ys = (1.5 * normalized[:, 0] + normalized[:, 1]
              - 1.5 * normalized[:, 2])                          # 1.5R + G - 1.5B

        # Adaptive combination
        alpha = np.std(Xs) / (np.std(Ys) + 1e-8)
        h = Xs - alpha * Ys

        # Overlap-add
        pulse[start:end] += h - np.mean(h)

    return pulse


# ---------------------------------------------------------------------------
# Step 4: BPM Extraction via FFT
# ---------------------------------------------------------------------------

def extract_bpm(bvp_signal: np.ndarray, fps: float,
                low_bpm: float = 42, high_bpm: float = 200) -> Optional[float]:
    """Estimate heart rate from the dominant frequency in the BVP signal.

    How it works:
        1. Compute the FFT (frequency spectrum) of the BVP signal
        2. Look only at frequencies corresponding to [42, 200] BPM
        3. Find the frequency with the highest power
        4. Convert Hz → BPM (multiply by 60)

    Args:
        bvp_signal: 1D numpy array of the blood volume pulse signal.
        fps: Sampling rate in Hz.
        low_bpm: Minimum plausible heart rate (default 42 BPM).
        high_bpm: Maximum plausible heart rate (default 200 BPM).

    Returns:
        Estimated heart rate in BPM, or None if no valid peak found.
    """
    N = len(bvp_signal)
    if N < 2:
        return None

    freqs = np.fft.rfftfreq(N, d=1.0 / fps)
    spectrum = np.abs(np.fft.rfft(bvp_signal))

    # Convert BPM limits to Hz
    low_hz = low_bpm / 60.0
    high_hz = high_bpm / 60.0
    mask = (freqs >= low_hz) & (freqs <= high_hz)

    if not np.any(mask):
        logger.warning("No frequencies in physiological range [%.1f, %.1f] Hz",
                       low_hz, high_hz)
        return None

    valid_freqs = freqs[mask]
    valid_spectrum = spectrum[mask]
    peak_freq = valid_freqs[np.argmax(valid_spectrum)]

    bpm = peak_freq * 60.0
    logger.debug("FFT peak at %.3f Hz → %.1f BPM", peak_freq, bpm)
    return round(float(bpm), 1)


# ---------------------------------------------------------------------------
# Step 5: Peak Detection for IBI
# ---------------------------------------------------------------------------

def detect_peaks(bvp_signal: np.ndarray, fps: float) -> List[int]:
    """Find peaks in the BVP signal for IBI computation.

    Uses SciPy's find_peaks with adaptive parameters:
        - min distance: 0.4s between peaks (~150 BPM max)
        - prominence: 0.3 × signal std (adapts to signal strength)

    Downstream, Module 04 (HRV) converts these peak positions to
    inter-beat intervals for HRV metric computation.

    Args:
        bvp_signal: 1D numpy array of the BVP signal.
        fps: Sampling rate in Hz.

    Returns:
        List of integer sample indices where peaks were detected.
    """
    if len(bvp_signal) < 3:
        return []

    min_distance = int(fps * 0.4)  # minimum 0.4s between beats
    prominence = 0.3 * np.std(bvp_signal)

    # Ensure minimum prominence to avoid detecting noise peaks
    prominence = max(prominence, 1e-6)

    peaks, _ = find_peaks(
        bvp_signal,
        distance=max(min_distance, 1),
        prominence=prominence,
    )

    logger.debug("Detected %d peaks in %d samples (%.1f s)",
                 len(peaks), len(bvp_signal), len(bvp_signal) / fps)

    return peaks.tolist()


# ---------------------------------------------------------------------------
# Helper: Construct RGB signal from green channel
# ---------------------------------------------------------------------------

def _green_to_synthetic_rgb(green_signal: np.ndarray) -> np.ndarray:
    """Create a synthetic RGB array from a single green channel.

    The POS and CHROM algorithms expect (N, 3) RGB input. When only
    the green channel is available, we construct a synthetic RGB by
    adding small offsets.  This works because both algorithms use
    relative channel differences, and the cardiac component is
    primarily in the green channel.

    Args:
        green_signal: 1D numpy array of green channel values.

    Returns:
        Numpy array of shape (N, 3) with columns [R, G, B].
    """
    green = np.asarray(green_signal, dtype=np.float64)
    return np.column_stack([
        green * 0.95,   # R: slightly lower than G
        green,          # G: original
        green * 0.98,   # B: slightly lower than G
    ])


# ---------------------------------------------------------------------------
# Step 6: Main orchestrator — full processing pipeline
# ---------------------------------------------------------------------------

def process_signals(roi_result: ROIResult) -> SignalResult:
    """Full signal processing pipeline: ROIResult → SignalResult.

    This is the main entry point that the API calls.  It chains all
    processing steps together:

        1. For each of 3 ROIs:
           a. Preprocess green signal (detrend + bandpass + normalize)
           b. Construct RGB (true if available, synthetic otherwise)
           c. Run POS algorithm → candidate
           d. Run CHROM algorithm → candidate
        2. Score all 6 candidates with SQI engine
        3. Fuse using quality-weighted average
        4. Extract BPM via FFT
        5. Detect peaks for IBI derivation
        6. Package as SignalResult

    Args:
        roi_result: ROIResult from the ROI extraction module.

    Returns:
        SignalResult with the fused BVP waveform, BPM, peak indices,
        and quality metrics.
    """
    from src.ensemble import fuse_signals
    from src.sqi_engine import compute_sqi

    fps = roi_result.fps
    green_signals = roi_result.green_signals
    rgb_signals = roi_result.rgb_signals
    num_rois = len(green_signals)

    candidates = []
    candidate_labels = []
    per_roi_sqi_scores = []

    for roi_idx in range(num_rois):
        green = np.array(green_signals[roi_idx], dtype=np.float64)

        if len(green) < int(fps * 2):
            logger.warning("ROI %d signal too short (%d samples), skipping",
                           roi_idx, len(green))
            per_roi_sqi_scores.append(0.0)
            continue

        # ── Step 1: Preprocessing ──
        # Detrend: remove slow baseline drift
        green_detrended = detrend(green, type='linear')

        # Bandpass filter: keep only cardiac frequencies
        green_preproc = bandpass_filter(green_detrended, fps)

        # ── Step 2: Construct RGB input ──
        if (rgb_signals is not None
                and roi_idx < len(rgb_signals)
                and len(rgb_signals[roi_idx]) == len(green)):
            # True RGB available from ROI extractor
            rgb = np.array(rgb_signals[roi_idx], dtype=np.float64)
            logger.debug("ROI %d: using true RGB signal", roi_idx)
        else:
            # Synthetic RGB from preprocessed green channel (Option A)
            rgb = _green_to_synthetic_rgb(green_preproc)
            logger.debug("ROI %d: using synthetic RGB from green", roi_idx)

        # ── Step 3: Run POS algorithm ──
        pos_pulse = pos_algorithm(rgb, fps)
        if np.std(pos_pulse) > 1e-10:
            pos_filtered = bandpass_filter(pos_pulse, fps)
        else:
            pos_filtered = pos_pulse

        # ── Step 4: Run CHROM algorithm ──
        chrom_pulse = chrom_algorithm(rgb, fps)
        if np.std(chrom_pulse) > 1e-10:
            chrom_filtered = bandpass_filter(chrom_pulse, fps)
        else:
            chrom_filtered = chrom_pulse

        candidates.append(pos_filtered)
        candidate_labels.append(f"POS-ROI{roi_idx}")
        candidates.append(chrom_filtered)
        candidate_labels.append(f"CHROM-ROI{roi_idx}")

        # ── SQI for this ROI (average of POS and CHROM) ──
        pos_sqi, _, _ = compute_sqi(pos_filtered, fps)
        chrom_sqi, _, _ = compute_sqi(chrom_filtered, fps)
        per_roi_sqi_scores.append(round((pos_sqi + chrom_sqi) / 2.0, 3))

    # ── Handle case where no valid candidates were produced ──
    if len(candidates) == 0:
        logger.error("No valid candidate signals produced")
        empty_signal = [0.0] * (len(green_signals[0]) if green_signals else 0)
        return SignalResult(
            bvp_signal=empty_signal,
            bpm=None,
            peak_indices=[],
            sqi_score=0.0,
            sqi_level="LOW",
            per_roi_sqi=per_roi_sqi_scores,
        )

    # ── Score each candidate signal ──
    sqi_scores = []
    for i, candidate in enumerate(candidates):
        score, _, _ = compute_sqi(candidate, fps)
        sqi_scores.append(score)
        logger.debug("Candidate %s: SQI=%.3f", candidate_labels[i], score)

    # ── Ensemble fusion: weighted average ──
    fused = fuse_signals(candidates, sqi_scores)

    # Final bandpass filter on fused signal
    if np.std(fused) > 1e-10:
        fused = bandpass_filter(fused, fps)

    # ── Composite SQI for the fused signal ──
    composite_sqi, sqi_level, _ = compute_sqi(fused, fps)

    # ── BPM extraction ──
    bpm = extract_bpm(fused, fps)

    # If SQI is LOW, suppress BPM output
    if sqi_level == "LOW":
        logger.warning("SQI is LOW (%.3f), suppressing BPM output", composite_sqi)
        bpm = None

    # ── Peak detection ──
    peaks = detect_peaks(fused, fps)

    logger.info(
        "Signal processing complete: BPM=%s, SQI=%.3f (%s), peaks=%d, "
        "candidates=%d",
        f"{bpm:.1f}" if bpm is not None else "suppressed",
        composite_sqi, sqi_level, len(peaks), len(candidates),
    )

    return SignalResult(
        bvp_signal=fused.tolist(),
        bpm=bpm,
        peak_indices=peaks,
        sqi_score=round(composite_sqi, 3),
        sqi_level=sqi_level,
        per_roi_sqi=per_roi_sqi_scores,
    )
