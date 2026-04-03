"""
FastAPI application entry point.

Serves the frontend dashboard and exposes REST endpoints for
video upload analysis and (optionally) live webcam frame processing.

See docs/modules/06_api_server.md for implementation details.
"""

# Dummy HRV and stress, since not implemented
# from ..hrv_analyzer import analyze_hrv
# from ..stress_classifier import classify_stress
import dataclasses

import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.staticfiles import StaticFiles

from ..models import AnalysisResult, ROIResult
from ..signal_processor import process_roi_signals

app = FastAPI(
    title="PulseGuard API",
    description="Contact-free cardiac stress monitoring via facial video analysis",
    version="0.1.0",
)


# --- Health check ---

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# TODO: POST /api/analyze/webcam - accepts base64 frames, returns live results

@app.post("/api/analyze")
async def analyze_video(video: UploadFile = File(...)):
    # For now, ignore the video and generate dummy ROI data
    # In full implementation, extract ROIs from video

    # Generate dummy green signals: 3 ROIs, 900 samples (30 fps * 30 sec)
    fps = 30
    num_frames = 900
    np.random.seed(42)  # For reproducible dummy data
    # Simulate cardiac signal at 72 BPM (1.2 Hz)
    t = np.linspace(0, num_frames / fps, num_frames, endpoint=False)
    cardiac_signal = np.sin(2 * np.pi * 1.2 * t) + 0.1 * np.random.randn(num_frames)

    green_signals = [
        cardiac_signal.tolist(),
        (cardiac_signal + 0.05 * np.random.randn(num_frames)).tolist(),
        (cardiac_signal + 0.05 * np.random.randn(num_frames)).tolist(),
    ]

    roi_result = ROIResult(
        green_signals=green_signals,
        face_detected=True,
        fps=fps,
        frame_count=num_frames,
    )

    # Process through signal processor
    signal_result = process_roi_signals(roi_result)

    # Dummy HRV (since not implemented)
    hrv_result = None  # For now

    # Dummy stress
    stress_level = "MODERATE"
    stress_confidence = 0.75

    analysis_result = AnalysisResult(
        signal=signal_result,
        hrv=hrv_result,
        stress_level=stress_level,
        stress_confidence=stress_confidence,
        processing_time_ms=1500.0,
        warnings=[]
    )

    return dataclasses.asdict(analysis_result)


# Serve frontend files
app.mount("/", StaticFiles(directory="/Users/anu/Desktop/Samvedna1/Contactless-Heart-Rate-Detection/frontend", html=True), name="frontend")
