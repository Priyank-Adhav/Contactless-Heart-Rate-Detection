"""
Shared test fixtures and configuration.

Provides synthetic signals, mock data, and reusable test utilities
shared across the unit, API, and integration test suites.
"""

import numpy as np
import pytest


@pytest.fixture
def synthetic_bvp_72bpm():
    """Clean sinusoidal BVP signal at 72 BPM (1.2 Hz), 30 fps, 30 seconds."""
    fps = 30
    duration = 30
    num_samples = fps * duration
    t = np.linspace(0, duration, num_samples, endpoint=False)
    signal = np.sin(2 * np.pi * 1.2 * t)
    return signal, fps


@pytest.fixture
def synthetic_bvp_60bpm():
    """Clean sinusoidal BVP signal at 60 BPM (1.0 Hz), 30 fps, 30 seconds."""
    fps = 30
    duration = 30
    num_samples = fps * duration
    t = np.linspace(0, duration, num_samples, endpoint=False)
    signal = np.sin(2 * np.pi * 1.0 * t)
    return signal, fps


@pytest.fixture
def noisy_signal():
    """Random noise with no cardiac component."""
    fps = 30
    num_samples = 30 * fps
    signal = np.random.randn(num_samples)
    return signal, fps


@pytest.fixture
def synthetic_ibi_resting():
    """IBI array simulating a resting heart rate (~70 BPM) with normal variability.

    Mean IBI ~857 ms with SD ~40 ms, which represents a healthy resting state.
    """
    np.random.seed(42)
    mean_ibi = 857.0  # ~70 BPM
    ibi = np.random.normal(loc=mean_ibi, scale=40.0, size=35)
    ibi = np.clip(ibi, 600, 1200)
    return ibi.tolist()


@pytest.fixture
def synthetic_ibi_stressed():
    """IBI array simulating a stressed state (~95 BPM) with low variability.

    Mean IBI ~631 ms with SD ~15 ms, representing elevated sympathetic activity.
    """
    np.random.seed(42)
    mean_ibi = 631.0  # ~95 BPM
    ibi = np.random.normal(loc=mean_ibi, scale=15.0, size=45)
    ibi = np.clip(ibi, 400, 900)
    return ibi.tolist()


@pytest.fixture
def sample_roi_signals():
    """Three synthetic ROI green channel signals with known cardiac frequency.

    Forehead signal is strongest, left cheek moderate, right cheek weakest.
    All contain 1.2 Hz (72 BPM) cardiac component with varying noise levels.
    """
    fps = 30
    duration = 30
    n = fps * duration
    t = np.linspace(0, duration, n, endpoint=False)

    cardiac = np.sin(2 * np.pi * 1.2 * t)

    forehead = 140.0 + 0.5 * cardiac + 0.1 * np.random.randn(n)
    left_cheek = 135.0 + 0.3 * cardiac + 0.15 * np.random.randn(n)
    right_cheek = 130.0 + 0.2 * cardiac + 0.2 * np.random.randn(n)

    return [forehead.tolist(), left_cheek.tolist(), right_cheek.tolist()], fps
