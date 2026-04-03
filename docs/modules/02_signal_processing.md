# Module 2: Signal Processing

Owner: P2 (Signal Lead)

## Purpose

Transform raw green channel time-series data from the ROI extractor into a
cleaned blood volume pulse (BVP) signal, then estimate heart rate in BPM.
This module implements two rPPG algorithms (POS and CHROM) and an ensemble
fusion mechanism that combines multiple candidates weighted by quality.

## Inputs and Outputs

**Input:** `ROIResult` from the ROI extractor module (three green channel
time-series and FPS).

**Output:** `SignalResult` containing the fused BVP waveform, BPM estimate,
detected peak indices, and per-signal SQI scores.

## Dependencies

- `numpy` for numerical computation
- `scipy.signal` for filtering and peak detection
- `scipy.fft` for frequency analysis

## Implementation Guide

### Step 1: Preprocessing

Before applying rPPG algorithms, each ROI signal needs three preprocessing steps.

**1a. Detrending** -- remove slow baseline drift:
```python
from scipy.signal import detrend
signal = detrend(signal, type='linear')
```

**1b. Bandpass filtering** -- isolate the cardiac frequency band:
```python
from scipy.signal import butter, filtfilt

def bandpass_filter(signal, fps, low=0.7, high=3.5, order=4):
    """Apply a zero-phase Butterworth bandpass filter.

    The passband [0.7, 3.5] Hz corresponds to [42, 210] BPM, covering
    all physiological heart rates including stressed/exercising states.
    """
    nyquist = fps / 2.0
    low_norm = low / nyquist
    high_norm = high / nyquist
    b, a = butter(order, [low_norm, high_norm], btype='band')
    return filtfilt(b, a, signal)
```

**1c. Moving average normalization** -- divide by a rolling mean to remove
amplitude modulation from lighting changes:
```python
def normalize_signal(signal, window_size):
    """Divide signal by its local mean to remove amplitude modulation."""
    kernel = np.ones(window_size) / window_size
    local_mean = np.convolve(signal, kernel, mode='same')
    local_mean[local_mean < 1e-8] = 1e-8  # prevent division by zero
    return signal / local_mean
```

Window size should be approximately 1.5 seconds of samples (e.g., 45 samples
at 30 fps).

### Step 2: POS Algorithm

The Plane-Orthogonal-to-Skin method (Wang et al., 2017) projects the
temporally normalized RGB channels onto a plane orthogonal to the skin-tone
direction, suppressing motion and illumination artifacts.

```python
def pos_algorithm(rgb_signal, fps, window_seconds=1.6):
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
```

Note: The sliding window approach with overlap-add handles non-stationary
signals better than a single global computation.

### Step 3: CHROM Algorithm

The Chrominance-based method (de Haan & Jeanne, 2013) uses a fixed linear
combination of color channels based on a chrominance model:

```python
def chrom_algorithm(rgb_signal, fps, window_seconds=1.6):
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
```

### Step 4: BPM Extraction via FFT

```python
def extract_bpm(bvp_signal, fps, low_bpm=42, high_bpm=200):
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
```

### Step 5: Ensemble Fusion

Run POS and CHROM on each of the three ROI signals (6 candidate signals total).
Compute a quality score for each candidate, then produce a weighted average:

```python
def fuse_signals(candidates, sqi_scores):
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
```

### Step 6: Peak Detection for IBI

```python
from scipy.signal import find_peaks

def detect_peaks(bvp_signal, fps):
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
```

## RGB Signal Construction

The POS and CHROM algorithms expect an (N, 3) array with R, G, B columns.
For the hackathon, we use a simplified approach where each ROI provides a
green channel signal. To construct the RGB input:

**Option A (recommended for speed):** Use the green channel from each ROI as 
three independent "single-channel" inputs. Run POS/CHROM on a synthetic RGB 
constructed by adding small offsets:
```python
green = roi_signal
rgb = np.column_stack([green * 0.95, green, green * 0.98])
```

**Option B (more accurate, if time allows):** Extract all three color channels 
(R, G, B) from each ROI in the roi_extractor module, producing a (N, 3) array 
per ROI.

Start with Option A. Switch to Option B only if BPM accuracy is poor.

## Testing

```bash
pytest tests/unit/test_signal_processor.py -v
```

Key validations:
- Bandpass filter removes out-of-band components
- POS/CHROM extract dominant frequency from synthetic cardiac signal
- BPM is within 3 BPM of the known synthetic frequency
- BPM is always clamped to physiological range

## Common Pitfalls

1. **Nyquist limit**: At 30 fps, the maximum detectable frequency is 15 Hz.
   The cardiac band (0.7-3.5 Hz) is well within this, but be aware if using
   lower-fps video sources.
2. **Zero-phase filtering**: Always use `filtfilt` (not `lfilter`) to avoid
   phase distortion in the cardiac signal.
3. **Short signals**: POS/CHROM with sliding windows need at least
   `window_seconds` of data. A 30-second video at 30 fps gives 900 samples,
   which is sufficient. Shorter clips may require reducing the window size.
4. **Division by zero**: Both POS and CHROM divide by mean values. Guard against
   zero or near-zero means (can happen with black frames or fully occluded ROIs).
