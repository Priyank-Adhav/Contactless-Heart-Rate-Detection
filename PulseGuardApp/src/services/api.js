// PulseGuard API client
// The Python backend must be running: uvicorn src.api.main:app --host 0.0.0.0 --port 8000

const BASE_URL = 'http://10.23.46.166:8000';

/**
 * Health check — is the backend reachable?
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE_URL}/api/health`, { timeout: 5000 });
    const data = await res.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
}

/**
 * Upload face-scan video → backend runs ROI → Signal → HRV → Stress pipeline
 * Endpoint: POST /api/analyze
 * @param {string} videoUri - URI to the video file
 * @param {boolean} forceVisual - If true, skip biometric and use Gemini visual assessment
 */
export async function analyzeVideo(videoUri, forceVisual = false) {
  const form = new FormData();
  form.append('video', {
    uri: videoUri,
    type: 'video/mp4',
    name: 'face_capture.mp4',
  });

  const url = forceVisual
    ? `${BASE_URL}/api/analyze?force_visual=true`
    : `${BASE_URL}/api/analyze`;

  const res = await fetch(url, {
    method: 'POST',
    body: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Server error ${res.status}`);
  }
  return res.json();
}

/**
 * Upload finger-PPG video → backend extracts red channel → BPM → HRV → Stress
 * Endpoint: POST /api/analyze/finger
 */
export async function analyzeFingerVideo(videoUri) {
  const form = new FormData();
  form.append('video', {
    uri: videoUri,
    type: 'video/mp4',
    name: 'finger_capture.mp4',
  });

  const res = await fetch(`${BASE_URL}/api/analyze/finger`, {
    method: 'POST',
    body: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Server error ${res.status}`);
  }
  return res.json();
}
