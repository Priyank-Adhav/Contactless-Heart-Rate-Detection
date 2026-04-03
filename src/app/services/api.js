// API Client — Communication with Python FastAPI backend
// See docs/app/03_api_client.md for full documentation
//
// ════════════════════════════════════════════════════════
//  IMPORTANT: Change BASE_URL to your server's local IP
//  Find it with: hostname -I (Linux), ipconfig (Windows)
//  Server must be started with: --host 0.0.0.0
// ════════════════════════════════════════════════════════

const BASE_URL = 'http://192.168.1.100:8000'; // ← CHANGE THIS

/**
 * Health check — verify the backend is reachable.
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE_URL}/api/health`);
    const data = await res.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
}

/**
 * Upload a recorded video for cardiac analysis.
 * @param {string} videoUri  Local file URI from expo-camera
 * @returns {Promise<object>} Analysis result JSON
 */
export async function analyzeVideo(videoUri) {
  const form = new FormData();
  form.append('video', {
    uri: videoUri,
    type: 'video/mp4',
    name: 'capture.mp4',
  });

  const res = await fetch(`${BASE_URL}/api/analyze`, {
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
 * Get AI health insights from analysis results.
 * @param {object} result  The analysis result from analyzeVideo()
 * @returns {Promise<object>}  { summary, alerts, suggestions, emoji }
 */
export async function getInsights(result) {
  const res = await fetch(`${BASE_URL}/api/insights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(result),
  });

  if (!res.ok) throw new Error('AI insights unavailable');
  return res.json();
}
