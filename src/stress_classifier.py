# src/app/stress_classifier.py

import logging
from typing import List, Tuple

import joblib
import numpy as np
import pandas as pd  # ✅ added

from src.models import HRVResult

logger = logging.getLogger(__name__)

LABEL_MAP = {0: "LOW", 1: "MODERATE", 2: "HIGH"}

def classify_stress(hrv: HRVResult) -> Tuple[str, float, List[str]]:
    """
    ML-based stress classification (primary and only method)
    """

    try:
        print("🔥 USING ML MODEL 🔥")

        model = joblib.load("models/stress_classifier.pkl")

        # ✅ FIX: use DataFrame with feature names (IMPORTANT)
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
        logger.error("ML stress classification failed: %s", e)
        return "UNKNOWN", 0.0, ["Model error"]
