"""
Signal Processing Module

Implements POS and CHROM rPPG algorithms for extracting the blood
volume pulse from raw green channel time-series data. Includes
bandpass filtering and signal normalization.

See docs/modules/02_signal_processing.md for implementation details.
"""

from typing import List, Optional

import numpy as np
from scipy.signal import butter, detrend, filtfilt, find_peaks

from .models import ROIResult, SignalResult


def bandpass_filter(signal: np.ndarray, fps: float, low: float = 0.7, high: float = 3.5, order: int = 4) -> np.ndarray:
    """Apply a zero-phase Butterworth bandpass filter.

    The passband [0.7, 3.5] Hz corresponds to [42, 210] BPM, covering
    all physiological heart rates including stressed/exercising states.
    """
    nyquist = fps / 2.0
    low_norm = low / nyquist
    high_norm = high / nyquist
    b, a = butter(order, [low_norm, high_norm], btype='band')
    return filtfilt(b, a, signal)


def normalize_signal(signal: np.ndarray, window_size: int) -> np.ndarray:
    """Divide signal by its local mean to remove amplitude modulation."""
    kernel = np.ones(window_size) / window_size
    local_mean = np.convolve(signal, kernel, mode='same')
    local_mean[local_mean < 1e-8] = 1e-8  # prevent division by zero
    return signal / local_mean


def pos_algorithm(rgb_signal: np.ndarray, fps: float, window_seconds: float = 1.6) -> np.ndarray:
    """Extract pulse signal using the POS method.

    Args:
        rgb_signal: numpy array of shape (N, 3), columns are R, G, B
        fps: sampling rate in Hz
        window_seconds: sliding window length in seconds

    Returns:
        pulse: 1D numpy array of the extracted pulse signal
    """
    N = rgb_signal.shape[0]
    window = int(window_seconds * fps)
    pulse = np.zeros(N)

    for start in range(0, N - window, 1):
        end = start + window
        segment = rgb_signal[start:end, :]

        # Temporal normalization
        mean = np.mean(segment, axis=0)
        if np.any(mean < 1e-8):
            continue
        normalized = segment / mean

        # Projection
        S1 = normalized[:, 1] - normalized[:, 2]       # G - B
        S2 = (normalized[:, 1] + normalized[:, 2]
              - 2.0 * normalized[:, 0])                 # G + B - 2R

        # Combine with adaptive alpha
        alpha = np.std(S1) / (np.std(S2) + 1e-8)
        h = S1 + alpha * S2

        # Overlap-add
        pulse[start:end] += h - np.mean(h)

    return pulse


def chrom_algorithm(rgb_signal: np.ndarray, fps: float, window_seconds: float = 1.6) -> np.ndarray:
    """Extract pulse signal using the CHROM method.

    Args:
        rgb_signal: numpy array of shape (N, 3), columns are R, G, B
        fps: sampling rate in Hz
        window_seconds: sliding window length

    Returns:
        pulse: 1D numpy array of the extracted pulse signal
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

        Xs = 3.0 * normalized[:, 0] - 2.0 * normalized[:, 1]
        Ys = (1.5 * normalized[:, 0] + normalized[:, 1]
              - 1.5 * normalized[:, 2])

        alpha = np.std(Xs) / (np.std(Ys) + 1e-8)
        h = Xs - alpha * Ys

        pulse[start:end] += h - np.mean(h)

    return pulse


def extract_bpm(bvp_signal: np.ndarray, fps: float, low_bpm: float = 42, high_bpm: float = 200) -> Optional[float]:
    """Estimate heart rate from the dominant frequency in the BVP signal.

    Uses FFT to find the strongest frequency component within the
    physiological heart rate range.
    """
    N = len(bvp_signal)
    freqs = np.fft.rfftfreq(N, d=1.0 / fps)
    spectrum = np.abs(np.fft.rfft(bvp_signal))

    # Restrict to physiological range
    low_hz = low_bpm / 60.0
    high_hz = high_bpm / 60.0
    mask = (freqs >= low_hz) & (freqs <= high_hz)

    if not np.any(mask):
        return None

    valid_freqs = freqs[mask]
    valid_spectrum = spectrum[mask]
    peak_freq = valid_freqs[np.argmax(valid_spectrum)]

    return peak_freq * 60.0  # convert Hz to BPM


def fuse_signals(candidates: List[np.ndarray], sqi_scores: List[float]) -> np.ndarray:
    """Weighted average of candidate BVP signals based on quality scores.

    Args:
        candidates: list of 1D numpy arrays (candidate BVP signals)
        sqi_scores: list of floats (quality score per candidate, 0 to 1)

    Returns:
        fused: 1D numpy array
    """
    total_weight = sum(sqi_scores)
    if total_weight < 1e-8:
        # All signals are garbage; return the first one and let SQI handle it
        return candidates[0]

    fused = np.zeros_like(candidates[0], dtype=float)
    for signal, weight in zip(candidates, sqi_scores):
        fused += weight * signal
    fused /= total_weight
    return fused


def detect_peaks(bvp_signal: np.ndarray, fps: float) -> List[int]:
    """Find peaks in the BVP signal for IBI computation.

    Uses adaptive prominence based on signal amplitude to handle
    varying signal strengths.
    """
    min_distance = int(fps * 0.4)  # minimum 0.4s between beats (~150 BPM max)
    prominence = 0.3 * np.std(bvp_signal)

    peaks, properties = find_peaks(
        bvp_signal,
        distance=min_distance,
        prominence=prominence,
    )
    return peaks.tolist()


def process_roi_signals(roi_result: ROIResult) -> SignalResult:
    """Process ROI signals to extract BVP and BPM.

    Args:
        roi_result: ROIResult containing three green channel signals

    Returns:
        SignalResult with fused BVP, BPM, peaks, and SQI scores
    """
    if not roi_result.face_detected or len(roi_result.green_signals) != 3:
        # Return empty result if no face detected
        return SignalResult(
            bvp_signal=[],
            bpm=None,
            peak_indices=[],
            sqi_score=0.0,
            sqi_level="LOW",
            per_roi_sqi=[0.0, 0.0, 0.0]
        )

    fps = roi_result.fps
    candidates = []
    sqi_scores = []

    for green_signal in roi_result.green_signals:
        signal = np.array(green_signal)

        # Preprocessing
        signal = detrend(signal, type='linear')
        signal = bandpass_filter(signal, fps)
        window_size = int(1.5 * fps)  # 1.5 seconds
        signal = normalize_signal(signal, window_size)

        # Construct synthetic RGB
        rgb = np.column_stack([signal * 0.95, signal, signal * 0.98])

        # Apply POS and CHROM
        pos_bvp = pos_algorithm(rgb, fps)
        chrom_bvp = chrom_algorithm(rgb, fps)

        # For now, use both and average them as candidates
        candidates.append(pos_bvp)
        candidates.append(chrom_bvp)

        # Dummy SQI scores, replace with actual SQI computation
        sqi_scores.append(1.0)  # POS
        sqi_scores.append(1.0)  # CHROM

    # Fuse all candidates (6 total: 2 per ROI)
    fused_bvp = fuse_signals(candidates, sqi_scores)

    # Extract BPM
    bpm = extract_bpm(fused_bvp, fps)

    # Detect peaks
    peak_indices = detect_peaks(fused_bvp, fps)

    # Compute composite SQI (average of per-ROI, but since we have 6, average)
    per_roi_sqi = [1.0, 1.0, 1.0]  # Dummy
    sqi_score = np.mean(per_roi_sqi)
    if sqi_score > 0.8:
        sqi_level = "HIGH"
    elif sqi_score > 0.5:
        sqi_level = "MEDIUM"
    else:
        sqi_level = "LOW"

    return SignalResult(
        bvp_signal=fused_bvp.tolist(),
        bpm=bpm,
        peak_indices=peak_indices,
        sqi_score=sqi_score,
        sqi_level=sqi_level,
        per_roi_sqi=per_roi_sqi
    )
