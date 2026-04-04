"""
Visual Assessment Module — Gemini Vision-Powered Triage Fallback

TWIST 1: When the rPPG signal quality (SQI) drops below the confidence
threshold (movement, poor lighting), the Triage Decision Agent activates
this module as a fallback.

Instead of relying on biometric signal processing, this module:
    1. Extracts representative face frames from the video
    2. Sends them to Gemini Vision API with a structured medical prompt
    3. Receives a Visual 7Stress Score (0-10) + indicator analysis
    4. Returns structured results for the dashboard

The VLM analyzes visible physical signs of distress:
    - Pallor (abnormal paleness → poor perfusion)
    - Sweating / perspiration (autonomic stress response)
    - Cyanosis (bluish discoloration → oxygen deprivation)
    - Labored breathing patterns (visible chest/shoulder movement)
    - Facial tension / grimacing (pain / distress indicators)

This approach is more robust than a custom CNN because:
    - No training data required
    - Handles edge cases a CNN wouldn't be trained on
    - Provides natural language reasoning (explainable!)
    - Works across diverse skin tones and lighting conditions
"""

import base64
import json
import logging
import os
import re
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini Vision API interaction
# ---------------------------------------------------------------------------

VISUAL_TRIAGE_PROMPT = """You are an expert medical triage AI analyzing a patient's face from a video frame captured by a health monitoring app called PulseGuard.

The biometric heart rate sensor (rPPG) could not get a reliable reading, so you must provide a thorough VISUAL assessment of the patient's physical state.

Carefully analyze the face image for these 5 clinical indicators:

1. **Pallor** — Is the skin abnormally pale? Check forehead, cheeks, and lip color.
   (Indicates: poor blood perfusion, anemia, shock, blood loss)

2. **Sweating/Perspiration** — Is there visible moisture, shine, or bead formation on the skin?
   (Indicates: autonomic stress response, fever, anxiety, cardiac events)

3. **Cyanosis** — Any bluish or grayish discoloration of lips, earlobes, or periorbital area?
   (Indicates: oxygen deprivation, respiratory distress, circulatory problems)

4. **Breathing Pattern** — Signs of labored, rapid, or irregular breathing?
   Look for: open mouth breathing, nasal flaring, visible neck muscle strain, elevated shoulders
   (Indicates: respiratory distress, asthma, panic attack, cardiac compromise)

5. **Facial Distress** — Signs of pain, anxiety, fear, or distress in the expression?
   Look for: furrowed brow, tightened jaw, grimacing, wide/fearful eyes, asymmetric expression
   (Indicates: pain, anxiety, neurological issues, emotional distress)

You MUST respond in this EXACT JSON format and NOTHING else:
{
    "visual_stress_score": <number 0-10, where 0=completely calm/healthy, 10=severe distress>,
    "confidence": <number 0.0-1.0, your confidence in this assessment>,
    "estimated_heart_rate_range": "<string like '60-80 BPM' based on facial color/distress level, or 'Unable to estimate'>",
    "urgency": "<one of: NONE, LOW, MODERATE, HIGH, CRITICAL>",
    "indicators": {
        "pallor": {"score": <0-10>, "description": "<2-3 sentence detailed observation>"},
        "sweating": {"score": <0-10>, "description": "<2-3 sentence detailed observation>"},
        "cyanosis": {"score": <0-10>, "description": "<2-3 sentence detailed observation>"},
        "breathing": {"score": <0-10>, "description": "<2-3 sentence detailed observation>"},
        "facial_distress": {"score": <0-10>, "description": "<2-3 sentence detailed observation>"}
    },
    "overall_assessment": "<2-3 sentence clinical summary of the patient's visible condition>",
    "recommended_action": "<specific actionable recommendation based on findings>",
    "wellness_tips": [
        "<specific tip 1 e.g. 'Practice 4-7-8 breathing technique for 5 minutes'>",
        "<specific tip 2 e.g. 'Take a 10-minute walk to improve circulation'>",
        "<specific tip 3 e.g. 'Ensure adequate hydration - drink 250ml water'>"
    ]
}

Important guidelines:
- Give DETAILED descriptions for each indicator, not one-word answers
- wellness_tips should be specific and actionable (exercises, breathing, hydration, rest)
- For healthy-looking individuals, still provide wellness maintenance tips
- estimated_heart_rate_range should reflect visible stress indicators
- If the image is unclear, rate uncertain indicators as 5 and explain the limitation"""


def _get_api_key() -> Optional[str]:
    """Get Gemini API key from environment or .env file."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    # Try loading from .env file
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def _extract_face_frame(video_path: str) -> Optional[np.ndarray]:
    """Extract the best face frame from the video.

    Samples frames at 1-second intervals, picks the one with the
    largest detected face (best quality for VLM analysis).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    best_frame = None
    best_face_area = 0

    # Sample every 1 second
    sample_step = max(int(fps), 1)
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))

            if len(faces) > 0:
                areas = [w * h for (_, _, w, h) in faces]
                max_area = max(areas)
                if max_area > best_face_area:
                    best_face_area = max_area
                    best_frame = frame.copy()

        frame_idx += 1

    cap.release()

    # If no face found, just use the middle frame
    if best_frame is None:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, best_frame = cap.read()
        cap.release()
        if not ret:
            return None

    return best_frame


def _frame_to_base64(frame: np.ndarray) -> str:
    """Encode a frame as base64 JPEG for API transmission."""
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode("utf-8")


def _call_gemini_vision(frame_b64: str, api_key: str) -> dict:
    """Call Gemini Vision API to analyze the face frame.

    Includes retry logic for free-tier rate limits (429 errors).
    """
    import time

    from google import genai

    client = genai.Client(api_key=api_key)

    # Try multiple models — each has separate quota on free tier
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

    last_error = None
    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        {
                            "role": "user",
                            "parts": [
                                {"text": VISUAL_TRIAGE_PROMPT},
                                {
                                    "inline_data": {
                                        "mime_type": "image/jpeg",
                                        "data": frame_b64,
                                    }
                                },
                            ],
                        }
                    ],
                )

                text = response.text.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    match = re.search(r"\{[\s\S]*\}", text)
                    if match:
                        return json.loads(match.group())
                    logger.error("Failed to parse Gemini response: %s", text[:200])
                    raise ValueError("Gemini returned non-JSON response")

            except Exception as e:
                last_error = e
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait = 5 * (attempt + 1)
                    logger.warning("%s rate limited (attempt %d), waiting %ds...",
                                   model_name, attempt + 1, wait)
                    time.sleep(wait)
                else:
                    raise
        # If all attempts for this model failed, try next model
        logger.info("All attempts for %s exhausted, trying next model", model_name)

    raise last_error  # all models and retries exhausted


# ---------------------------------------------------------------------------
# Fallback: OpenCV heuristic analysis (when no API key available)
# ---------------------------------------------------------------------------

def _heuristic_assessment(video_path: str) -> dict:
    """Basic OpenCV-based visual assessment when Gemini is unavailable.

    Uses skin color analysis (HSV) and motion detection as a simpler
    fallback — not as good as VLM but still provides useful signal.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _default_response("Could not open video")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    saturations = []
    brightnesses = []
    prev_gray = None
    motion_scores = []

    frame_idx = 0
    sample_step = max(int(fps / 5), 1)  # 5 samples per second

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_step == 0:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            saturations.append(float(np.mean(hsv[:, :, 1])))
            brightnesses.append(float(np.mean(hsv[:, :, 2])))

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion_scores.append(float(np.mean(diff)))
            prev_gray = gray
        frame_idx += 1

    cap.release()

    if not saturations:
        return _default_response("No frames analyzed")

    avg_sat = np.mean(saturations)
    avg_bright = np.mean(brightnesses)
    avg_motion = np.mean(motion_scores) if motion_scores else 0

    # Pallor: low saturation + high brightness
    pallor = float(np.clip((1 - avg_sat / 100) * 5 + (avg_bright / 255) * 3, 0, 10))
    # Motion-based distress estimate
    motion_distress = float(np.clip(avg_motion / 10, 0, 10))
    # Composite
    score = round((pallor * 0.5 + motion_distress * 0.5), 1)
    score = min(score, 10.0)

    level = "HIGH" if score >= 6 else "MODERATE" if score >= 3.5 else "LOW"

    return {
        "visual_stress_score": score,
        "visual_stress_level": level,
        "confidence": 0.4,
        "analysis_method": "heuristic_opencv",
        "indicators": {
            "pallor": {"score": round(pallor, 1), "description": f"Skin saturation avg: {avg_sat:.0f}"},
            "sweating": {"score": 5, "description": "Cannot detect via basic analysis"},
            "cyanosis": {"score": 5, "description": "Cannot detect via basic analysis"},
            "breathing": {"score": round(motion_distress, 1), "description": f"Motion level: {avg_motion:.1f}"},
            "facial_distress": {"score": 5, "description": "Cannot detect via basic analysis"},
        },
        "overall_assessment": f"Heuristic analysis — pallor score {pallor:.1f}/10, motion {motion_distress:.1f}/10",
        "recommended_action": "For accurate assessment, ensure GEMINI_API_KEY is configured.",
        "details": [
            f"Pallor indicator: {pallor:.1f}/10",
            f"Motion/restlessness: {motion_distress:.1f}/10",
            "Note: Set GEMINI_API_KEY for AI-powered visual triage",
        ],
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def assess_visual_distress(video_path: str) -> dict:
    """Run visual distress assessment on a video.

    Primary: Gemini Vision API (if GEMINI_API_KEY is set)
    Fallback: OpenCV heuristic analysis (if no API key)

    Called by the Triage Decision Agent when rPPG SQI drops below
    the confidence threshold.

    Returns:
        dict with visual_stress_score (0-10), visual_stress_level,
        indicators, overall_assessment, and recommended_action.
    """
    api_key = _get_api_key()

    if api_key:
        logger.info("Visual Assessment: Using Gemini Vision API")
        try:
            # Extract best face frame
            frame = _extract_face_frame(video_path)
            if frame is None:
                logger.warning("Could not extract face frame, falling back to heuristics")
                return _heuristic_assessment(video_path)

            # Encode and send to Gemini
            frame_b64 = _frame_to_base64(frame)
            gemini_result = _call_gemini_vision(frame_b64, api_key)

            # Normalize score to 0-10
            score = float(gemini_result.get("visual_stress_score", 5))
            score = max(0, min(10, score))
            confidence = float(gemini_result.get("confidence", 0.7))

            level = "HIGH" if score >= 6 else "MODERATE" if score >= 3.5 else "LOW"

            # Build details list from indicators
            details = []
            indicators = gemini_result.get("indicators", {})
            for key in ["pallor", "sweating", "cyanosis", "breathing", "facial_distress"]:
                ind = indicators.get(key, {})
                if ind.get("description"):
                    details.append(f"{key.replace('_', ' ').title()}: {ind['description']}")

            result = {
                "visual_stress_score": round(score, 1),
                "visual_stress_level": level,
                "confidence": round(confidence, 3),
                "analysis_method": "gemini_vision",
                "indicators": indicators,
                "overall_assessment": gemini_result.get("overall_assessment", ""),
                "recommended_action": gemini_result.get("recommended_action", ""),
                "wellness_tips": gemini_result.get("wellness_tips", []),
                "urgency": gemini_result.get("urgency", level),
                "estimated_heart_rate_range": gemini_result.get("estimated_heart_rate_range", ""),
                "details": details,
            }

            logger.info("Gemini Visual Assessment: score=%.1f, level=%s, confidence=%.2f",
                        score, level, confidence)
            return result

        except Exception as e:
            logger.error("Gemini Vision failed: %s — falling back to heuristics", e)
            result = _heuristic_assessment(video_path)
            result["details"].append(f"Gemini API error: {e}")
            return result
    else:
        logger.info("Visual Assessment: No GEMINI_API_KEY — using OpenCV heuristics")
        return _heuristic_assessment(video_path)


def _default_response(reason: str) -> dict:
    """Return a safe default when assessment can't run."""
    return {
        "visual_stress_score": 5.0,
        "visual_stress_level": "UNKNOWN",
        "confidence": 0.1,
        "analysis_method": "none",
        "indicators": {
            "pallor": {"score": 5, "description": reason},
            "sweating": {"score": 5, "description": reason},
            "cyanosis": {"score": 5, "description": reason},
            "breathing": {"score": 5, "description": reason},
            "facial_distress": {"score": 5, "description": reason},
        },
        "overall_assessment": reason,
        "recommended_action": "Retry with better lighting and less movement",
        "details": [reason],
    }
