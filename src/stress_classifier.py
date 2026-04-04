# src/app/stress_classifier.py

import logging
from typing import List, Tuple

import joblib
import numpy as np
import pandas as pd

from src.models import HRVResult

logger = logging.getLogger(__name__)

LABEL_MAP = {0: "LOW", 1: "MODERATE", 2: "HIGH"}


# ✅ RULE-BASED (FOR TESTS — DO NOT REMOVE)
def classify_stress(hrv: HRVResult) -> Tuple[str, float, List[str]]:
    """
    Rule-based stress classifier (used by tests)
    """

    score = 0

    if hrv.rmssd < 25:
        score += 1
    if hrv.sdnn < 50:
        score += 1
    if hrv.pnn50 < 10:
        score += 1
    if hrv.mean_hr > 90:
        score += 1
    if hrv.lf_hf_ratio and hrv.lf_hf_ratio > 2:
        score += 1

    if score >= 3:
        level = "HIGH"
    elif score == 2:
        level = "MODERATE"
    else:
        level = "LOW"

    confidence = min(1.0, 0.5 + score * 0.1)

    warnings: List[str] = []
    if len(hrv.ibi_ms) < 10:
        confidence *= 0.85
        warnings.append("Limited data - stress estimate may be unreliable.")

    return level, round(confidence, 3), warnings


# ✅ ML-BASED (YOUR NEW FEATURE)
def classify_stress_ml(
    hrv: HRVResult,
    model_path: str = "models/stress_classifier.pkl"
) -> Tuple[str, float, List[str]]:
    """
    ML-based stress classification (fallback-safe)
    """

    try:
        print("🔥 USING ML MODEL 🔥")

        model = joblib.load(model_path)

        features = pd.DataFrame([{
            'hr': hrv.mean_hr,
            'rmssd': hrv.rmssd,
            'pnn50': hrv.pnn50,
            'lf': 0,
            'hf': 0,
            'lf_hf': hrv.lf_hf_ratio if hrv.lf_hf_ratio else 1.5,
            'tp': 0,
            'sdrr': hrv.sdnn
        }])

        proba = model.predict_proba(features)[0]
        pred = int(np.argmax(proba))
        confidence = float(np.max(proba))

        warnings: List[str] = []

        if len(hrv.ibi_ms) < 10:
            confidence *= 0.85
            warnings.append("Limited data - stress estimate may be unreliable.")

        level = LABEL_MAP[pred]

        logger.info("ML Stress: %s (confidence=%.3f)", level, confidence)

        return level, round(confidence, 3), warnings

    except Exception as e:
        logger.warning("ML failed, falling back to rule-based: %s", e)

        # 🔥 IMPORTANT: fallback to rule-based
        return classify_stress(hrv)
