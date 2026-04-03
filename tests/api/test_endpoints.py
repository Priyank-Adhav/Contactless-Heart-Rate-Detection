"""
API endpoint tests.

Validates request/response contracts for the FastAPI server.
Uses httpx.AsyncClient against the app instance (no live server needed).
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:

    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        response = client.get("/api/health")
        data = response.json()
        assert data["status"] == "ok"


class TestAnalyzeEndpoint:

    @pytest.mark.skip(reason="Awaiting /api/analyze implementation")
    def test_upload_valid_video_returns_200(self, client, tmp_path):
        """A valid video file upload should return 200 with results."""
        pass

    @pytest.mark.skip(reason="Awaiting /api/analyze implementation")
    def test_response_contains_required_fields(self, client):
        """Response JSON should contain bpm, sqi_score, sqi_level,
        hrv, stress_level, stress_confidence, and bvp_waveform."""
        pass

    @pytest.mark.skip(reason="Awaiting /api/analyze implementation")
    def test_invalid_file_type_returns_422(self, client):
        """Uploading a non-video file should return 422."""
        pass

    @pytest.mark.skip(reason="Awaiting /api/analyze implementation")
    def test_empty_upload_returns_422(self, client):
        """Missing file in request should return 422."""
        pass

    @pytest.mark.skip(reason="Awaiting /api/analyze implementation")
    def test_low_sqi_response_contains_warnings(self, client):
        """When signal quality is LOW, the response should include
        a warning message and bpm may be null."""
        pass
