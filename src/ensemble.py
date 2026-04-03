"""
Ensemble Fusion Module

Combines outputs from multiple rPPG algorithms (POS, CHROM) across
multiple ROIs into a single fused blood volume pulse signal, weighted
by per-signal quality scores.

The idea: we have 6 candidate signals (2 algorithms × 3 ROIs).
Some are better than others — forehead usually gives a cleaner signal
than cheeks, and one algorithm may outperform the other depending on
lighting.  By weighting each candidate by its quality score (SQI),
the best signals contribute most to the final output.

See docs/modules/02_signal_processing.md for implementation details.
"""

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


def fuse_signals(candidates: List[np.ndarray],
                 sqi_scores: List[float]) -> np.ndarray:
    """Weighted average of candidate BVP signals based on quality scores.

    Each candidate signal is multiplied by its SQI score, then all are
    summed and divided by the total weight.  This ensures that higher-
    quality signals dominate the fused output.

    Example:
        candidates = [signal_A, signal_B, signal_C]
        sqi_scores = [0.8, 0.2, 0.5]
        fused = (0.8*A + 0.2*B + 0.5*C) / (0.8 + 0.2 + 0.5)

    Args:
        candidates: List of 1D numpy arrays (candidate BVP signals).
                    All must have the same length.
        sqi_scores: List of floats (quality score per candidate, 0 to 1).
                    Same length as candidates.

    Returns:
        Fused 1D numpy array, same length as each candidate.
    """
    if len(candidates) == 0:
        raise ValueError("No candidate signals to fuse")

    total_weight = sum(sqi_scores)

    if total_weight < 1e-8:
        # All signals are garbage; return the first one and let the SQI
        # gate downstream handle it (it will suppress the output)
        logger.warning("All SQI scores near zero, returning first candidate")
        return np.array(candidates[0], dtype=np.float64)

    fused = np.zeros_like(candidates[0], dtype=np.float64)
    for signal, weight in zip(candidates, sqi_scores):
        fused += weight * np.array(signal, dtype=np.float64)
    fused /= total_weight

    logger.debug("Fused %d candidates (total weight=%.3f)",
                 len(candidates), total_weight)

    return fused
