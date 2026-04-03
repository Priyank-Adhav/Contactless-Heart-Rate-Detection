# Module 6: API Server

Owner: P3 (Backend Lead)

## Purpose

Expose the analysis pipeline as a REST API and serve the frontend dashboard.
Accepts video file uploads (and optionally webcam frame streams), orchestrates
the full pipeline, and returns structured JSON results.

## Inputs and Outputs

**Input:** HTTP requests with video file attachments or base64-encoded frames.

**Output:** JSON responses conforming to the AnalysisResult schema.

## Dependencies

- `fastapi` for the web framework
- `uvicorn` for the ASGI server
- `python-multipart` for file upload handling
- All src modules for pipeline orchestration

## Endpoint Specification

### GET /api/health

Health check endpoint. Returns `{"status": "ok"}`.

Already implemented in the skeleton.

### POST /api/analyze

Main analysis endpoint for video file upload.

**Request:**
- Content-Type: `multipart/form-data`
- Field: `video` (file, required) -- MP4, WebM, or AVI file

**Response (200):**
```json
{
    "bpm": 74.2,
    "sqi_score": 0.82,
    "sqi_level": "HIGH",
    "per_roi_sqi": [0.85, 0.79, 0.81],
    "bvp_waveform": [0.12, 0.15, ...],
    "hrv": {
        "rmssd": 42.1,
        "sdnn": 51.3,
        "pnn50": 18.5,
        "lf_hf_ratio": 1.4,
        "mean_hr": 74.2,
        "ibi_ms": [810, 825, ...]
    },
    "stress_level": "LOW",
    "stress_confidence": 0.72,
    "processing_time_ms": 2340,
    "warnings": []
}
```

**Response when SQI is LOW (200, but with warnings):**
```json
{
    "bpm": null,
    "sqi_score": 0.22,
    "sqi_level": "LOW",
    "per_roi_sqi": [0.15, 0.28, 0.23],
    "bvp_waveform": [...],
    "hrv": null,
    "stress_level": "UNKNOWN",
    "stress_confidence": 0.0,
    "processing_time_ms": 1850,
    "warnings": [
        "Signal quality insufficient for reliable measurement.",
        "Ensure adequate lighting and remain still during recording."
    ]
}
```

**Error responses:**
- 422: Invalid file type or missing file

### POST /api/analyze/webcam (Optional)

For real-time webcam analysis. Accepts a JSON body with base64-encoded frames
captured by the frontend. This is an optional stretch goal.

**Request:**
```json
{
    "frames": ["base64_encoded_frame_1", "base64_encoded_frame_2", ...],
    "fps": 30,
    "duration_seconds": 30
}
```

## Implementation Guide

### Step 1: File Upload Handling

```python
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

app = FastAPI(title="PulseGuard API", version="0.1.0")

ALLOWED_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv"}

@app.post("/api/analyze")
async def analyze_video(video: UploadFile = File(...)):
    # Validate file type
    ext = Path(video.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {ext}. Accepted: {ALLOWED_EXTENSIONS}"
        )

    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await video.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start_time = time.time()
        result = run_pipeline(tmp_path)
        elapsed_ms = (time.time() - start_time) * 1000
        result["processing_time_ms"] = round(elapsed_ms, 1)
        return JSONResponse(content=result)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
```

### Step 2: Pipeline Orchestration

```python
def run_pipeline(video_path):
    """Execute the full analysis pipeline.

    Returns a dictionary matching the API response schema.
    """
    # Stage 1: ROI extraction
    from src.roi_extractor import extract_rois
    roi_result = extract_rois(video_path)

    if not roi_result.face_detected:
        return {
            "bpm": None,
            "sqi_score": 0.0,
            "sqi_level": "LOW",
            "per_roi_sqi": [0.0, 0.0, 0.0],
            "bvp_waveform": [],
            "hrv": None,
            "stress_level": "UNKNOWN",
            "stress_confidence": 0.0,
            "warnings": ["No face detected in the video."],
        }

    # Stage 2: Signal processing + ensemble fusion
    from src.signal_processor import process_signals
    signal_result = process_signals(roi_result)

    # Stage 3: Check SQI -- gate downstream processing
    if signal_result.sqi_level == "LOW":
        return {
            "bpm": None,
            "sqi_score": signal_result.sqi_score,
            "sqi_level": signal_result.sqi_level,
            "per_roi_sqi": signal_result.per_roi_sqi,
            "bvp_waveform": signal_result.bvp_signal,
            "hrv": None,
            "stress_level": "UNKNOWN",
            "stress_confidence": 0.0,
            "warnings": [
                "Signal quality insufficient for reliable measurement.",
                "Ensure adequate lighting and remain still during recording.",
            ],
        }

    # Stage 4: HRV analysis
    from src.hrv_analyzer import compute_hrv
    hrv_result = compute_hrv(signal_result.peak_indices, roi_result.fps)

    # Stage 5: Stress classification
    hrv_dict = None
    stress_level = "UNKNOWN"
    stress_confidence = 0.0

    if hrv_result is not None:
        from src.stress_classifier import classify_stress
        stress_level, stress_confidence = classify_stress(hrv_result)
        hrv_dict = {
            "rmssd": hrv_result.rmssd,
            "sdnn": hrv_result.sdnn,
            "pnn50": hrv_result.pnn50,
            "lf_hf_ratio": hrv_result.lf_hf_ratio,
            "mean_hr": hrv_result.mean_hr,
            "ibi_ms": hrv_result.ibi_ms,
        }

    warnings = []
    if signal_result.sqi_level == "MEDIUM":
        warnings.append("Signal quality is moderate. Results may have reduced accuracy.")
    if hrv_result is None:
        warnings.append("Insufficient peaks detected for HRV analysis.")

    return {
        "bpm": signal_result.bpm,
        "sqi_score": signal_result.sqi_score,
        "sqi_level": signal_result.sqi_level,
        "per_roi_sqi": signal_result.per_roi_sqi,
        "bvp_waveform": signal_result.bvp_signal,
        "hrv": hrv_dict,
        "stress_level": stress_level,
        "stress_confidence": stress_confidence,
        "warnings": warnings,
    }
```

### Step 3: Serve Frontend

```python
# Mount the frontend directory to serve static files at root
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

This must be the last mount call, after all API routes are registered.

### Step 4: CORS (only if needed during development)

If the frontend and backend are served from different origins during
development, add CORS middleware:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Remove or restrict this before the demo.

## Running the Server

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Testing

```bash
pytest tests/api/test_endpoints.py -v
```

Key validations:
- Health endpoint returns 200
- Valid video upload returns 200 with correct JSON schema
- Invalid file type returns 422
- Missing file returns 422
