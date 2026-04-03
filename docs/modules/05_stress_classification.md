# Module 5: Stress Classification

Owner: P3 (Backend Lead)

## Purpose

Classify the subject's cardiac stress level as Low, Moderate, or High based
on the HRV feature vector. Uses a rule-based scoring system as the primary
method, with an optional machine learning classifier as a secondary path.

## Inputs and Outputs

**Input:** `HRVResult` from the HRV analysis module.

**Output:** A tuple of `(stress_level, confidence)`:
- `stress_level`: one of "LOW", "MODERATE", "HIGH"
- `confidence`: float between 0.0 and 1.0

## Dependencies

- `numpy` (only)
- `scikit-learn` + `joblib` (optional, only if ML classifier is implemented)

## Implementation Guide

### Primary: Rule-Based Classifier

The rule-based system scores stress using thresholds derived from clinical
HRV literature. Each metric contributes points to a cumulative stress score.

```python
def classify_stress(hrv):
    """Classify cardiac stress from HRV features.

    Scoring is based on established clinical thresholds:
    - Low RMSSD indicates reduced parasympathetic activity (stress)
    - High LF/HF ratio indicates sympathetic dominance (stress)
    - Low SDNN indicates reduced cardiac adaptability (stress)
    - High pNN50 indicates good parasympathetic tone (anti-stress)

    Args:
        hrv: HRVResult instance

    Returns:
        (level, confidence) tuple
    """
    score = 0

    # RMSSD scoring (most sensitive short-term stress indicator)
    if hrv.rmssd < 20:
        score += 3
    elif hrv.rmssd < 35:
        score += 2
    elif hrv.rmssd < 50:
        score += 1

    # LF/HF ratio scoring (sympathovagal balance)
    if hrv.lf_hf_ratio is not None:
        if hrv.lf_hf_ratio > 4.0:
            score += 3
        elif hrv.lf_hf_ratio > 2.0:
            score += 2
        elif hrv.lf_hf_ratio > 1.0:
            score += 1

    # SDNN scoring (overall variability)
    if hrv.sdnn < 30:
        score += 2
    elif hrv.sdnn < 50:
        score += 1

    # pNN50 scoring (parasympathetic indicator, inverted)
    if hrv.pnn50 > 20:
        score -= 1

    # Mean HR as secondary indicator
    if hrv.mean_hr > 100:
        score += 1
    elif hrv.mean_hr > 85:
        score += 0.5

    # Classification
    if score >= 6:
        level = "HIGH"
        confidence = min(score / 9.0, 1.0)
    elif score >= 3:
        level = "MODERATE"
        confidence = 0.4 + (score - 3) / 10.0
    else:
        level = "LOW"
        confidence = max(0.5, 1.0 - score / 6.0)

    return level, round(float(confidence), 3)
```

### Threshold Reference

| Metric | Low Stress | Moderate Stress | High Stress |
|--------|-----------|-----------------|-------------|
| RMSSD (ms) | > 50 | 20 - 50 | < 20 |
| SDNN (ms) | > 50 | 30 - 50 | < 30 |
| LF/HF | < 1.0 | 1.0 - 4.0 | > 4.0 |
| pNN50 (%) | > 20 | 5 - 20 | < 5 |
| Mean HR | < 75 | 75 - 100 | > 100 |

These thresholds are intentionally conservative for a resting measurement.

### Optional: ML Classifier

If time allows and the rule-based system needs improvement, a lightweight
Random Forest can be trained on the WESAD dataset features:

1. Extract HRV features from WESAD ground truth
2. Train a 5-feature Random Forest (RMSSD, SDNN, pNN50, LF/HF, mean_HR)
3. Serialize with joblib
4. Load at inference time and use as secondary opinion

```python
import joblib
import numpy as np

def classify_stress_ml(hrv, model_path="models/stress_rf.joblib"):
    """ML-based stress classification (optional secondary classifier)."""
    try:
        model = joblib.load(model_path)
        features = np.array([[
            hrv.rmssd, hrv.sdnn, hrv.pnn50,
            hrv.lf_hf_ratio or 1.5,  # fallback if LF/HF unavailable
            hrv.mean_hr,
        ]])
        prediction = model.predict(features)[0]
        probabilities = model.predict_proba(features)[0]
        confidence = float(max(probabilities))

        label_map = {0: "LOW", 1: "MODERATE", 2: "HIGH"}
        return label_map.get(prediction, "MODERATE"), confidence
    except FileNotFoundError:
        # Fall back to rules if model file is missing
        return classify_stress(hrv)
```

Only implement this if the rule-based system is working and tested first.

### Edge Cases

- **LF/HF is None**: frequency analysis can fail with very short or noisy data.
  The classifier should work with time-domain features alone. In score
  calculation, simply skip the LF/HF contribution.
- **Very few IBIs**: if HRVResult has fewer than 10 IBIs, confidence should
  be reduced and a warning added: "Limited data - stress estimate may be
  unreliable."
- **All metrics normal**: should produce LOW stress with moderate confidence.
  Do not output 100% confidence since 30 seconds is too short for a definitive
  assessment.

## Testing

```bash
pytest tests/unit/test_stress_classifier.py -v
```

Key validations:
- Known relaxed profile -> LOW
- Known stressed profile -> HIGH
- Intermediate profile -> MODERATE
- Confidence is always in [0.0, 1.0]
- Handles None LF/HF ratio without crashing
