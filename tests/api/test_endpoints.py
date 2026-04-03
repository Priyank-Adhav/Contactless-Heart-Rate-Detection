"""
API endpoint tests.

Validates request/response contracts for the FastAPI server.
Uses TestClient to test against the app instance (no live server needed).

Tests are organized by endpoint and cover:
- Health check (basic availability)
- Video upload validation (file type, size, empty file)
- Response schema (required fields present)
- Pipeline error handling (mock failures)
"""

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import _error_response, app, run_pipeline


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        response = client.get("/api/health")
        data = response.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# File validation on /api/analyze
# ---------------------------------------------------------------------------

class TestAnalyzeValidation:

    def test_invalid_file_type_returns_422(self, client):
        """Uploading a non-video file should return 422."""
        fake_file = io.BytesIO(b"not a video")
        response = client.post(
            "/api/analyze",
            files={"video": ("test.txt", fake_file, "text/plain")},
        )
        assert response.status_code == 422
        assert "Unsupported file type" in response.json()["detail"]

    def test_empty_file_returns_422(self, client):
        """An empty file upload should return 422."""
        empty_file = io.BytesIO(b"")
        response = client.post(
            "/api/analyze",
            files={"video": ("test.mp4", empty_file, "video/mp4")},
        )
        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()

    def test_missing_file_returns_422(self, client):
        """Request without file should return 422."""
        response = client.post("/api/analyze")
        assert response.status_code == 422

    def test_accepts_mp4(self, client):
        """MP4 extension should pass validation (pipeline may fail
        on dummy content, but the extension check should pass)."""
        # Create a minimal file that passes extension check
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_success_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.mp4", fake_video, "video/mp4")},
            )
        assert response.status_code == 200

    def test_accepts_webm(self, client):
        """WebM extension should pass validation."""
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_success_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.webm", fake_video, "video/webm")},
            )
        assert response.status_code == 200

    def test_accepts_avi(self, client):
        """AVI extension should pass validation."""
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_success_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.avi", fake_video, "video/avi")},
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Response schema validation
# ---------------------------------------------------------------------------

class TestAnalyzeResponse:

    def test_success_response_contains_required_fields(self, client):
        """A successful response should contain all required fields."""
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_success_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.mp4", fake_video, "video/mp4")},
            )

        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "bpm", "sqi_score", "sqi_level", "per_roi_sqi",
            "bvp_waveform", "hrv", "stress_level", "stress_confidence",
            "processing_time_ms", "warnings",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_processing_time_is_added(self, client):
        """Response should include processing_time_ms > 0."""
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_success_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.mp4", fake_video, "video/mp4")},
            )

        data = response.json()
        assert "processing_time_ms" in data
        assert data["processing_time_ms"] >= 0

    def test_low_sqi_response_has_null_bpm(self, client):
        """When SQI is LOW, bpm should be null and warnings present."""
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_low_sqi_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.mp4", fake_video, "video/mp4")},
            )

        data = response.json()
        assert data["bpm"] is None
        assert data["sqi_level"] == "LOW"
        assert data["hrv"] is None
        assert len(data["warnings"]) > 0

    def test_success_response_has_hrv_fields(self, client):
        """When analysis succeeds, HRV dict should have required keys."""
        fake_video = io.BytesIO(b"\x00" * 1024)
        with patch("src.api.main.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = _mock_success_response()
            response = client.post(
                "/api/analyze",
                files={"video": ("test.mp4", fake_video, "video/mp4")},
            )

        data = response.json()
        assert data["hrv"] is not None
        hrv = data["hrv"]
        for key in ["rmssd", "sdnn", "pnn50", "lf_hf_ratio", "mean_hr", "ibi_ms"]:
            assert key in hrv, f"Missing HRV field: {key}"


# ---------------------------------------------------------------------------
# Pipeline orchestration unit tests
# ---------------------------------------------------------------------------

class TestRunPipeline:

    def test_error_response_has_correct_shape(self):
        """_error_response should produce a valid response dict."""
        result = _error_response(warnings=["Something went wrong"])
        assert result["bpm"] is None
        assert result["sqi_level"] == "LOW"
        assert "Something went wrong" in result["warnings"]

    def test_pipeline_no_face_returns_warning(self):
        """When ROI extraction finds no face, response should indicate that."""
        from src.models import ROIResult

        mock_roi = ROIResult(
            green_signals=[[], [], []],
            face_detected=False,
            fps=30.0,
            frame_count=100,
        )

        with patch("src.roi_extractor.extract_rois", return_value=mock_roi):
            result = run_pipeline("/fake/path.mp4")

        assert result["bpm"] is None
        assert "No face detected" in result["warnings"][0]


# ---------------------------------------------------------------------------
# Helper: mock response builders
# ---------------------------------------------------------------------------

def _mock_success_response():
    """Build a mock successful pipeline response."""
    return {
        "bpm": 72.5,
        "sqi_score": 0.85,
        "sqi_level": "HIGH",
        "per_roi_sqi": [0.88, 0.82, 0.84],
        "bvp_waveform": [0.1, 0.2, 0.3, 0.2, 0.1],
        "hrv": {
            "rmssd": 42.1,
            "sdnn": 51.3,
            "pnn50": 18.5,
            "lf_hf_ratio": 1.4,
            "mean_hr": 72.5,
            "ibi_ms": [830, 820, 840],
        },
        "stress_level": "LOW",
        "stress_confidence": 0.72,
        "warnings": [],
    }


def _mock_low_sqi_response():
    """Build a mock response for low signal quality."""
    return {
        "bpm": None,
        "sqi_score": 0.22,
        "sqi_level": "LOW",
        "per_roi_sqi": [0.15, 0.28, 0.23],
        "bvp_waveform": [],
        "hrv": None,
        "stress_level": "UNKNOWN",
        "stress_confidence": 0.0,
        "warnings": [
            "Signal quality insufficient for reliable measurement.",
            "Ensure adequate lighting and remain still during recording.",
        ],
    }
