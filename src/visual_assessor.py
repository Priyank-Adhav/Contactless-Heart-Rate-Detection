"""
Visual Assessment Module — Triage Decision Agent Fallback

When the rPPG signal quality (SQI) drops below a confidence threshold,
this module provides a fallback Visual Stress Score by analyzing visible
physical signs of distress from the video frames:

    1. Pallor Detection  — skin color saturation analysis (HSV space)
    2. Breathing Rate     — vertical oscillation of face bounding box
    3. Motion / Tremor    — frame-to-frame landmark jitter

The Triage Decision Agent in the API selects whichever mode (Biometric
or Visual Assessment) is more trustworthy for the current environment.

See TWIST 1 requirements for full specification.
"""

import logging
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core assessment functions
# ---------------------------------------------------------------------------

def _detect_pallor(frames: List[np.ndarray], face_boxes: List[tuple]) -> dict:
    """Analyze skin color for signs of pallor (abnormal paleness).

    Pallor indicates poor blood perfusion — a sign of shock, anemia,
    or severe stress. We measure average skin saturation in HSV space.

    Normal skin:  saturation 40-180, value 120-250
    Pallor:       saturation < 40, value > 180 (washed out)
    """
    saturations = []
    values = []

    for frame, box in zip(frames, face_boxes):
        if box is None:
            continue
        x, y, w, h = box
        # Extract face region, center 60% to avoid hair/background
        cx, cy = x + w // 2, y + h // 2
        rw, rh = int(w * 0.3), int(h * 0.3)
        roi = frame[max(0, cy - rh):cy + rh, max(0, cx - rw):cx + rw]

        if roi.size == 0:
            continue

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        saturations.append(float(np.mean(hsv[:, :, 1])))
        values.append(float(np.mean(hsv[:, :, 2])))

    if not saturations:
        return {"pallor_score": 0.5, "detail": "Could not analyze skin color"}

    avg_sat = np.mean(saturations)
    avg_val = np.mean(values)

    # Score: 0 = healthy color, 1 = severe pallor
    # Low saturation + high value = pale
    sat_score = np.clip(1.0 - (avg_sat - 20) / 80, 0, 1)  # pale if sat < 40
    val_score = np.clip((avg_val - 160) / 60, 0, 1)        # pale if val > 180

    pallor_score = round(float(0.6 * sat_score + 0.4 * val_score), 3)

    detail = "Normal skin color"
    if pallor_score > 0.7:
        detail = "Significant pallor detected — possible poor perfusion"
    elif pallor_score > 0.4:
        detail = "Mild pallor detected — skin appears slightly pale"

    logger.info("Pallor: score=%.3f, avg_sat=%.1f, avg_val=%.1f", pallor_score, avg_sat, avg_val)
    return {"pallor_score": pallor_score, "detail": detail}


def _estimate_breathing_rate(face_boxes: List[tuple], fps: float) -> dict:
    """Estimate breathing rate from vertical oscillation of face position.

    When a person breathes, their shoulders and head move slightly up
    and down. By tracking the Y-coordinate of the face bounding box
    center over time, we can detect this oscillation.

    Normal: 12-20 breaths/min
    Elevated: 20-30 (tachypnea, stress)
    Critical: > 30 (severe respiratory distress)
    """
    if len(face_boxes) < int(fps * 3):
        return {"breathing_rate": None, "breathing_score": 0.5,
                "detail": "Insufficient frames for breathing analysis"}

    # Extract Y-centers
    y_centers = []
    for box in face_boxes:
        if box is not None:
            _, y, _, h = box
            y_centers.append(y + h / 2)
        elif y_centers:
            y_centers.append(y_centers[-1])  # hold last value

    if len(y_centers) < int(fps * 3):
        return {"breathing_rate": None, "breathing_score": 0.5,
                "detail": "Face not consistently detected"}

    y_arr = np.array(y_centers, dtype=np.float64)

    # Detrend and filter for breathing band (0.15-0.5 Hz = 9-30 breaths/min)
    from scipy.signal import butter, detrend, filtfilt

    y_arr = detrend(y_arr)
    nyq = fps / 2
    low = max(0.15 / nyq, 0.001)
    high = min(0.5 / nyq, 0.999)
    b, a = butter(2, [low, high], btype='band')
    y_filt = filtfilt(b, a, y_arr)

    # FFT to find dominant breathing frequency
    freqs = np.fft.rfftfreq(len(y_filt), 1.0 / fps)
    spectrum = np.abs(np.fft.rfft(y_filt))
    breath_mask = (freqs >= 0.15) & (freqs <= 0.5)

    if not np.any(breath_mask):
        return {"breathing_rate": None, "breathing_score": 0.5,
                "detail": "Could not isolate breathing signal"}

    peak_idx = np.argmax(spectrum[breath_mask])
    breathing_hz = float(freqs[breath_mask][peak_idx])
    breathing_rate = round(breathing_hz * 60, 1)

    # Score: 0 = normal, 1 = severe distress
    if breathing_rate <= 20:
        score = 0.1
        detail = f"Normal breathing: {breathing_rate} breaths/min"
    elif breathing_rate <= 25:
        score = 0.4
        detail = f"Slightly elevated: {breathing_rate} breaths/min"
    elif breathing_rate <= 30:
        score = 0.7
        detail = f"Elevated breathing: {breathing_rate} breaths/min — possible stress"
    else:
        score = 0.9
        detail = f"Rapid breathing: {breathing_rate} breaths/min — respiratory distress"

    logger.info("Breathing: rate=%.1f/min, score=%.2f", breathing_rate, score)
    return {"breathing_rate": breathing_rate, "breathing_score": round(score, 3),
            "detail": detail}


def _compute_motion_score(face_boxes: List[tuple], fps: float) -> dict:
    """Quantify facial tremor / excessive movement.

    High frame-to-frame jitter of the face position indicates tremor,
    shaking, or restlessness — common in severe distress.
    """
    if len(face_boxes) < 10:
        return {"motion_score": 0.5, "detail": "Insufficient data for motion analysis"}

    positions = []
    for box in face_boxes:
        if box is not None:
            x, y, w, h = box
            positions.append((x + w / 2, y + h / 2))

    if len(positions) < 10:
        return {"motion_score": 0.5, "detail": "Face not consistently detected"}

    pos = np.array(positions)
    # Frame-to-frame displacement (pixels)
    displacements = np.sqrt(np.sum(np.diff(pos, axis=0) ** 2, axis=1))
    avg_disp = float(np.mean(displacements))

    # Normalize by face size (first detected width)
    face_w = face_boxes[0][2] if face_boxes[0] is not None else 100
    norm_disp = avg_disp / max(face_w, 1)

    # Score: 0 = still, 1 = severe motion/tremor
    score = float(np.clip(norm_disp / 0.05, 0, 1))

    if score < 0.2:
        detail = "Subject is still — minimal movement"
    elif score < 0.5:
        detail = "Moderate movement detected"
    elif score < 0.7:
        detail = "Significant movement — patient may be restless"
    else:
        detail = "Excessive movement/tremor — possible severe distress"

    logger.info("Motion: norm_disp=%.4f, score=%.2f", norm_disp, score)
    return {"motion_score": round(score, 3), "detail": detail}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def assess_visual_distress(video_path: str) -> dict:
    """Run full visual assessment on a video when rPPG signal is unreliable.

    This is the fallback mode activated by the Triage Decision Agent when
    SQI drops below the confidence threshold.

    Returns:
        dict with keys:
            - visual_stress_score: float 0-1 (0=normal, 1=severe distress)
            - visual_stress_level: "LOW" / "MODERATE" / "HIGH"
            - pallor: {pallor_score, detail}
            - breathing: {breathing_rate, breathing_score, detail}
            - motion: {motion_score, detail}
            - details: list of human-readable observations
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _fallback_response("Could not open video file")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Sample every N frames to keep it fast (aim for ~100 samples)
    sample_step = max(1, total_frames // 100)

    frames = []
    face_boxes = []
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_step == 0:
            frames.append(frame)

            # Fast face detection via Haar cascade
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))

            if len(faces) > 0:
                # Take largest face
                areas = [w * h for (_, _, w, h) in faces]
                best = faces[np.argmax(areas)]
                face_boxes.append(tuple(best))
            else:
                face_boxes.append(None)

        frame_idx += 1

    cap.release()

    if len(frames) < 5:
        return _fallback_response("Video too short for visual assessment")

    face_detected_count = sum(1 for b in face_boxes if b is not None)
    if face_detected_count < 3:
        return _fallback_response("Face not reliably detected in video")

    # --- Run all three assessments ---
    pallor = _detect_pallor(frames, face_boxes)
    breathing = _estimate_breathing_rate(face_boxes, fps)
    motion = _compute_motion_score(face_boxes, fps)

    # --- Composite visual stress score ---
    # Weighted combination: pallor is most clinically important
    visual_score = (
        0.45 * pallor["pallor_score"]
        + 0.30 * breathing.get("breathing_score", 0.5)
        + 0.25 * motion["motion_score"]
    )
    visual_score = round(float(np.clip(visual_score, 0, 1)), 3)

    # Classify
    if visual_score >= 0.6:
        level = "HIGH"
    elif visual_score >= 0.35:
        level = "MODERATE"
    else:
        level = "LOW"

    # Collect details
    details = [
        pallor["detail"],
        breathing["detail"],
        motion["detail"],
    ]

    logger.info("Visual assessment: score=%.3f, level=%s", visual_score, level)

    return {
        "visual_stress_score": visual_score,
        "visual_stress_level": level,
        "pallor": pallor,
        "breathing": breathing,
        "motion": motion,
        "details": details,
    }


def _fallback_response(reason: str) -> dict:
    """Return a safe default when visual assessment can't run."""
    return {
        "visual_stress_score": 0.5,
        "visual_stress_level": "UNKNOWN",
        "pallor": {"pallor_score": 0.5, "detail": reason},
        "breathing": {"breathing_rate": None, "breathing_score": 0.5, "detail": reason},
        "motion": {"motion_score": 0.5, "detail": reason},
        "details": [reason],
    }
