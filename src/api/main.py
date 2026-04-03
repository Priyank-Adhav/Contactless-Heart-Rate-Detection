"""
FastAPI application entry point.

Serves the frontend dashboard and exposes REST endpoints for
video upload analysis and (optionally) live webcam frame processing.

See docs/modules/06_api_server.md for implementation details.
"""

from fastapi import FastAPI

app = FastAPI(
    title="PulseGuard API",
    description="Contact-free cardiac stress monitoring via facial video analysis",
    version="0.1.0",
)


# --- Health check ---

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# TODO: POST /api/analyze - accepts video file, returns AnalysisResult
# TODO: POST /api/analyze/webcam - accepts base64 frames, returns live results
# TODO: Mount frontend static files at root

# Serve frontend files
# app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
