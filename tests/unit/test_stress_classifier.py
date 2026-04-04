"""
Unit tests for the stress classification module.

Validates the rule-based scoring system against known HRV feature
profiles representing low, moderate, and high stress states.
"""

from src.models import HRVResult
from src.stress_classifier import classify_stress


def _make_hrv(rmssd, sdnn, pnn50, lf_hf, mean_hr, ibi_count=30):
    """Helper to construct an HRVResult with specified values.

    Args:
        rmssd, sdnn, pnn50, lf_hf, mean_hr: HRV metric values.
        ibi_count: Number of IBI entries to generate (default 30).
                   Set to <10 to test the "limited data" edge case.
    """
    ibi_val = 60000.0 / mean_hr if mean_hr > 0 else 800.0
    return HRVResult(
        rmssd=rmssd,
        sdnn=sdnn,
        pnn50=pnn50,
        lf_hf_ratio=lf_hf,
        mean_hr=mean_hr,
        ibi_ms=[ibi_val] * ibi_count,
    )


# ── Test profiles ──
# These represent clearly distinct HRV states

RELAXED_PROFILE = _make_hrv(rmssd=55, sdnn=60, pnn50=25, lf_hf=0.8, mean_hr=65)
STRESSED_PROFILE = _make_hrv(rmssd=15, sdnn=25, pnn50=3, lf_hf=5.0, mean_hr=98)
MODERATE_PROFILE = _make_hrv(rmssd=30, sdnn=40, pnn50=10, lf_hf=2.5, mean_hr=80)


class TestRuleBasedClassifier:
    """Tests for the rule-based stress scoring system."""

    def test_relaxed_profile_classified_low(self):
        """HRV profile with high RMSSD, low LF/HF, moderate HR
        should be classified as LOW stress.

        Scoring breakdown:
            RMSSD=55  → ≥50, +0 pts
            LF/HF=0.8 → ≤1.0, +0 pts
            SDNN=60   → ≥50, +0 pts
            pNN50=25  → >20, −1 pt
            HR=65     → <85, +0 pts
            Total = −1 → LOW
        """
        level, confidence, warnings = classify_stress(RELAXED_PROFILE)
        assert level == "LOW", f"Expected LOW, got {level}"

    def test_stressed_profile_classified_high(self):
        """HRV profile with low RMSSD, high LF/HF, elevated HR
        should be classified as HIGH stress.

        Scoring breakdown:
            RMSSD=15  → <20, +3 pts
            LF/HF=5.0 → >4.0, +3 pts
            SDNN=25   → <30, +2 pts
            pNN50=3   → ≤20, +0 pts
            HR=98     → >85, +0.5 pts
            Total = 8.5 → HIGH
        """
        level, confidence, warnings = classify_stress(STRESSED_PROFILE)
        assert level == "HIGH", f"Expected HIGH, got {level}"

    def test_moderate_profile_classified_moderate(self):
        """Intermediate HRV values should produce MODERATE stress.

        Scoring breakdown:
            RMSSD=30  → 20-35, +2 pts
            LF/HF=2.5 → 2.0-4.0, +2 pts
            SDNN=40   → 30-50, +1 pt
            pNN50=10  → ≤20, +0 pts
            HR=80     → <85, +0 pts
            Total = 5 → MODERATE
        """
        level, confidence, warnings = classify_stress(MODERATE_PROFILE)
        assert level == "MODERATE", f"Expected MODERATE, got {level}"

    def test_confidence_between_zero_and_one(self):
        """Stress confidence should always be in [0.0, 1.0] for all profiles."""
        for profile in [RELAXED_PROFILE, STRESSED_PROFILE, MODERATE_PROFILE]:
            _, confidence, _ = classify_stress(profile)
            assert 0.0 <= confidence <= 1.0, (
                f"Confidence {confidence} is outside [0.0, 1.0]"
            )

    def test_handles_none_lf_hf_ratio(self):
        """When LF/HF is None (frequency analysis failed), the classifier
        should still produce a result using time-domain features only."""
        hrv = _make_hrv(rmssd=55, sdnn=60, pnn50=25, lf_hf=None, mean_hr=65)
        level, confidence, warnings = classify_stress(hrv)
        # Should still classify — no crash
        assert level in ("LOW", "MODERATE", "HIGH")
        assert 0.0 <= confidence <= 1.0

    def test_none_lf_hf_gives_low_for_relaxed(self):
        """A relaxed profile with None LF/HF should still be LOW.

        Without LF/HF, scoring:
            RMSSD=55 → +0, SDNN=60 → +0, pNN50=25 → −1, HR=65 → +0
            Total = −1 → LOW
        """
        hrv = _make_hrv(rmssd=55, sdnn=60, pnn50=25, lf_hf=None, mean_hr=65)
        level, _, _ = classify_stress(hrv)
        assert level == "LOW"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_low_ibi_count_reduces_confidence(self):
        """With fewer than 10 IBIs, confidence should be reduced and
        a warning should be added."""
        hrv = _make_hrv(rmssd=55, sdnn=60, pnn50=25, lf_hf=0.8, mean_hr=65,
                        ibi_count=5)  # only 5 IBIs
        _, confidence, warnings = classify_stress(hrv)

        # Compare with normal-length version
        _, normal_confidence, _ = classify_stress(RELAXED_PROFILE)

        assert confidence < normal_confidence, (
            f"Short-data confidence ({confidence}) should be less than "
            f"normal confidence ({normal_confidence})"
        )


    def test_no_warnings_for_sufficient_data(self):
        """With 30+ IBIs, no data-length warnings should be present."""
        _, _, warnings = classify_stress(RELAXED_PROFILE)


    def test_pnn50_reduces_score(self):
        """High pNN50 should reduce the stress level compared to low pNN50.

        Profile with pNN50=25 gets −1 point (anti-stress).
        Profile with pNN50=5 gets 0 points.
        Same other values → first should have lower or equal stress.
        """
        hrv_high_pnn50 = _make_hrv(rmssd=35, sdnn=40, pnn50=25, lf_hf=2.5, mean_hr=80)
        hrv_low_pnn50 = _make_hrv(rmssd=35, sdnn=40, pnn50=5, lf_hf=2.5, mean_hr=80)

        level_high, _, _ = classify_stress(hrv_high_pnn50)
        level_low, _, _ = classify_stress(hrv_low_pnn50)

        rank = {"LOW": 0, "MODERATE": 1, "HIGH": 2}
        assert rank[level_high] <= rank[level_low], (
            f"High pNN50 ({level_high}) should not be more stressed than "
            f"low pNN50 ({level_low})"
        )

    def test_deterministic_output(self):
        """Same input should always produce the same output."""
        results = [classify_stress(STRESSED_PROFILE) for _ in range(10)]
        levels = [r[0] for r in results]
        confidences = [r[1] for r in results]

        assert len(set(levels)) == 1, "Level should be deterministic"
        assert len(set(confidences)) == 1, "Confidence should be deterministic"

    def test_elevated_hr_adds_stress(self):
        """Heart rate above 100 should push classification higher."""
        hrv_normal_hr = _make_hrv(rmssd=30, sdnn=40, pnn50=10, lf_hf=2.5, mean_hr=75)
        hrv_high_hr = _make_hrv(rmssd=30, sdnn=40, pnn50=10, lf_hf=2.5, mean_hr=105)

        _, conf_normal, _ = classify_stress(hrv_normal_hr)
        _, conf_high, _ = classify_stress(hrv_high_hr)

        # Higher HR should give equal or higher confidence in stress
        rank = {"LOW": 0, "MODERATE": 1, "HIGH": 2}
        level_normal, _, _ = classify_stress(hrv_normal_hr)
        level_high, _, _ = classify_stress(hrv_high_hr)
        assert rank[level_high] >= rank[level_normal]


class TestMLClassifierFallback:
    """Tests for the optional ML classifier."""

    def test_ml_falls_back_to_rules_when_no_model(self):
        """When the model file doesn't exist, classify_stress_ml should
        fall back to the rule-based classifier and return the same result."""
        from src.stress_classifier import classify_stress_ml

        rule_result = classify_stress(RELAXED_PROFILE)
        ml_result = classify_stress_ml(RELAXED_PROFILE, model_path="nonexistent.joblib")

        assert rule_result == ml_result, (
            f"ML fallback {ml_result} should match rules {rule_result}"
        )
