/**
 * PulseGuard Dashboard - Client Application
 *
 * Handles video upload, webcam capture, API communication,
 * and result rendering including waveform charts and SQI indicators.
 *
 * See docs/modules/07_frontend_dashboard.md for implementation details.
 */

"use strict";

const API_BASE = window.location.origin;

/* ============================================================
   State
   ============================================================ */

let selectedFile = null;
let waveformChart = null;
let webcamStream = null;
let mediaRecorder = null;
let recordedChunks = [];
let countdownInterval = null;
let isRecording = false;

/* ============================================================
   DOM references
   ============================================================ */

const $ = (id) => document.getElementById(id);

const dom = {
    // Input mode
    btnUploadMode: $("btn-upload-mode"),
    btnWebcamMode: $("btn-webcam-mode"),
    uploadSection: $("upload-section"),
    webcamSection: $("webcam-section"),

    // File upload
    dropZone: $("drop-zone"),
    fileInput: $("file-input"),
    fileInfo: $("file-info"),
    fileName: $("file-name"),
    fileSize: $("file-size"),
    fileRemove: $("file-remove"),
    btnAnalyze: $("btn-analyze"),

    // Webcam
    webcamPreview: $("webcam-preview"),
    webcamCountdown: $("webcam-countdown"),
    btnWebcamAction: $("btn-webcam-action"),

    // Demo
    btnDemo: $("btn-demo"),

    // BPM
    bpmWaiting: $("bpm-waiting"),
    bpmDisplay: $("bpm-display"),
    bpmValue: $("bpm-value"),
    sqiDot: $("sqi-dot"),
    sqiText: $("sqi-text"),

    // Warning
    warningBar: $("warning-bar"),
    warningMessages: $("warning-messages"),

    // Results
    resultsSection: $("results-section"),
    bvpChart: $("bvp-chart"),

    // HRV metrics
    metricRmssd: $("metric-rmssd"),
    metricSdnn: $("metric-sdnn"),
    metricPnn50: $("metric-pnn50"),
    metricLfhf: $("metric-lfhf"),
    metricMeanhr: $("metric-meanhr"),

    // Stress
    stressCard: $("stress-card"),
    stressLevel: $("stress-level"),
    stressConfidence: $("stress-confidence"),

    // ROI
    roiBarForehead: $("roi-bar-forehead"),
    roiBarLeft: $("roi-bar-left"),
    roiBarRight: $("roi-bar-right"),
    roiScoreForehead: $("roi-score-forehead"),
    roiScoreLeft: $("roi-score-left"),
    roiScoreRight: $("roi-score-right"),

    // Loading
    loadingOverlay: $("loading-overlay"),
};

/* ============================================================
   Input mode toggle
   ============================================================ */

dom.btnUploadMode.addEventListener("click", () => {
    dom.btnUploadMode.classList.add("active");
    dom.btnWebcamMode.classList.remove("active");
    dom.uploadSection.style.display = "";
    dom.webcamSection.classList.remove("visible");
    stopWebcam();
});

dom.btnWebcamMode.addEventListener("click", async () => {
    dom.btnWebcamMode.classList.add("active");
    dom.btnUploadMode.classList.remove("active");
    dom.uploadSection.style.display = "none";
    dom.webcamSection.classList.add("visible");
    await startWebcamPreview();
});

/* ============================================================
   File upload (drag & drop + click)
   ============================================================ */

dom.dropZone.addEventListener("click", () => dom.fileInput.click());

dom.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dom.dropZone.classList.add("drag-over");
});

dom.dropZone.addEventListener("dragleave", () => {
    dom.dropZone.classList.remove("drag-over");
});

dom.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dom.dropZone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith("video/")) {
        setSelectedFile(files[0]);
    }
});

dom.fileInput.addEventListener("change", () => {
    if (dom.fileInput.files.length > 0) {
        setSelectedFile(dom.fileInput.files[0]);
    }
});

dom.fileRemove.addEventListener("click", () => {
    clearSelectedFile();
});

function setSelectedFile(file) {
    selectedFile = file;
    dom.fileName.textContent = file.name;
    dom.fileSize.textContent = formatFileSize(file.size);
    dom.fileInfo.classList.add("visible");
    dom.dropZone.style.display = "none";
    dom.btnAnalyze.disabled = false;
}

function clearSelectedFile() {
    selectedFile = null;
    dom.fileInput.value = "";
    dom.fileInfo.classList.remove("visible");
    dom.dropZone.style.display = "";
    dom.btnAnalyze.disabled = true;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
}

/* ============================================================
   Analyze button
   ============================================================ */

dom.btnAnalyze.addEventListener("click", async () => {
    if (!selectedFile) return;
    await runAnalysis(selectedFile);
});

async function runAnalysis(file) {
    showLoading(true);
    hideWarnings();

    try {
        const data = await analyzeVideo(file);
        renderResults(data);
    } catch (err) {
        showError(err.message || "Analysis failed. Please try again.");
    } finally {
        showLoading(false);
    }
}

/* ============================================================
   API communication
   ============================================================ */

async function analyzeVideo(file) {
    const formData = new FormData();
    formData.append("video", file);

    let response;
    try {
        response = await fetch("/api/analyze", {
            method: "POST",
            body: formData,
        });
    } catch (networkErr) {
        throw new Error("Cannot connect to server. Is the API running?");
    }

    if (response.status === 404 || response.status === 405 || response.status === 501) {
        throw new Error(
            "The /api/analyze endpoint is not available yet (Module 06). Use the Demo button to preview the dashboard."
        );
    }

    if (!response.ok) {
        let detail = "Analysis failed";
        try {
            const error = await response.json();
            detail = error.detail || detail;
        } catch (_) { }
        throw new Error(detail);
    }

    return await response.json();
}

/* ============================================================
   Webcam capture
   ============================================================ */

async function startWebcamPreview() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError("Webcam requires HTTPS or localhost. Serve via FastAPI or use a secure connection.");
        return;
    }
    try {
        webcamStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: "user" },
        });
        dom.webcamPreview.srcObject = webcamStream;
        await dom.webcamPreview.play();
    } catch (err) {
        showError("Could not access webcam: " + err.message);
    }
}

function stopWebcam() {
    if (webcamStream) {
        webcamStream.getTracks().forEach((t) => t.stop());
        webcamStream = null;
    }
    dom.webcamPreview.srcObject = null;
    stopRecording();
}

dom.btnWebcamAction.addEventListener("click", () => {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording(30);
    }
});

function startRecording(durationSeconds) {
    if (!webcamStream) return;

    recordedChunks = [];
    mediaRecorder = new MediaRecorder(webcamStream, { mimeType: "video/webm" });
    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordedChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: "video/webm" });
        const file = new File([blob], "webcam-capture.webm", { type: "video/webm" });
        await runAnalysis(file);
    };

    mediaRecorder.start();
    isRecording = true;
    dom.btnWebcamAction.textContent = "Stop Recording";
    dom.btnWebcamAction.classList.add("recording");

    // Countdown
    let remaining = durationSeconds;
    dom.webcamCountdown.textContent = remaining + "s";
    dom.webcamCountdown.classList.add("visible");

    countdownInterval = setInterval(() => {
        remaining--;
        dom.webcamCountdown.textContent = remaining + "s";
        if (remaining <= 0) {
            stopRecording();
        }
    }, 1000);
}

function stopRecording() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    dom.webcamCountdown.classList.remove("visible");
    dom.btnWebcamAction.textContent = "Start Recording";
    dom.btnWebcamAction.classList.remove("recording");

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
    isRecording = false;
}

/* ============================================================
   Result rendering
   ============================================================ */

function renderResults(data) {
    // API returns flat structure — build the shape renderResults expects
    const signal = {
        bpm:         data.bpm,
        sqi_score:   data.sqi_score,
        sqi_level:   data.sqi_level,
        bvp_signal:  data.bvp_waveform,   // renamed field
        per_roi_sqi: data.per_roi_sqi,
    };

    const { hrv, stress_level, stress_confidence, warnings } = data;

    dom.resultsSection.classList.add("visible");

    if (warnings && warnings.length > 0) showWarnings(warnings);

    renderBPM(signal.bpm, signal.sqi_score, signal.sqi_level);
    renderWaveform(signal.bvp_signal, signal.sqi_level);
    renderHRV(hrv);
    renderStress(stress_level, stress_confidence);

    if (signal.per_roi_sqi && signal.per_roi_sqi.length >= 3) {
        renderROI(signal.per_roi_sqi);
    }
}

/* ---- BPM ---- */

function renderBPM(bpm, sqiScore, sqiLevel) {
    dom.bpmWaiting.style.display = "none";
    dom.bpmDisplay.style.display = "";

    if (bpm === null || bpm === undefined || sqiLevel === "LOW") {
        dom.bpmValue.textContent = "--";
        dom.bpmValue.classList.add("suppressed");
    } else {
        dom.bpmValue.classList.remove("suppressed");
        animateCountUp(dom.bpmValue, Math.round(bpm));
    }

    renderSQI(sqiScore, sqiLevel);
}

function animateCountUp(el, target) {
    const duration = 800;
    const start = performance.now();
    const from = 0;

    el.classList.add("animating");

    function step(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const current = Math.round(from + (target - from) * eased);
        el.textContent = current;

        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            el.textContent = target;
            el.classList.remove("animating");
        }
    }

    requestAnimationFrame(step);
}

/* ---- SQI ---- */

function renderSQI(score, level) {
    const dot = dom.sqiDot;
    const text = dom.sqiText;

    dot.className = "sqi-dot";
    if (level === "HIGH") dot.classList.add("high");
    else if (level === "MEDIUM") dot.classList.add("medium");
    else if (level === "LOW") dot.classList.add("low");

    const pct = score !== null && score !== undefined
        ? (score * 100).toFixed(0) + "%"
        : "--";
    text.textContent = `Signal Quality: ${level || "--"} (${pct})`;
}

/* ---- BVP Waveform ---- */

function renderWaveform(bvpSignal, sqiLevel) {
    if (!bvpSignal || bvpSignal.length === 0) return;

    const labels = bvpSignal.map((_, i) => (i / 30).toFixed(1)); // assume 30 fps

    const lineColor = sqiLevel === "LOW" ? "rgba(248, 113, 113, 0.8)" : "#6c9cfc";
    const fillColor = sqiLevel === "LOW" ? "rgba(248, 113, 113, 0.05)" : "rgba(108, 156, 252, 0.1)";

    if (waveformChart) {
        waveformChart.destroy();
    }

    const ctx = dom.bvpChart.getContext("2d");
    waveformChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: "BVP Signal",
                data: bvpSignal,
                borderColor: lineColor,
                backgroundColor: fillColor,
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
                    ticks: {
                        color: "#9aa0a6",
                        maxTicksLimit: 15,
                    },
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

/* ---- HRV Metrics ---- */

function renderHRV(hrv) {
    if (!hrv) {
        setMetric(dom.metricRmssd, "--", true);
        setMetric(dom.metricSdnn, "--", true);
        setMetric(dom.metricPnn50, "--", true);
        setMetric(dom.metricLfhf, "--", true);
        setMetric(dom.metricMeanhr, "--", true);
        return;
    }

    setMetric(dom.metricRmssd, hrv.rmssd?.toFixed(1) ?? "--", !hrv.rmssd);
    setMetric(dom.metricSdnn, hrv.sdnn?.toFixed(1) ?? "--", !hrv.sdnn);
    setMetric(dom.metricPnn50, hrv.pnn50?.toFixed(1) ?? "--", !hrv.pnn50);
    setMetric(dom.metricLfhf, hrv.lf_hf_ratio?.toFixed(2) ?? "--", hrv.lf_hf_ratio == null);
    setMetric(dom.metricMeanhr, hrv.mean_hr?.toFixed(0) ?? "--", !hrv.mean_hr);
}

function setMetric(el, value, muted) {
    el.textContent = value;
    el.classList.toggle("muted", muted);
}

/* ---- Stress ---- */

function renderStress(level, confidence) {
    const card = dom.stressCard;
    const levelEl = dom.stressLevel;
    const confEl = dom.stressConfidence;

    // Clear old classes
    card.classList.remove("stress-low", "stress-moderate", "stress-high", "stress-unknown");
    levelEl.classList.remove("low", "moderate", "high", "unknown");

    if (!level || level === "UNKNOWN") {
        card.classList.add("stress-unknown");
        levelEl.classList.add("unknown");
        levelEl.textContent = "Insufficient Data";
        confEl.textContent = "";
        return;
    }

    const key = level.toLowerCase();
    card.classList.add("stress-" + key);
    levelEl.classList.add(key);
    levelEl.textContent = level;

    if (confidence !== null && confidence !== undefined) {
        confEl.textContent = `Confidence: ${(confidence * 100).toFixed(0)}%`;
    } else {
        confEl.textContent = "";
    }
}

/* ---- ROI Quality ---- */

function renderROI(scores) {
    const bars = [dom.roiBarForehead, dom.roiBarLeft, dom.roiBarRight];
    const labels = [dom.roiScoreForehead, dom.roiScoreLeft, dom.roiScoreRight];

    scores.forEach((score, i) => {
        const pct = Math.round(score * 100);
        bars[i].style.width = pct + "%";

        bars[i].classList.remove("high", "medium", "low");
        if (score > 0.6) bars[i].classList.add("high");
        else if (score > 0.35) bars[i].classList.add("medium");
        else bars[i].classList.add("low");

        labels[i].textContent = (score * 100).toFixed(0) + "%";
    });
}

/* ============================================================
   Warnings & errors
   ============================================================ */

function showWarnings(messages) {
    dom.warningBar.classList.remove("error");
    dom.warningBar.classList.add("visible");
    dom.warningMessages.innerHTML = messages
        .map((m) => `<span>${escapeHtml(m)}</span>`)
        .join("");
}

function showError(message) {
    dom.warningBar.classList.add("visible", "error");
    dom.warningMessages.innerHTML = `<span>${escapeHtml(message)}</span>`;
}

function hideWarnings() {
    dom.warningBar.classList.remove("visible", "error");
    dom.warningMessages.innerHTML = "";
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

/* ============================================================
   Loading overlay
   ============================================================ */

function showLoading(show) {
    dom.loadingOverlay.classList.toggle("visible", show);
}

/* ============================================================
   Demo mode
   ============================================================ */

dom.btnDemo.addEventListener("click", () => {
    const demoData = generateDemoData();
    hideWarnings();
    renderResults(demoData);
});

function generateDemoData() {
    // Generate a realistic BVP waveform (1.2 Hz = 72 BPM, 30 fps, 10s)
    const fps = 30;
    const duration = 10;
    const numSamples = fps * duration;
    const bvp = [];

    for (let i = 0; i < numSamples; i++) {
        const t = i / fps;
        const cardiac = Math.sin(2 * Math.PI * 1.2 * t);
        const harmonic = 0.3 * Math.sin(2 * Math.PI * 2.4 * t);
        const noise = 0.05 * (Math.random() - 0.5);
        bvp.push(cardiac + harmonic + noise);
    }

    return {
        signal: {
            bvp_signal: bvp,
            bpm: 74,
            peak_indices: [],
            sqi_score: 0.82,
            sqi_level: "HIGH",
            per_roi_sqi: [0.88, 0.76, 0.71],
        },
        hrv: {
            rmssd: 42.1,
            sdnn: 51.3,
            pnn50: 18.5,
            lf_hf_ratio: 1.4,
            mean_hr: 74.2,
            ibi_ms: [],
        },
        stress_level: "LOW",
        stress_confidence: 0.72,
        processing_time_ms: 2340,
        warnings: [],
    };
}

/* ============================================================
   Init
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
    // Ensure upload mode is shown by default
    dom.uploadSection.style.display = "";
    dom.webcamSection.classList.remove("visible");
});