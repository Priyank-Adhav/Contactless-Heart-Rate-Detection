# App Module 3: API Client

Owner: P3 (Backend Lead)

## Purpose

Single file that handles all HTTP communication between the mobile app and the
Python FastAPI backend. Every other module imports from this file.

## How It Works

```
Phone records video  →  api.js uploads to server  →  server processes  →  JSON back
```

The phone and server must be on the **same WiFi**. The server must be started
with `--host 0.0.0.0` to accept connections from other devices.

## Implementation Guide

### `src/services/api.js`

```javascript
// ══════════════════════════════════════════════════
//  CHANGE THIS to your computer's local IP address
//  Find it: hostname -I (Linux), ipconfig (Windows)
// ══════════════════════════════════════════════════
const BASE_URL = 'http://192.168.1.100:8000';

/**
 * Health check — test if the backend is reachable.
 * Call this on app start to verify connection.
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
 * Upload a recorded video for cardiac analysis.
 *
 * @param {string} videoUri  Local file URI from expo-camera recording
 * @returns {Promise<object>} Analysis result:
 *   {
 *     bpm: 74.2,
 *     sqi_score: 0.82, sqi_level: "HIGH",
 *     hrv: { rmssd, sdnn, pnn50, lf_hf_ratio, mean_hr, ibi_ms },
 *     stress_level: "LOW", stress_confidence: 0.72,
 *     bvp_waveform: [...],
 *     warnings: [],
 *     processing_time_ms: 2340
 *   }
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
 *
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
```

## Starting the Backend Server

```bash
# Terminal 1: Start Python server (accessible from phone)
cd Contactless-Heart-Rate-Detection
source venv/bin/activate
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Find your IP for the app config:
hostname -I          # Linux → e.g. 192.168.1.100
```

## Testing Checklist

- [ ] `checkHealth()` returns `true` when server is running
- [ ] `checkHealth()` returns `false` when server is off
- [ ] `analyzeVideo()` uploads successfully (check server terminal for logs)
- [ ] Error thrown for unreachable server has a clear message
- [ ] Response JSON has all expected fields (bpm, hrv, stress_level, etc.)
