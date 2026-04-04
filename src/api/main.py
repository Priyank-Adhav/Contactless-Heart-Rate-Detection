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
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
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
# Live session constants
# ---------------------------------------------------------------------------

# Minimum seconds of buffered signal before we trust a POS/CHROM result.
# Short windows produce noisy FFT peaks that can land on the 2nd harmonic.
LIVE_MIN_SECONDS_FIRST_RESULT = 5.0

# How often (in seconds of signal) to emit intermediate results after the
# first one has been sent.
LIVE_INTERMEDIATE_INTERVAL_SECONDS = 2.5

# Minimum seconds needed to attempt a final analysis on WebSocket stop.
LIVE_MIN_SECONDS_FINAL = 3.0

# FPS bounds accepted from the client init message.
LIVE_FPS_MIN = 5.0
LIVE_FPS_MAX = 60.0

# Default FPS assumption if client never sends an init message.
# Matches the original frontend interval of 100 ms.
LIVE_FPS_DEFAULT = 10.0


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

def _run_analysis_on_roi(roi_result, video_path: str = None) -> dict:
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

    # --- Stage 3: SQI gate + Triage Decision Agent ---
    # TWIST 1: When SQI is LOW, switch to Visual Assessment Mode
    # Uses Gemini Vision API (if key available) or OpenCV heuristics
    if signal_result.sqi_level == "LOW":
        logger.info("SQI is LOW — Triage Decision Agent switching to Visual Assessment Mode")
        try:
            from src.visual_assessor import assess_visual_distress
            visual = assess_visual_distress(video_path)
        except Exception as e:
            logger.error("Visual assessment failed: %s", e)
            visual = {
                "visual_stress_score": 5.0,
                "visual_stress_level": "UNKNOWN",
                "confidence": 0.1,
                "analysis_method": "error",
                "indicators": {
                    "pallor": {"score": 5, "description": "Assessment unavailable"},
                    "sweating": {"score": 5, "description": "Assessment unavailable"},
                    "cyanosis": {"score": 5, "description": "Assessment unavailable"},
                    "breathing": {"score": 5, "description": "Assessment unavailable"},
                    "facial_distress": {"score": 5, "description": "Assessment unavailable"},
                },
                "overall_assessment": f"Visual assessment error: {e}",
                "recommended_action": "Retry with better conditions",
                "details": [f"Visual assessment error: {e}"],
            }

        # Map visual_stress_level to stress_level format
        vs_level = visual.get("visual_stress_level", "UNKNOWN")

        return {
            "bpm": None,
            "sqi_score": signal_result.sqi_score,
            "sqi_level": signal_result.sqi_level,
            "per_roi_sqi": signal_result.per_roi_sqi,
            "bvp_waveform": signal_result.bvp_signal[:500],
            "hrv": None,
            "stress_level": vs_level,
            "stress_confidence": visual.get("confidence", 0.5),
            "active_mode": "visual_assessment",
            "mode_reason": "rPPG signal quality below confidence threshold — switched to Gemini-powered visual triage",
            "analysis_method": visual.get("analysis_method", "unknown"),
            "visual_assessment": visual,
            "warnings": [
                "Biometric mode unavailable — signal quality too low.",
                f"Visual Assessment Mode activated ({visual.get('analysis_method', 'unknown')}).",
            ] + visual.get("details", []),
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
            from src.stress_classifier import classify_stress_ml as classify_stress  ##
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
        "active_mode": "biometric",
        "mode_reason": "rPPG signal quality sufficient for biometric analysis",
        "visual_assessment": None,
        "warnings": warnings,
        "is_final": True,
    }


def run_pipeline(video_path: str) -> dict:
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
        roi_result = extract_rois(video_path)
    except Exception as e:
        logger.error("ROI extraction failed: %s", e)
        return _error_response(
            warnings=["ROI extraction failed. Ensure the video contains a visible face."],
            error_detail=str(e),
        )

    return _run_analysis_on_roi(roi_result, video_path)


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

    # Rough BPM from FFT — uses roi_result.fps so frequency bins are correct
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
async def analyze_video(video: UploadFile = File(...), force_visual: bool = False):
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

        # Manual visual assessment mode — skip biometric pipeline
        if force_visual:
            logger.info("Force visual assessment requested — skipping biometric pipeline")
            from src.visual_assessor import assess_visual_distress
            visual = assess_visual_distress(tmp_path)
            vs_level = visual.get("visual_stress_level", "UNKNOWN")
            elapsed_ms = (time.time() - start_time) * 1000

            result = {
                "bpm": None,
                "sqi_score": 0,
                "sqi_level": "N/A",
                "per_roi_sqi": [],
                "bvp_waveform": [],
                "hrv": None,
                "stress_level": vs_level,
                "stress_confidence": visual.get("confidence", 0.5),
                "active_mode": "visual_assessment",
                "mode_reason": "Manual visual assessment mode — Gemini AI analyzing physical distress indicators",
                "analysis_method": visual.get("analysis_method", "unknown"),
                "visual_assessment": visual,
                "processing_time_ms": round(elapsed_ms, 1),
                "warnings": [
                    f"Visual Assessment Mode ({visual.get('analysis_method', 'unknown')})",
                ] + visual.get("details", []),
            }
            return JSONResponse(content=result)

        result = run_pipeline(tmp_path)
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
# POST /api/analyze/finger -- finger PPG endpoint
# ---------------------------------------------------------------------------

def run_finger_pipeline(video_path: str) -> dict:
    """Process a finger-on-flashlight video for PPG analysis.

    Instead of face ROI extraction, this reads the mean red channel
    intensity per frame. The flashlight illuminates the finger, and
    blood flow modulates the red light — giving a strong PPG signal.
    """
    import cv2
    import numpy as np

    warnings = []

    # --- Stage 1: Extract red channel from video ---
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _error_response(warnings=["Could not open video file."])

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    red_signal = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Mean of red channel (BGR format, index 2 = Red)
        red_signal.append(float(np.mean(frame[:, :, 2])))

    cap.release()

    if len(red_signal) < int(fps * 3):
        return _error_response(
            warnings=["Video too short for finger PPG analysis. Need at least 3 seconds."]
        )

    red = np.array(red_signal, dtype=np.float64)
    logger.info("Finger PPG: %d frames at %.1f fps", len(red), fps)

    # --- Stage 2: Signal processing ---
    try:
        from scipy.signal import detrend

        from src.signal_processor import bandpass_filter, detect_peaks, extract_bpm

        # Detrend and bandpass filter
        # Finger PPG has much stronger signal → use tighter band (48-150 BPM)
        red_detrended = detrend(red, type='linear')
        red_filtered = bandpass_filter(red_detrended, fps, low=0.8, high=2.5)

        # BPM via FFT
        bpm = extract_bpm(red_filtered, fps)

        # Peak detection
        peaks = detect_peaks(red_filtered, fps)

        # SQI estimate: finger PPG is typically high quality
        from src.sqi_engine import compute_sqi
        sqi_score, sqi_level, _ = compute_sqi(red_filtered, fps)

    except Exception as e:
        logger.error("Finger signal processing failed: %s", e)
        return _error_response(warnings=[f"Signal processing failed: {e}"])

    # --- Stage 3: HRV analysis ---
    hrv_result = None
    try:
        from src.hrv_analyzer import compute_hrv
        hrv_result = compute_hrv(peaks, fps)
    except Exception as e:
        logger.error("Finger HRV analysis failed: %s", e)
        warnings.append(f"HRV analysis failed: {e}")

    if hrv_result is None and not any("HRV" in w for w in warnings):
        warnings.append("Insufficient peaks detected for HRV analysis.")

    # --- Stage 4: Stress classification ---
    stress_level = "UNKNOWN"
    stress_confidence = 0.0
    if hrv_result is not None:
        try:
            from src.stress_classifier import classify_stress
            stress_level, stress_confidence, stress_warnings = classify_stress(hrv_result)
            warnings.extend(stress_warnings)
        except Exception as e:
            logger.error("Stress classification failed: %s", e)
            warnings.append(f"Stress classification failed: {e}")

    # --- Build response ---
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

    return {
        "bpm": round(hrv_result.mean_hr, 1) if hrv_result else bpm,
        "sqi_score": sqi_score,
        "sqi_level": sqi_level,
        "per_roi_sqi": [sqi_score],
        "bvp_waveform": red_filtered[:500].tolist(),
        "hrv": hrv_dict,
        "stress_level": stress_level,
        "stress_confidence": stress_confidence,
        "active_mode": "biometric",
        "mode_reason": "Finger PPG — direct contact provides strong signal",
        "visual_assessment": None,
        "warnings": warnings,
    }


@app.post("/api/analyze/finger")
async def analyze_finger(video: UploadFile = File(...)):
    """Analyze pulse from finger-on-flashlight video.

    The user places their finger on the camera+flashlight. The red channel
    intensity oscillates with each heartbeat, giving a strong PPG signal.
    """
    if video.filename is None:
        raise HTTPException(status_code=422, detail="No filename provided.")

    ext = Path(video.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422,
            detail=f"Unsupported: '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    content = await video.read()
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=422,
            detail=f"File too large ({len(content)/1024/1024:.1f}MB). Max: {MAX_FILE_SIZE_BYTES/1024/1024:.0f}MB.")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start_time = time.time()
        result = run_finger_pipeline(tmp_path)
        elapsed_ms = (time.time() - start_time) * 1000
        result["processing_time_ms"] = round(elapsed_ms, 1)
        logger.info("Finger analysis: bpm=%s, time=%.0fms",
                     result.get("bpm"), elapsed_ms)
        return JSONResponse(content=result)
    except Exception as e:
        logger.exception("Finger analysis failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
# WebSocket /api/live -- live webcam frame streaming
# ---------------------------------------------------------------------------

@app.websocket("/api/live")
async def live_video_endpoint(websocket: WebSocket):
    """Process webcam frames in real-time via WebSocket.

    Protocol:
        Client sends: {"action": "init", "fps": <number>} as the first message
                      to negotiate the actual capture frame rate. The backend
                      uses this value for all FFT frequency bin calculations,
                      intermediate result thresholds, and ROIResult construction.
                      Without the correct FPS the frequency axis is wrong and BPM
                      reads high (typically landing on a harmonic of the true rate).

        Client sends: {"frame": "<base64 jpeg>"} for each frame
        Client sends: {"action": "stop"} to finalize

        Server sends: intermediate JSON results once MIN_SECONDS_FIRST_RESULT of
                      signal has been buffered, then every INTERMEDIATE_INTERVAL_SECONDS
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

    # fps_estimate is set by the client's init message.
    # Keeping this accurate is critical: POS and CHROM both construct their
    # FFT frequency axes using roi_result.fps. A wrong value shifts every
    # frequency bin, causing the peak-finder to latch onto the wrong
    # harmonic and report BPM that is a multiple of the true rate.
    fps_estimate: float = LIVE_FPS_DEFAULT

    frame_count = 0

    green_buffers = [[] for _ in ROI_DEFINITIONS]
    rgb_buffers = [[] for _ in ROI_DEFINITIONS]
    face_absent_frames = 0
    landmarks_list = []

    # Track how many frames were present at last intermediate emission so we
    # can use a frame-delta trigger instead of modulo (avoids phase sensitivity).
    last_intermediate_at = 0

    try:
        while True:
            data = await websocket.receive_json()

            # ----------------------------------------------------------------
            # Init handshake — client declares actual capture FPS
            # ----------------------------------------------------------------
            if data.get("action") == "init":
                client_fps = data.get("fps")
                if client_fps is not None:
                    try:
                        client_fps = float(client_fps)
                        if LIVE_FPS_MIN <= client_fps <= LIVE_FPS_MAX:
                            fps_estimate = client_fps
                            logger.info(
                                "Live session FPS negotiated: %.1f", fps_estimate
                            )
                        else:
                            logger.warning(
                                "Client FPS %.1f out of accepted range [%.1f, %.1f]; "
                                "using default %.1f",
                                client_fps, LIVE_FPS_MIN, LIVE_FPS_MAX, fps_estimate,
                            )
                    except (TypeError, ValueError):
                        logger.warning("Invalid FPS value from client: %r", client_fps)
                continue

            # ----------------------------------------------------------------
            # Stop signal — run final analysis and close
            # ----------------------------------------------------------------
            if data.get("action") == "stop":
                break

            # ----------------------------------------------------------------
            # Frame data
            # ----------------------------------------------------------------
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
                face_absent_frames += 1
                landmarks_list.append(None)
                for i in range(len(ROI_DEFINITIONS)):
                    green_buffers[i].append(None)
                    rgb_buffers[i].append(None)

            # ----------------------------------------------------------------
            # Intermediate result emission
            # Thresholds are derived from fps_estimate so they scale correctly
            # regardless of whether the client sends at 10 FPS or 25 FPS.
            # ----------------------------------------------------------------
            frames_for_first = int(fps_estimate * LIVE_MIN_SECONDS_FIRST_RESULT)
            frames_per_interval = max(1, int(fps_estimate * LIVE_INTERMEDIATE_INTERVAL_SECONDS))

            if (
                frame_count >= frames_for_first
                and (frame_count - last_intermediate_at) >= frames_per_interval
            ):
                try:
                    interim_absence = face_absent_frames / max(frame_count, 1)
                    if interim_absence > 0.5:
                        intermediate = _error_response(
                            warnings=["Face not detected. Please center your face in the frame."]
                        )
                    else:
                        roi_res = _build_live_roi(
                            green_buffers, rgb_buffers, fps_estimate, frame_count
                        )
                        intermediate = _run_analysis_on_roi(roi_res, None)
                    intermediate["is_final"] = False
                    await websocket.send_json(intermediate)
                    last_intermediate_at = frame_count
                    logger.debug(
                        "Intermediate result sent at frame %d (fps=%.1f, absence=%.0f%%, bpm=%s)",
                        frame_count, fps_estimate, interim_absence * 100, intermediate.get("bpm"),
                    )
                except Exception as exc:
                    logger.warning("Intermediate analysis failed: %s", exc)

        # --------------------------------------------------------------------
        # Stop received: run final analysis over all buffered frames
        # --------------------------------------------------------------------
        frames_for_final = int(fps_estimate * LIVE_MIN_SECONDS_FINAL)
        if frame_count >= frames_for_final:
            absence_ratio = face_absent_frames / max(frame_count, 1)
            if absence_ratio > 0.4:
                final = _error_response(
                    warnings=[
                        f"Face absent for {absence_ratio*100:.0f}% of the recording. "
                        "Ensure your face is visible and well-lit throughout."
                    ]
                )
                final["is_final"] = True
            else:
                roi_res = _build_live_roi(
                    green_buffers, rgb_buffers, fps_estimate, frame_count
                )
                final = _run_analysis_on_roi(roi_res, None)
                final["is_final"] = True
            await websocket.send_json(final)
            logger.info(
                "Final result sent: frames=%d, fps=%.1f, absence=%.0f%%, bpm=%s, sqi=%s",
                frame_count, fps_estimate, absence_ratio*100, final.get("bpm"), final.get("sqi_level"),
            )
        else:
            logger.warning(
                "Not enough frames for final analysis: got %d, need %d (fps=%.1f)",
                frame_count, frames_for_final, fps_estimate,
            )
            await websocket.send_json(
                _error_response(
                    warnings=[
                        f"Insufficient data: only {frame_count / fps_estimate:.1f}s of signal captured "
                        f"(minimum {LIVE_MIN_SECONDS_FINAL:.0f}s required)."
                    ]
                )
            )

    except WebSocketDisconnect:
        logger.info("Client disconnected from live session (frames=%d)", frame_count)
    except Exception as e:
        logger.error("Live processing error: %s", e, exc_info=True)
    finally:
        landmarker.close()


def _build_live_roi(green_buffers, rgb_buffers, fps, frame_count):
    """Build a clean ROIResult from live frame buffers.

    The fps argument is passed through to ROIResult.fps so that downstream
    signal processing modules (POS, CHROM) construct correct FFT frequency
    axes. This is why accurate FPS negotiation matters end-to-end.
    """
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

