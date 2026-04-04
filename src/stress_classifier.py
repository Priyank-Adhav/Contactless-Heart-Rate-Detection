"""
Stress Classification Module

Classifies cardiac stress level (Low, Moderate, High) from HRV
features using a rule-based scoring system. An optional secondary
classifier trained on labeled data can override the rule-based
output when available.

Scoring system (points accumulate → higher = more stressed):
    RMSSD  : 0–3 pts  (low RMSSD = parasympathetic shutdown)
    LF/HF  : 0–3 pts  (high ratio = sympathetic dominance)
    SDNN   : 0–2 pts  (low SDNN = reduced cardiac adaptability)
    pNN50  : −1 pt    (high pNN50 = good parasympathetic tone)
    Mean HR: 0–1 pt   (elevated HR = secondary stress indicator)

    Total max ≈ 9.5 pts
    LOW < 3 ≤ MODERATE < 6 ≤ HIGH

See docs/modules/05_stress_classification.md for implementation details.
"""

import logging
from typing import List, Tuple

from src.models import HRVResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primary: Rule-based stress classifier
# ---------------------------------------------------------------------------

def classify_stress(hrv: HRVResult) -> Tuple[str, float, List[str]]:
    """Classify cardiac stress from HRV features using rule-based scoring.

    Each HRV metric is compared against clinical thresholds derived from
    published HRV literature.  Points accumulate into a stress score:

        Score < 3   → LOW stress
        Score 3–5.9 → MODERATE stress
        Score ≥ 6   → HIGH stress

    Args:
        hrv: HRVResult instance from the HRV analysis module.

    Returns:
        A 3-tuple of (stress_level, confidence, warnings):
            - stress_level: "LOW", "MODERATE", or "HIGH"
            - confidence:   float between 0.0 and 1.0
            - warnings:     list of warning strings (empty if none)
    """
    score = 0.0
    warnings: List[str] = []

    # ── RMSSD scoring (most sensitive short-term stress indicator) ──
    # Low RMSSD means the heart isn't varying beat-to-beat → parasympathetic
    # nervous system is suppressed → body is in "fight or flight" mode.
    if hrv.rmssd < 20:
        score += 3
    elif hrv.rmssd < 35:
        score += 2
    elif hrv.rmssd < 50:
        score += 1
    # ≥ 50 ms: healthy, no points added

    logger.debug("After RMSSD (%.1f ms): score = %.1f", hrv.rmssd, score)

    # ── LF/HF ratio scoring (sympathovagal balance) ──
    # High LF/HF means the sympathetic ("stress") branch of the nervous
    # system is dominating over the parasympathetic ("relax") branch.
    # Skip entirely if frequency analysis failed (lf_hf_ratio is None).
    if hrv.lf_hf_ratio is not None:
        if hrv.lf_hf_ratio > 4.0:
            score += 3
        elif hrv.lf_hf_ratio > 2.0:
            score += 2
        elif hrv.lf_hf_ratio > 1.0:
            score += 1
        logger.debug("After LF/HF (%.2f): score = %.1f", hrv.lf_hf_ratio, score)
    else:
        logger.debug("LF/HF is None, skipping frequency-domain scoring")

    # ── SDNN scoring (overall variability) ──
    # Low SDNN means the heart rate is very "rigid" — reduced ability to
    # adapt to changing demands.
    if hrv.sdnn < 30:
        score += 2
    elif hrv.sdnn < 50:
        score += 1

    logger.debug("After SDNN (%.1f ms): score = %.1f", hrv.sdnn, score)

    # ── pNN50 scoring (parasympathetic indicator — inverted) ──
    # High pNN50 is actually a GOOD sign — it means the parasympathetic
    # system is active, so we SUBTRACT points (anti-stress).
    if hrv.pnn50 > 20:
        score -= 1

    logger.debug("After pNN50 (%.1f%%): score = %.1f", hrv.pnn50, score)

    # ── Mean HR as secondary indicator ──
    # Elevated resting heart rate is a secondary stress marker.
    if hrv.mean_hr > 100:
        score += 1
    elif hrv.mean_hr > 85:
        score += 0.5

    logger.debug("After Mean HR (%.1f BPM): score = %.1f", hrv.mean_hr, score)

    # ── Classification: map score to stress level ──
    if score >= 6:
        level = "HIGH"
        # Confidence scales with severity, max out at 1.0
        confidence = min(score / 9.0, 1.0)
    elif score >= 3:
        level = "MODERATE"
        # Moderate confidence: 0.4 base + scales slightly with score
        confidence = 0.4 + (score - 3) / 10.0
    else:
        level = "LOW"
        # For low stress, confidence is higher when score is lower
        confidence = max(0.5, 1.0 - score / 6.0)

    # Clamp confidence to [0.0, 1.0] before any adjustments
    confidence = max(0.0, min(confidence, 1.0))

    # ── Edge case: limited data reduces confidence ──
    if len(hrv.ibi_ms) < 10:
        confidence *= 0.85  # reduce by 15%
        # warnings.append("Limited data - stress estimate may be unreliable.")
        logger.info("Short IBI array (%d values), reducing confidence", len(hrv.ibi_ms))

    confidence = round(float(confidence), 3)

    logger.info(
        "Stress classification: %s (confidence=%.3f, score=%.1f) from "
        "RMSSD=%.1f, SDNN=%.1f, pNN50=%.1f, LF/HF=%s, HR=%.1f",
        level, confidence, score,
        hrv.rmssd, hrv.sdnn, hrv.pnn50,
        f"{hrv.lf_hf_ratio:.2f}" if hrv.lf_hf_ratio is not None else "N/A",
        hrv.mean_hr,
    )

    return level, confidence, warnings


# ---------------------------------------------------------------------------
# Optional: ML-based stress classifier (secondary path)
# ---------------------------------------------------------------------------

def classify_stress_ml(
    hrv: HRVResult,
    model_path: str = "models/stress_rf.joblib",
) -> Tuple[str, float, List[str]]:
    """ML-based stress classification using a pre-trained Random Forest.

    This is an optional secondary classifier. If the model file exists,
    it predicts stress from a 5-feature vector [RMSSD, SDNN, pNN50,
    LF/HF, Mean HR]. If the model file is missing or loading fails,
    it silently falls back to the rule-based classifier.

    Args:
        hrv: HRVResult instance from the HRV analysis module.
        model_path: Path to the serialized scikit-learn model (.joblib).

    Returns:
        Same 3-tuple as classify_stress: (level, confidence, warnings).
    """
    try:
        import joblib
        import numpy as np

        model = joblib.load(model_path)

        features = np.array([[
            hrv.rmssd,
            hrv.sdnn,
            hrv.pnn50,
            hrv.lf_hf_ratio if hrv.lf_hf_ratio is not None else 1.5,
            hrv.mean_hr,
        ]])

        prediction = model.predict(features)[0]
        probabilities = model.predict_proba(features)[0]
        confidence = float(max(probabilities))

        label_map = {0: "LOW", 1: "MODERATE", 2: "HIGH"}
        level = label_map.get(prediction, "MODERATE")

        warnings: List[str] = []
        if len(hrv.ibi_ms) < 10:
            confidence *= 0.85
            # warnings.append("Limited data - stress estimate may be unreliable.")

        logger.info("ML classifier: %s (confidence=%.3f)", level, confidence)
        return level, round(confidence, 3), warnings

    except FileNotFoundError:
        logger.info("Model file not found at '%s', falling back to rules", model_path)
        return classify_stress(hrv)
    except Exception as e:
        logger.warning("ML classifier failed (%s), falling back to rules", e)
        return classify_stress(hrv)
