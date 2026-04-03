# Module 7: Frontend Dashboard

Owner: P4 (Frontend Lead)

## Purpose

Present the analysis results in a polished, interactive web dashboard. The
frontend handles video upload, webcam capture, API communication, and renders
all output components: BPM display, SQI indicator, BVP waveform chart, HRV
metrics, stress classification, and ROI quality visualization.

## Technology

- **HTML5** for structure
- **CSS3** (vanilla, no framework) for styling
- **JavaScript** (ES6+, no framework) for logic
- **Chart.js 4.x** (CDN) for waveform and chart rendering
- **Inter** (Google Fonts) for typography

No build step. No npm. Files are served directly by FastAPI as static assets.

## Design Specification

### Visual Identity

- **Theme**: Dark mode with glassmorphism panels
- **Background**: Deep navy (#0a0e1a) with subtle gradient
- **Cards**: Semi-transparent backgrounds with backdrop blur and thin borders
- **Accent**: Blue (#6c9cfc) for primary actions and highlights
- **SQI colors**: Green (#34d399), Yellow (#fbbf24), Red (#f87171)
- **Font**: Inter at weights 300, 400, 500, 600, 700

### Layout Structure

```
+-----------------------------------------------------+
|  PulseGuard          Contact-Free Cardiac Monitor    |
+-----------------------------------------------------+
|                                                       |
|  +------------------+  +---------------------------+ |
|  |                  |  |                           | |
|  |  Video Upload    |  |   BPM Display             | |
|  |  or Webcam       |  |   [  74  ] BPM            | |
|  |  Preview         |  |   SQI: [green dot] 0.82   | |
|  |                  |  |                           | |
|  +------------------+  +---------------------------+ |
|                                                       |
|  +--------------------------------------------------+|
|  |  BVP Waveform                                    ||
|  |  [======  chart  ==============================] ||
|  +--------------------------------------------------+|
|                                                       |
|  +-------------+  +-------------+  +---------------+ |
|  |  RMSSD      |  |  SDNN       |  |  Stress       | |
|  |  42.1 ms    |  |  51.3 ms    |  |  LOW          | |
|  +-------------+  +-------------+  +---------------+ |
|  +-------------+  +-------------+  +---------------+ |
|  |  pNN50      |  |  LF/HF      |  |  Confidence   | |
|  |  18.5%      |  |  1.4         |  |  72%          | |
|  +-------------+  +-------------+  +---------------+ |
+-----------------------------------------------------+
```

### Component Details

#### 1. Input Section (Left Panel)

**Video Upload:**
- Drag-and-drop zone with dashed border
- Click to select file
- Shows file name and size after selection
- "Analyze" button triggers upload

**Webcam Capture:**
- Toggle button: "Switch to Webcam"
- Shows live preview in a video element
- 30-second countdown timer
- "Start Recording" / "Stop" button
- After capture, shows preview of recorded clip

#### 2. BPM Display (Right of input)

- Large numeric display (font size 48-64px, weight 700)
- Animated on appearance (count up from 0)
- Below BPM: SQI indicator as colored dot + text
- When SQI is LOW: BPM shows "--" with red dot and warning text

#### 3. BVP Waveform Chart

- Chart.js line chart, full width
- X-axis: time in seconds (0-30)
- Y-axis: BVP amplitude (no units, normalized)
- Line color: accent blue with 50% opacity fill below
- Smooth line with tension=0.3
- On LOW SQI: chart shows in red/gray to indicate unreliable data

#### 4. HRV Metrics Grid

- 2x3 grid of metric cards
- Each card: metric name (small, secondary color), value (large, primary color)
- Cards have glassmorphism styling (backdrop blur, border)
- When HRV is null: cards show "--" in muted color

#### 5. Stress Classification

- Dedicated card with larger visual presence
- Background gradient changes with stress level:
  - LOW: dark green gradient
  - MODERATE: dark amber gradient
  - HIGH: dark red gradient
- Shows stress level text and confidence percentage
- When UNKNOWN: neutral gray gradient, "Insufficient Data" text

#### 6. ROI Quality Visualization (Stretch goal)

- Three small indicators (Forehead, Left Cheek, Right Cheek)
- Each shows a colored bar proportional to that ROI's SQI score
- Gives visual feedback about which face regions contributed

### Warnings Display

When the API response contains warnings:
- Show a warning bar below the input section
- Amber background with appropriate icon
- List all warning messages

## Implementation Guide

### API Communication

```javascript
async function analyzeVideo(file) {
    const formData = new FormData();
    formData.append("video", file);

    const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Analysis failed");
    }

    return await response.json();
}
```

### Waveform Chart Setup

```javascript
function createWaveformChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext("2d");
    return new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [{
                label: "BVP Signal",
                data: [],
                borderColor: "#6c9cfc",
                backgroundColor: "rgba(108, 156, 252, 0.1)",
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                fill: true,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 800 },
            scales: {
                x: {
                    title: { display: true, text: "Time (s)", color: "#9aa0a6" },
                    ticks: { color: "#9aa0a6" },
                    grid: { color: "rgba(255,255,255,0.05)" },
                },
                y: {
                    title: { display: true, text: "Amplitude", color: "#9aa0a6" },
                    ticks: { color: "#9aa0a6" },
                    grid: { color: "rgba(255,255,255,0.05)" },
                },
            },
            plugins: {
                legend: { display: false },
            },
        },
    });
}
```

### Webcam Capture

```javascript
async function startWebcamCapture(durationSeconds) {
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
    });

    const video = document.getElementById("webcam-preview");
    video.srcObject = stream;
    await video.play();

    const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);

    recorder.start();

    return new Promise((resolve) => {
        setTimeout(() => {
            recorder.stop();
            stream.getTracks().forEach((t) => t.stop());
            recorder.onstop = () => {
                const blob = new Blob(chunks, { type: "video/webm" });
                resolve(blob);
            };
        }, durationSeconds * 1000);
    });
}
```

### SQI Traffic Light

```javascript
function renderSQI(score, level) {
    const dot = document.getElementById("sqi-dot");
    const text = document.getElementById("sqi-text");

    const colors = { HIGH: "#34d399", MEDIUM: "#fbbf24", LOW: "#f87171" };
    dot.style.backgroundColor = colors[level] || "#5f6368";
    dot.style.boxShadow = `0 0 12px ${colors[level] || "#5f6368"}`;
    text.textContent = `${level} (${(score * 100).toFixed(0)}%)`;
}
```

## CSS Card Styling Reference

```css
.card {
    background: rgba(255, 255, 255, 0.04);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 24px;
    transition: background 200ms ease, border-color 200ms ease;
}

.card:hover {
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.14);
}
```

## Testing

Frontend testing is primarily manual during the hackathon:
- Upload a video, verify all fields populate
- Upload a noisy video, verify warnings and suppressed output
- Test webcam flow end-to-end
- Test on both Chrome and Firefox
- Verify responsive behavior at 1920x1080 and 1366x768

## Priorities

1. Video upload + result display (must have)
2. BVP waveform chart (must have)
3. SQI traffic light and output suppression (must have)
4. HRV metrics grid (must have)
5. Stress classification display (must have)
6. Webcam capture (should have)
7. ROI quality visualization (nice to have)
8. Animated transitions (nice to have)
