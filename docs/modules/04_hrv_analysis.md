# Module 4: HRV Analysis

Owner: P3 (Backend Lead)

## Purpose

Compute heart rate variability metrics from inter-beat interval (IBI) data
derived from the BVP signal peaks. Produces both time-domain metrics (RMSSD,
SDNN, pNN50) and frequency-domain metrics (LF/HF ratio) that feed into the
stress classifier.

## Inputs and Outputs

**Input:** List of peak indices from SignalResult + sampling rate (fps).

**Output:** `HRVResult` dataclass containing all computed metrics and the
IBI array in milliseconds.

## Dependencies

- `numpy` for core computation
- `neurokit2` for validated frequency-domain analysis (optional but recommended)

## Implementation Guide

### Step 1: Convert Peak Indices to IBI

```python
import numpy as np

def compute_ibi(peak_indices, fps):
    """Convert peak sample indices to inter-beat intervals in milliseconds.

    Args:
        peak_indices: list of integer sample indices where peaks occur
        fps: sampling rate of the BVP signal

    Returns:
        list of IBI values in milliseconds
    """
    if len(peak_indices) < 2:
        return []

    peaks = np.array(peak_indices)
    intervals_samples = np.diff(peaks)
    intervals_ms = (intervals_samples / fps) * 1000.0

    return intervals_ms.tolist()
```

### Step 2: Artifact Rejection on IBI

Raw IBI data from rPPG often contains outliers from missed or false peaks.
Remove physiologically impossible intervals before computing HRV:

```python
def clean_ibi(ibi_ms, min_ibi=300, max_ibi=1500, max_change_pct=0.3):
    """Remove physiologically impossible IBI values.

    Args:
        ibi_ms: list of IBI values in milliseconds
        min_ibi: minimum plausible IBI (300 ms = 200 BPM)
        max_ibi: maximum plausible IBI (1500 ms = 40 BPM)
        max_change_pct: maximum allowed percentage change between
                        consecutive IBIs (0.3 = 30%)

    Returns:
        cleaned list of IBI values
    """
    if len(ibi_ms) < 2:
        return ibi_ms

    cleaned = [ibi_ms[0]] if min_ibi <= ibi_ms[0] <= max_ibi else []

    for i in range(1, len(ibi_ms)):
        val = ibi_ms[i]
        if val < min_ibi or val > max_ibi:
            continue
        if cleaned:
            change = abs(val - cleaned[-1]) / cleaned[-1]
            if change > max_change_pct:
                continue
        cleaned.append(val)

    return cleaned
```

### Step 3: Time-Domain HRV Metrics

```python
def compute_time_domain(ibi_ms):
    """Compute time-domain HRV metrics.

    Args:
        ibi_ms: list of cleaned IBI values in milliseconds

    Returns:
        dict with keys: rmssd, sdnn, pnn50, mean_hr
    """
    ibi = np.array(ibi_ms)
    diffs = np.diff(ibi)

    rmssd = float(np.sqrt(np.mean(diffs ** 2)))
    sdnn = float(np.std(ibi, ddof=1))
    pnn50 = float(np.sum(np.abs(diffs) > 50) / len(diffs) * 100) if len(diffs) > 0 else 0.0
    mean_hr = float(60000.0 / np.mean(ibi)) if np.mean(ibi) > 0 else 0.0

    return {
        "rmssd": round(rmssd, 2),
        "sdnn": round(sdnn, 2),
        "pnn50": round(pnn50, 2),
        "mean_hr": round(mean_hr, 1),
    }
```

### Step 4: Frequency-Domain HRV Metrics

Frequency-domain analysis requires converting the unevenly sampled IBI series
into a power spectral density estimate. The Lomb-Scargle periodogram works
directly on unevenly sampled data.

**Using NeuroKit2 (recommended):**
```python
import neurokit2 as nk

def compute_frequency_domain(ibi_ms):
    """Compute LF/HF ratio using NeuroKit2.

    LF band: 0.04 - 0.15 Hz (reflects mixed sympathetic/parasympathetic)
    HF band: 0.15 - 0.40 Hz (reflects parasympathetic activity)
    LF/HF ratio > 2.0 generally suggests sympathetic dominance (stress).

    Note: Frequency-domain analysis ideally requires 2-5 minutes of data.
    With 30 seconds, results are approximate but still useful for
    relative comparison.
    """
    try:
        # Construct cumulative time array
        ibi = np.array(ibi_ms) / 1000.0  # convert to seconds
        times = np.cumsum(ibi)

        # NeuroKit2 expects peaks in samples or a peaks dict
        # We can compute HRV from the RR intervals directly
        hrv = nk.hrv_frequency(
            {"RRI": ibi_ms},
            sampling_rate=1000,  # IBI is in ms, so "sampling rate" is 1000
            normalize=True,
        )

        lf_hf = hrv.get("HRV_LFHF", [None])[0]
        return float(lf_hf) if lf_hf is not None else None
    except Exception:
        return None
```

**Manual alternative (if NeuroKit2 gives trouble):**
```python
from scipy.signal import lombscargle

def compute_lf_hf_manual(ibi_ms):
    """Manual Lomb-Scargle based LF/HF computation."""
    ibi_s = np.array(ibi_ms) / 1000.0
    times = np.cumsum(ibi_s)
    times -= times[0]

    # Subtract mean for Lomb-Scargle
    ibi_centered = ibi_s - np.mean(ibi_s)

    # Frequency grid
    freqs = np.linspace(0.01, 0.5, 500)
    angular_freqs = 2 * np.pi * freqs
    pgram = lombscargle(times, ibi_centered, angular_freqs, normalize=True)

    # Band powers
    lf_mask = (freqs >= 0.04) & (freqs < 0.15)
    hf_mask = (freqs >= 0.15) & (freqs < 0.40)

    lf_power = np.trapz(pgram[lf_mask], freqs[lf_mask])
    hf_power = np.trapz(pgram[hf_mask], freqs[hf_mask])

    if hf_power < 1e-10:
        return None
    return float(lf_power / hf_power)
```

### Step 5: Assemble HRVResult

```python
from src.models import HRVResult

def compute_hrv(peak_indices, fps):
    """Full HRV computation pipeline.

    Args:
        peak_indices: list of peak sample indices from BVP
        fps: sampling rate

    Returns:
        HRVResult or None if insufficient data
    """
    ibi_raw = compute_ibi(peak_indices, fps)
    if len(ibi_raw) < 5:
        return None

    ibi_clean = clean_ibi(ibi_raw)
    if len(ibi_clean) < 5:
        return None

    td = compute_time_domain(ibi_clean)
    lf_hf = compute_frequency_domain(ibi_clean)

    return HRVResult(
        rmssd=td["rmssd"],
        sdnn=td["sdnn"],
        pnn50=td["pnn50"],
        lf_hf_ratio=lf_hf,
        mean_hr=td["mean_hr"],
        ibi_ms=ibi_clean,
    )
```

## Normal Ranges Reference

These ranges are for healthy, resting adults and serve as sanity checks:

| Metric | Typical Range | Interpretation |
|--------|---------------|----------------|
| RMSSD | 19 - 75 ms | Higher = more parasympathetic activity |
| SDNN | 30 - 100 ms | Higher = greater overall HRV |
| pNN50 | 1 - 50% | Higher = more parasympathetic activity |
| LF/HF | 0.5 - 5.0 | Higher = more sympathetic dominance |
| Mean HR | 50 - 100 BPM | Resting range |

## Testing

```bash
pytest tests/unit/test_hrv_analyzer.py -v
```

Key validations:
- IBI length is peaks minus one
- RMSSD/SDNN are positive and within plausible ranges for the test data
- Stressed IBI produces lower RMSSD than resting IBI
- Handles fewer than 5 IBIs gracefully (returns None)
