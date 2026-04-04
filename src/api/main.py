"""
FastAPI application entry point.

Serves the frontend dashboard and exposes REST endpoints for
video upload analysis and (optionally) live webcam frame processing.

Pipeline orchestration:
    1. Accept video file via POST /api/analyze
    2. Save to a temp file
    3. Run the full pipeline: ROI -> Signal -> SQI gate -> HRV -> Stress
    4. Return structured JSON conforming to AnalysisResult schema
    5. Clean up the temp file

See docs/modules/06_api_server.md for implementation details.
"""

import base64
import logging
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PulseGuard API",
    description="Contact-free cardiac stress monitoring via facial video analysis",
    version="0.1.0",
)

# CORS middleware for development (frontend may be on a different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv"}

# Upper limit for uploaded video files (50 MB)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """Basic health check endpoint for monitoring and CI."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def _run_analysis_on_roi(roi_result) -> dict:
    """Run signal processing, HRV, and stress stages on an existing ROIResult.

    Shared by both the batch /api/analyze and live /api/live endpoints.
    """
    warnings = []

    if not roi_result.face_detected:
        return _error_response(
            warnings=["No face detected in the video."],
        )

    # --- Stage 2: Signal processing + ensemble fusion ---
    try:
        from src.signal_processor import process_signals
        signal_result = process_signals(roi_result)
    except ImportError:
        logger.warning("signal_processor not yet implemented, using placeholder")
        signal_result = _placeholder_signal_result(roi_result)
        warnings.append("Signal processing module not yet available; showing placeholder data.")
    except Exception as e:
        logger.error("Signal processing failed: %s", e)
        return _error_response(
            warnings=[f"Signal processing failed: {e}"],
        )

    # --- Stage 3: SQI gate ---
    if signal_result.sqi_level == "LOW":
        return {
            "bpm": None,
            "sqi_score": signal_result.sqi_score,
            "sqi_level": signal_result.sqi_level,
            "per_roi_sqi": signal_result.per_roi_sqi,
            "bvp_waveform": signal_result.bvp_signal[:500] if hasattr(signal_result, 'bvp_signal') else [],
            "hrv": None,
            "stress_level": "UNKNOWN",
            "stress_confidence": 0.0,
            "warnings": [
                "Signal quality insufficient for reliable measurement.",
                "Ensure adequate lighting and remain still during recording.",
            ],
            "is_final": True,
        }

    # --- Stage 4: HRV analysis ---
    hrv_result = None
    try:
        from src.hrv_analyzer import compute_hrv
        hrv_result = compute_hrv(signal_result.peak_indices, roi_result.fps)
    except ImportError:
        logger.warning("hrv_analyzer not yet implemented")
        warnings.append("HRV analysis module not yet available.")
    except Exception as e:
        logger.error("HRV analysis failed: %s", e)
        warnings.append(f"HRV analysis failed: {e}")

    if hrv_result is None and "HRV analysis module not yet available." not in warnings:
        warnings.append("Insufficient peaks detected for HRV analysis.")

    # --- Stage 5: Stress classification ---
    stress_level = "UNKNOWN"
    stress_confidence = 0.0

    if hrv_result is not None:
        try:
            from src.stress_classifier import classify_stress
            stress_level, stress_confidence, stress_warnings = classify_stress(hrv_result)
            warnings.extend(stress_warnings)
        except ImportError:
            logger.warning("stress_classifier not yet implemented")
            warnings.append("Stress classification module not yet available.")
        except Exception as e:
            logger.error("Stress classification failed: %s", e)
            warnings.append(f"Stress classification failed: {e}")

    # --- Build HRV dict for response ---
    hrv_dict = None
    if hrv_result is not None:
        hrv_dict = {
            "rmssd": hrv_result.rmssd,
            "sdnn": hrv_result.sdnn,
            "pnn50": hrv_result.pnn50,
            "lf_hf_ratio": hrv_result.lf_hf_ratio,
            "mean_hr": hrv_result.mean_hr,
            "ibi_ms": hrv_result.ibi_ms,
        }

    # --- SQI level warnings ---
    if signal_result.sqi_level == "MEDIUM":
        warnings.append("Signal quality is moderate. Results may have reduced accuracy.")

    return {
        "bpm": round(hrv_result.mean_hr, 1) if hrv_result is not None and getattr(hrv_result, 'mean_hr', None) else getattr(signal_result, 'bpm', None),
        "sqi_score": signal_result.sqi_score,
        "sqi_level": signal_result.sqi_level,
        "per_roi_sqi": signal_result.per_roi_sqi,
        "bvp_waveform": signal_result.bvp_signal[:500] if hasattr(signal_result, 'bvp_signal') else [],
        "hrv": hrv_dict,
        "stress_level": stress_level,
        "stress_confidence": stress_confidence,
        "warnings": warnings,
        "is_final": True,
    }


def run_pipeline(video_path: str, duration_sec: float = None) -> dict:
    """Execute the full analysis pipeline on a video file.

    Each pipeline stage is imported lazily so that the server can start
    even when some modules are not yet implemented. Failures in any
    stage are caught and reported in the warnings list rather than
    crashing the entire request.

    Returns a dictionary matching the API response schema.
    """
    # --- Stage 1: ROI extraction ---
    try:
        from src.roi_extractor import extract_rois
        roi_result = extract_rois(video_path, duration_sec=duration_sec)
    except Exception as e:
        logger.error("ROI extraction failed: %s", e)
        return _error_response(
            warnings=["ROI extraction failed. Ensure the video contains a visible face."],
            error_detail=str(e),
        )

    return _run_analysis_on_roi(roi_result)


def _error_response(warnings: list, error_detail: str = None) -> dict:
    """Build a standardized error response for pipeline failures."""
    return {
        "bpm": None,
        "sqi_score": 0.0,
        "sqi_level": "LOW",
        "per_roi_sqi": [0.0, 0.0, 0.0],
        "bvp_waveform": [],
        "hrv": None,
        "stress_level": "UNKNOWN",
        "stress_confidence": 0.0,
        "warnings": warnings,
        "is_final": True,
    }


def _placeholder_signal_result(roi_result):
    """Create a placeholder SignalResult when signal_processor is unavailable.

    Uses a simple FFT on the raw green channel to estimate BPM. This is
    not production quality but allows the API to return something useful
    while the signal processing module is being developed.
    """
    import numpy as np

    from src.models import SignalResult

    # Use the first ROI (forehead) green channel as a rough BVP proxy
    green = roi_result.green_signals[0]
    if len(green) < 30:
        return SignalResult(
            bvp_signal=green,
            bpm=None,
            peak_indices=[],
            sqi_score=0.1,
            sqi_level="LOW",
            per_roi_sqi=[0.1, 0.1, 0.1],
        )

    arr = np.array(green, dtype=float)
    # Simple detrend
    arr = arr - np.mean(arr)

    # Rough BPM from FFT
    fps = roi_result.fps
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / fps)
    spectrum = np.abs(np.fft.rfft(arr))
    cardiac_mask = (freqs >= 0.7) & (freqs <= 3.5)

    bpm = None
    if np.any(cardiac_mask):
        peak_idx = np.argmax(spectrum[cardiac_mask])
        bpm = float(freqs[cardiac_mask][peak_idx] * 60.0)

    return SignalResult(
        bvp_signal=arr.tolist()[:500],
        bpm=bpm,
        peak_indices=[],
        sqi_score=0.3,
        sqi_level="MEDIUM",
        per_roi_sqi=[0.3, 0.3, 0.3],
    )


# ---------------------------------------------------------------------------
# POST /api/analyze -- main video upload endpoint
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
async def analyze_video(video: UploadFile = File(...), duration_sec: float = Form(None)):
    """Accept a video file upload and run the full analysis pipeline.

    Args:
        video: Uploaded video file (MP4, WebM, AVI, MOV, MKV).

    Returns:
        JSON response with BPM, SQI, HRV, stress level, and waveform data.
    """
    # Validate file extension
    if video.filename is None:
        raise HTTPException(status_code=422, detail="No filename provided.")

    ext = Path(video.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: '{ext}'. Accepted formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and validate file size
    content = await video.read()
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB.",
        )

    # Save to temp file and run pipeline
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start_time = time.time()
        result = run_pipeline(tmp_path, duration_sec)
        elapsed_ms = (time.time() - start_time) * 1000
        result["processing_time_ms"] = round(elapsed_ms, 1)

        logger.info(
            "Analysis complete: bpm=%s, sqi=%s, time=%.0fms",
            result.get("bpm"), result.get("sqi_level"), elapsed_ms,
        )

        return JSONResponse(content=result)
    except Exception as e:
        logger.exception("Unexpected error during analysis")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# WebSocket /api/live -- live webcam frame streaming
# ---------------------------------------------------------------------------

@app.websocket("/api/live")
async def live_video_endpoint(websocket: WebSocket):
    """Process webcam frames in real-time via WebSocket.

    Protocol:
        Client sends: {"frame": "<base64 jpeg>"} for each frame
        Client sends: {"action": "stop"} to finalize
        Server sends: intermediate JSON results every ~15 frames (after 2s buffer)
        Server sends: final JSON result with is_final=True after stop
    """
    await websocket.accept()
    from src.roi_extractor import (
        ROI_DEFINITIONS,
        _create_landmarker,
        _process_frame,
    )

    try:
        landmarker = _create_landmarker(running_mode="IMAGE")
    except Exception as e:
        logger.error("Could not load landmarker for WS: %s", e)
        await websocket.close(code=1011)
        return

    fps_estimate = 10.0  # fallback baseline
    duration_sec = None
    frame_count = 0
    start_time = time.time()

    green_buffers = [[] for _ in ROI_DEFINITIONS]
    rgb_buffers = [[] for _ in ROI_DEFINITIONS]
    landmarks_list = []

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "stop":
                duration_sec = data.get("duration_sec", None)
                break

            frame_b64 = data.get("frame")
            if not frame_b64:
                continue

            # Strip data-URL prefix if present
            if "," in frame_b64:
                frame_b64 = frame_b64.split(",", 1)[1]

            img_bytes = base64.b64decode(frame_b64)
            img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            frame_h, frame_w = frame.shape[:2]

            # IMAGE mode — no timestamp needed
            green_vals, rgb_vals, lm_coords = _process_frame(
                landmarker, frame, frame_w, frame_h, timestamp_ms=None
            )

            frame_count += 1
            if green_vals is not None:
                landmarks_list.append(lm_coords)
                for i in range(len(ROI_DEFINITIONS)):
                    green_buffers[i].append(green_vals[i])
                    rgb_buffers[i].append(rgb_vals[i])
            else:
                landmarks_list.append(None)
                for i in range(len(ROI_DEFINITIONS)):
                    green_buffers[i].append(None)
                    rgb_buffers[i].append(None)

            # Send intermediate results every 15 frames once we have >= 20 frames (~2s at 10fps)
            if frame_count % 15 == 0 and frame_count >= 20:
                try:
                    roi_res = _build_live_roi(green_buffers, rgb_buffers, fps_estimate, frame_count)
                    intermediate = _run_analysis_on_roi(roi_res)
                    intermediate["is_final"] = False
                    await websocket.send_json(intermediate)
                except Exception:
                    pass  # don't crash the stream on intermediate errors

        # --- Stop received: run final analysis ---
        if frame_count > 10:
            if duration_sec is not None and float(duration_sec) > 0:
                true_fps = frame_count / float(duration_sec)
            else:
                elapsed = time.time() - start_time
                true_fps = frame_count / elapsed if elapsed > 0 else 10.0

            roi_res = _build_live_roi(green_buffers, rgb_buffers, true_fps, frame_count)
            final = _run_analysis_on_roi(roi_res)
            final["is_final"] = True
            await websocket.send_json(final)

    except WebSocketDisconnect:
        logger.info("Client disconnected from live session")
    except Exception as e:
        logger.error("Live processing error: %s", e)
    finally:
        landmarker.close()


def _build_live_roi(green_buffers, rgb_buffers, fps, frame_count):
    """Build a clean ROIResult from live frame buffers."""
    from src.models import ROIResult
    from src.roi_extractor import _interpolate_gaps, _interpolate_rgb_gaps

    temp_green = [_interpolate_gaps(buf, max_gap=5) for buf in green_buffers]
    temp_rgb = [_interpolate_rgb_gaps(buf, max_gap=5) for buf in rgb_buffers]

    # Scrub remaining Nones that would crash scipy.detrend
    temp_green = [[x if x is not None else 0.0 for x in buf] for buf in temp_green]
    temp_rgb = [
        [[c if c is not None else 0.0 for c in p] if p is not None else [0.0, 0.0, 0.0] for p in buf]
        for buf in temp_rgb
    ]

    return ROIResult(
        green_signals=temp_green,
        rgb_signals=temp_rgb,
        face_detected=True,
        fps=fps,
        frame_count=frame_count,
    )


# ---------------------------------------------------------------------------
# Serve frontend static files (must be the LAST mount)
# ---------------------------------------------------------------------------

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
