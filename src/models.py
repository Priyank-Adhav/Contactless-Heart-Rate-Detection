"""
Shared data structures for inter-module communication.

Every module in the pipeline consumes and produces instances of these
dataclasses. This ensures that modules can be developed and tested
independently as long as they respect the interface contract.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ROIResult:
    """Output of the ROI extraction stage.

    Contains the per-frame green channel averages for each of the three
    facial regions (forehead, left cheek, right cheek), along with
    metadata about the video source.
    """

    green_signals: List[List[float]]  # shape: [3][num_frames]
    face_detected: bool
    fps: float
    frame_count: int
    rgb_signals: Optional[List[List[List[float]]]] = None  # shape: [3 ROIs][num_frames][3 channels]
    landmarks_per_frame: Optional[list] = None  # optional, for visualization


@dataclass
class SignalResult:
    """Output of signal processing and ensemble fusion.

    Carries the cleaned blood volume pulse waveform, the estimated BPM,
    detected peak locations (for IBI derivation), and quality metrics
    for each candidate signal that contributed to the final output.
    """

    bvp_signal: List[float]
    bpm: Optional[float]  # None when SQI is too low to report
    peak_indices: List[int]
    sqi_score: float  # composite score, 0.0 to 1.0
    sqi_level: str  # "HIGH", "MEDIUM", or "LOW"
    per_roi_sqi: List[float]  # one score per ROI, for visualization


@dataclass
class HRVResult:
    """Output of HRV analysis.

    Standard time-domain and frequency-domain metrics derived from
    inter-beat intervals.
    """

    rmssd: float
    sdnn: float
    pnn50: float
    lf_hf_ratio: Optional[float]  # may be None if frequency analysis fails
    mean_hr: float
    ibi_ms: List[float]  # inter-beat intervals in milliseconds


@dataclass
class AnalysisResult:
    """Top-level result returned by the API.

    Aggregates signal processing, HRV, and stress classification outputs
    into a single response object.
    """

    signal: SignalResult
    hrv: Optional[HRVResult]
    stress_level: str  # "LOW", "MODERATE", or "HIGH"
    stress_confidence: float
    processing_time_ms: float
    warnings: List[str] = field(default_factory=list)
