# Module 3: Signal Quality Index Engine

Owner: P1 (Pipeline Lead)

## Purpose

Determine whether a candidate BVP signal contains a reliable cardiac component
or is dominated by noise. The SQI engine computes a composite quality score from
three independent metrics and outputs a confidence level that gates downstream
processing. When quality is LOW, the system suppresses BPM output rather than
presenting an unreliable measurement.

## Inputs and Outputs

**Input:** A 1D BVP signal array and the sampling rate (fps).

**Output:** A tuple of `(score, level, color)`:
- `score`: float between 0.0 and 1.0
- `level`: one of "HIGH", "MEDIUM", "LOW"
- `color`: "green", "yellow", or "red" (for UI traffic light)

## Dependencies

- `numpy` for numerical computation
- `scipy.signal` for FFT and spectral analysis
- `scipy.stats` for kurtosis calculation

## Implementation Guide

### Metric 1: Spectral SNR (Weight: 0.50)

Measures how much of the signal's power is concentrated in the cardiac frequency
band versus spread across all frequencies.

```python
import numpy as np

def compute_spectral_snr(signal, fps, hr_low=0.7, hr_high=3.5):
    """Compute spectral signal-to-noise ratio.

    Ratio of power in the cardiac band [0.7, 3.5] Hz to total power.
    A strong cardiac signal will have most of its energy concentrated
    in a narrow band around the true heart rate.
    """
    N = len(signal)
    freqs = np.fft.rfftfreq(N, d=1.0 / fps)
    power = np.abs(np.fft.rfft(signal)) ** 2

    cardiac_mask = (freqs >= hr_low) & (freqs <= hr_high)
    cardiac_power = np.sum(power[cardiac_mask])
    total_power = np.sum(power[1:])  # exclude DC component

    if total_power < 1e-10:
        return 0.0

    ratio = cardiac_power / total_power

    # Map ratio to a 0-1 score. Typical clean rPPG signals have ratio > 0.5.
    # Noise has ratio around 0.1-0.2 (since the cardiac band is ~40% of 0-15 Hz).
    score = np.clip((ratio - 0.15) / 0.45, 0.0, 1.0)
    return float(score)
```

### Metric 2: Kurtosis Score (Weight: 0.25)

Clean pulse signals have a characteristic amplitude distribution. Random noise
tends toward Gaussian (kurtosis near 0), while strong pulse signals have higher
kurtosis due to peaked waveform morphology.

```python
from scipy.stats import kurtosis

def compute_kurtosis_score(signal):
    """Score based on excess kurtosis of the signal.

    Clean BVP signals typically have kurtosis between 1.0 and 5.0
    (excess kurtosis, Fisher definition). Values outside this range
    suggest either noise (near 0) or extreme artifacts (very high).
    """
    k = kurtosis(signal, fisher=True)

    # Ideal range: 1.0 to 5.0
    if 1.0 <= k <= 5.0:
        score = 1.0
    elif 0.5 <= k < 1.0 or 5.0 < k <= 7.0:
        score = 0.6
    elif 0.0 <= k < 0.5 or 7.0 < k <= 10.0:
        score = 0.3
    else:
        score = 0.1

    return float(score)
```

### Metric 3: Spectral Purity (Weight: 0.25)

Measures the width of the dominant FFT peak. A clean cardiac signal produces a
narrow, well-defined peak. Noise produces a broad, flat spectrum.

```python
def compute_spectral_purity(signal, fps, hr_low=0.7, hr_high=3.5):
    """Score based on the width of the dominant spectral peak.

    Uses full-width at half-maximum (FWHM) of the highest peak in
    the cardiac band. Narrower peaks indicate cleaner signals.
    """
    N = len(signal)
    freqs = np.fft.rfftfreq(N, d=1.0 / fps)
    spectrum = np.abs(np.fft.rfft(signal))

    cardiac_mask = (freqs >= hr_low) & (freqs <= hr_high)
    cardiac_freqs = freqs[cardiac_mask]
    cardiac_spectrum = spectrum[cardiac_mask]

    if len(cardiac_spectrum) == 0:
        return 0.0

    peak_idx = np.argmax(cardiac_spectrum)
    peak_value = cardiac_spectrum[peak_idx]
    half_max = peak_value / 2.0

    # Find FWHM
    above_half = cardiac_spectrum >= half_max
    transitions = np.diff(above_half.astype(int))
    rises = np.where(transitions == 1)[0]
    falls = np.where(transitions == -1)[0]

    if len(rises) == 0 or len(falls) == 0:
        # Cannot determine width; assume moderately pure
        return 0.5

    # Find the rise/fall pair around the peak
    left = rises[rises < peak_idx]
    right = falls[falls > peak_idx]

    if len(left) == 0 or len(right) == 0:
        return 0.5

    fwhm_bins = right[0] - left[-1]
    freq_resolution = cardiac_freqs[1] - cardiac_freqs[0] if len(cardiac_freqs) > 1 else 1.0
    fwhm_hz = fwhm_bins * freq_resolution

    # Score: FWHM < 0.15 Hz is excellent, > 0.5 Hz is poor
    score = np.clip(1.0 - (fwhm_hz - 0.1) / 0.5, 0.0, 1.0)
    return float(score)
```

### Composite Score and Decision

```python
def compute_sqi(signal, fps):
    """Compute composite signal quality index.

    Returns:
        score: float in [0.0, 1.0]
        level: "HIGH", "MEDIUM", or "LOW"
        color: "green", "yellow", or "red"
    """
    snr = compute_spectral_snr(signal, fps)
    kurt = compute_kurtosis_score(signal)
    purity = compute_spectral_purity(signal, fps)

    score = 0.50 * snr + 0.25 * kurt + 0.25 * purity
    score = float(np.clip(score, 0.0, 1.0))

    if score > 0.6:
        return score, "HIGH", "green"
    elif score > 0.35:
        return score, "MEDIUM", "yellow"
    else:
        return score, "LOW", "red"
```

### Integration with Pipeline

The SQI engine is called in two places:

1. **Per-candidate scoring** (in ensemble.py): Score each of the 6 candidate
   signals (2 algorithms x 3 ROIs) before fusion. Use scores as fusion weights.
2. **Post-fusion validation**: Score the final fused signal. If the fused signal
   is still LOW quality, suppress the BPM output.

## Threshold Tuning

The thresholds (0.6 for HIGH, 0.35 for MEDIUM) were chosen as reasonable
starting points. During testing with real videos:

- If too many valid signals are being rejected, lower thresholds.
- If garbage BPM values are getting through, raise thresholds.

Tune using the test fixtures and at least 2-3 real face videos.

## Testing

```bash
pytest tests/unit/test_sqi_engine.py -v
```

Key validations:
- Clean sinusoid scores HIGH
- Random noise scores LOW
- Score is always in [0.0, 1.0]
- Output suppression triggers on LOW quality
