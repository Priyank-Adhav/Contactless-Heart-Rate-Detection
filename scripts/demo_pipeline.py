#!/usr/bin/env python3
"""
PulseGuard Pipeline Demo Script
================================
Demonstrates the complete backend flow using synthetic data:

    Signal Processing (02) → HRV Analysis (04) → Stress Classification (05)

Run this script to see exactly what each module does, with real numbers
and step-by-step explanations. Perfect for understanding the pipeline
and explaining it to teammates.

Usage:
    python scripts/demo_pipeline.py
"""

import sys
sys.path.insert(0, ".")  # ensure project root is on path

import numpy as np

# ═══════════════════════════════════════════════════════════════════════
#  PART 1: SIGNAL PROCESSING  (Module 02)
#  Goal: Extract a heartbeat waveform from raw skin-color data
# ═══════════════════════════════════════════════════════════════════════

print("=" * 70)
print("  PART 1: SIGNAL PROCESSING (Module 02)")
print("  Goal: Raw skin-color data → Heartbeat waveform + BPM")
print("=" * 70)

from src.signal_processor import (
    bandpass_filter,
    pos_algorithm,
    chrom_algorithm,
    extract_bpm,
    detect_peaks,
    _green_to_synthetic_rgb,
)
from src.ensemble import fuse_signals
from src.sqi_engine import compute_sqi

# --- Simulate what the camera sees ---
fps = 30        # 30 frames per second
duration = 30   # 30 seconds of video
N = fps * duration  # 900 frames total
t = np.linspace(0, duration, N, endpoint=False)

# The "true" heart rate: 72 BPM = 1.2 Hz
true_bpm = 72
true_freq = true_bpm / 60.0  # 1.2 Hz

# Simulate green channel from face (baseline ~140 + tiny cardiac pulse)
cardiac_pulse = 0.5 * np.sin(2 * np.pi * true_freq * t)
noise = 0.2 * np.random.randn(N)  # camera/motion noise
green_signal = 140.0 + cardiac_pulse + noise

print(f"\n📹 Simulated video: {duration}s at {fps} fps = {N} frames")
print(f"💓 True heart rate:  {true_bpm} BPM ({true_freq} Hz)")
print(f"📊 Green channel:    baseline=140, cardiac amplitude=0.5, noise=0.2")

# Step 1: Bandpass filter
from scipy.signal import detrend
detrended = detrend(green_signal, type='linear')
filtered = bandpass_filter(detrended, fps, low=0.7, high=3.5)
print(f"\n🔧 Step 1 - Bandpass filter [0.7-3.5 Hz]:")
print(f"   Removed DC offset, breathing (< 0.7 Hz), and noise (> 3.5 Hz)")
print(f"   Signal power before: {np.std(detrended):.4f}")
print(f"   Signal power after:  {np.std(filtered):.4f}")

# Step 2: Build synthetic RGB and run POS + CHROM
rgb = _green_to_synthetic_rgb(filtered)
pos_pulse = pos_algorithm(rgb, fps)
chrom_pulse = chrom_algorithm(rgb, fps)

print(f"\n🧬 Step 2 - rPPG algorithms:")
print(f"   POS  pulse std: {np.std(pos_pulse):.6f}")
print(f"   CHROM pulse std: {np.std(chrom_pulse):.6f}")

# Step 3: Score quality
pos_sqi, pos_level, _ = compute_sqi(bandpass_filter(pos_pulse, fps), fps)
chrom_sqi, chrom_level, _ = compute_sqi(bandpass_filter(chrom_pulse, fps), fps)
print(f"\n📏 Step 3 - Signal Quality (SQI):")
print(f"   POS  SQI: {pos_sqi:.3f} ({pos_level})")
print(f"   CHROM SQI: {chrom_sqi:.3f} ({chrom_level})")

# Step 4: Fuse signals
candidates = [bandpass_filter(pos_pulse, fps), bandpass_filter(chrom_pulse, fps)]
sqi_scores = [pos_sqi, chrom_sqi]
fused = fuse_signals(candidates, sqi_scores)
fused = bandpass_filter(fused, fps)

print(f"\n🔀 Step 4 - Ensemble Fusion:")
print(f"   Weights: POS={pos_sqi:.3f}, CHROM={chrom_sqi:.3f}")
print(f"   Fused signal std: {np.std(fused):.6f}")

# Step 5: Extract BPM
estimated_bpm = extract_bpm(fused, fps)
print(f"\n📈 Step 5 - FFT → BPM:")
print(f"   Estimated BPM: {estimated_bpm}")
print(f"   True BPM:      {true_bpm}")
print(f"   Error:         {abs(estimated_bpm - true_bpm):.1f} BPM ✅" if estimated_bpm else "   Could not estimate BPM ❌")

# Step 6: Peak detection
peaks = detect_peaks(fused, fps)
print(f"\n🔍 Step 6 - Peak Detection:")
print(f"   Found {len(peaks)} heartbeat peaks in {duration}s")
print(f"   Expected ~{int(true_bpm * duration / 60)} peaks")

# ═══════════════════════════════════════════════════════════════════════
#  PART 2: HRV ANALYSIS  (Module 04)
#  Goal: Convert peaks → Inter-Beat Intervals → HRV metrics
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  PART 2: HRV ANALYSIS (Module 04)")
print("  Goal: Peak positions → IBI → RMSSD, SDNN, pNN50, LF/HF, Mean HR")
print("=" * 70)

from src.hrv_analyzer import compute_ibi, clean_ibi, compute_time_domain, compute_frequency_domain, compute_hrv

# Full pipeline
hrv_result = compute_hrv(peaks, fps)

if hrv_result:
    print(f"\n📐 IBI Conversion:")
    print(f"   {len(peaks)} peaks → {len(hrv_result.ibi_ms)} inter-beat intervals")
    print(f"   Mean IBI: {np.mean(hrv_result.ibi_ms):.1f} ms")
    print(f"   → Mean HR: {hrv_result.mean_hr} BPM")

    print(f"\n📊 Time-Domain HRV Metrics:")
    print(f"   RMSSD  = {hrv_result.rmssd:.2f} ms   (beat-to-beat variability)")
    print(f"   SDNN   = {hrv_result.sdnn:.2f} ms   (overall variability)")
    print(f"   pNN50  = {hrv_result.pnn50:.2f}%    (frequency of big timing jumps)")

    print(f"\n🌊 Frequency-Domain HRV Metrics:")
    if hrv_result.lf_hf_ratio is not None:
        print(f"   LF/HF  = {hrv_result.lf_hf_ratio:.2f}     (stress/relaxation balance)")
        if hrv_result.lf_hf_ratio > 2.0:
            print(f"   → Sympathetic dominance (stress indicator)")
        else:
            print(f"   → Balanced or parasympathetic leaning (relaxed)")
    else:
        print(f"   LF/HF  = N/A (insufficient data for frequency analysis)")

    print(f"\n📋 Normal Ranges Reference:")
    print(f"   {'Metric':<10} {'Value':>8} {'Normal Range':>15} {'Status':>10}")
    print(f"   {'─'*10} {'─'*8} {'─'*15} {'─'*10}")

    def check_range(val, low, high):
        return "✅ Normal" if low <= val <= high else "⚠️ Outside"

    print(f"   {'RMSSD':<10} {hrv_result.rmssd:>7.1f}  {'19-75 ms':>15} {check_range(hrv_result.rmssd, 19, 75):>10}")
    print(f"   {'SDNN':<10} {hrv_result.sdnn:>7.1f}  {'30-100 ms':>15} {check_range(hrv_result.sdnn, 30, 100):>10}")
    print(f"   {'pNN50':<10} {hrv_result.pnn50:>7.1f}  {'1-50%':>15} {check_range(hrv_result.pnn50, 1, 50):>10}")
    print(f"   {'Mean HR':<10} {hrv_result.mean_hr:>7.1f}  {'50-100 BPM':>15} {check_range(hrv_result.mean_hr, 50, 100):>10}")
else:
    print("\n⚠️ HRV analysis returned None (insufficient peaks)")

# ═══════════════════════════════════════════════════════════════════════
#  PART 3: STRESS CLASSIFICATION  (Module 05)
#  Goal: HRV metrics → Stress level (LOW / MODERATE / HIGH)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  PART 3: STRESS CLASSIFICATION (Module 05)")
print("  Goal: HRV metrics → Score → LOW / MODERATE / HIGH stress")
print("=" * 70)

from src.stress_classifier import classify_stress

if hrv_result:
    level, confidence, warnings = classify_stress(hrv_result)

    print(f"\n📋 Scoring Breakdown:")
    score = 0

    # RMSSD
    if hrv_result.rmssd < 20:
        pts = 3
    elif hrv_result.rmssd < 35:
        pts = 2
    elif hrv_result.rmssd < 50:
        pts = 1
    else:
        pts = 0
    score += pts
    print(f"   RMSSD = {hrv_result.rmssd:.1f} ms  → +{pts} pts  (< 20: +3, < 35: +2, < 50: +1)")

    # LF/HF
    if hrv_result.lf_hf_ratio is not None:
        if hrv_result.lf_hf_ratio > 4.0:
            pts = 3
        elif hrv_result.lf_hf_ratio > 2.0:
            pts = 2
        elif hrv_result.lf_hf_ratio > 1.0:
            pts = 1
        else:
            pts = 0
        score += pts
        print(f"   LF/HF = {hrv_result.lf_hf_ratio:.2f}     → +{pts} pts  (> 4: +3, > 2: +2, > 1: +1)")
    else:
        print(f"   LF/HF = N/A       → +0 pts  (skipped)")

    # SDNN
    if hrv_result.sdnn < 30:
        pts = 2
    elif hrv_result.sdnn < 50:
        pts = 1
    else:
        pts = 0
    score += pts
    print(f"   SDNN  = {hrv_result.sdnn:.1f} ms  → +{pts} pts  (< 30: +2, < 50: +1)")

    # pNN50
    if hrv_result.pnn50 > 20:
        pts = -1
    else:
        pts = 0
    score += pts
    print(f"   pNN50 = {hrv_result.pnn50:.1f}%    → {'+' if pts >= 0 else ''}{pts} pts  (> 20%: -1, anti-stress)")

    # Mean HR
    if hrv_result.mean_hr > 100:
        pts = 1
    elif hrv_result.mean_hr > 85:
        pts = 0.5
    else:
        pts = 0
    score += pts
    print(f"   HR    = {hrv_result.mean_hr:.1f} BPM → +{pts} pts  (> 100: +1, > 85: +0.5)")

    print(f"\n   {'─' * 40}")
    print(f"   Total Score = {score}")
    print(f"   Classification: score < 3 → LOW, 3-5.9 → MODERATE, ≥ 6 → HIGH")

    print(f"\n🎯 RESULT:")
    emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🔴"}
    print(f"   {emoji.get(level, '⚪')} Stress Level: {level}")
    print(f"   📊 Confidence:   {confidence:.1%}")
    if warnings:
        for w in warnings:
            print(f"   ⚠️  {w}")
else:
    print("\n⚠️ Cannot classify stress — HRV analysis failed")

# ═══════════════════════════════════════════════════════════════════════
#  PART 4: COMPARISON — RESTING vs STRESSED
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  PART 4: SIDE-BY-SIDE COMPARISON  (Resting vs Stressed)")
print("=" * 70)

from src.models import HRVResult

# Pre-built profiles
resting = HRVResult(rmssd=55.0, sdnn=60.0, pnn50=25.0, lf_hf_ratio=0.8, mean_hr=65.0,
                    ibi_ms=[923.0] * 30)
stressed = HRVResult(rmssd=15.0, sdnn=25.0, pnn50=3.0, lf_hf_ratio=5.0, mean_hr=98.0,
                     ibi_ms=[612.0] * 40)

r_level, r_conf, r_warn = classify_stress(resting)
s_level, s_conf, s_warn = classify_stress(stressed)

print(f"\n   {'Metric':<12} {'Resting':>10} {'Stressed':>10} {'What it means':>30}")
print(f"   {'─'*12} {'─'*10} {'─'*10} {'─'*30}")
print(f"   {'RMSSD':<12} {'55.0 ms':>10} {'15.0 ms':>10} {'Beat-to-beat variability':>30}")
print(f"   {'SDNN':<12} {'60.0 ms':>10} {'25.0 ms':>10} {'Overall timing spread':>30}")
print(f"   {'pNN50':<12} {'25.0%':>10} {'3.0%':>10} {'Big timing jump frequency':>30}")
print(f"   {'LF/HF':<12} {'0.80':>10} {'5.00':>10} {'Stress/relax balance':>30}")
print(f"   {'Mean HR':<12} {'65 BPM':>10} {'98 BPM':>10} {'Average heart rate':>30}")
print(f"   {'─'*12} {'─'*10} {'─'*10} {'─'*30}")
print(f"   {'RESULT':<12} {'🟢 '+r_level:>10} {'🔴 '+s_level:>10}")
print(f"   {'Confidence':<12} {r_conf:>9.0%} {s_conf:>9.0%}")

print(f"""
{'=' * 70}
  SUMMARY: What the project does
{'=' * 70}

  PulseGuard detects heart rate and stress from a CAMERA — no wearable needed!

  📹 Camera → 🧑 Face Detection → 🎨 Skin Color Changes (rPPG)
      → 💓 Heartbeat Waveform → 📊 HRV Metrics → 🎯 Stress Level

  Three modules you implemented:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Signal Processor (02)                                        │
  │  • Removes noise with bandpass filter (keeps 42-210 BPM)      │
  │  • Runs POS + CHROM algorithms to extract pulse from color    │
  │  • Fuses 6 candidates with quality-weighted averaging         │
  │  • Extracts BPM via FFT, detects peaks for IBI                │
  ├─────────────────────────────────────────────────────────────────┤
  │  HRV Analyzer (04)                                            │
  │  • Converts peak positions → inter-beat intervals (IBI in ms) │
  │  • Removes bad IBIs (< 300ms or > 1500ms)                     │
  │  • Computes RMSSD, SDNN, pNN50 (time-domain)                  │
  │  • Computes LF/HF ratio via Lomb-Scargle (frequency-domain)   │
  ├─────────────────────────────────────────────────────────────────┤
  │  Stress Classifier (05)                                       │
  │  • Scores each metric against clinical thresholds              │
  │  • Maps total score → LOW / MODERATE / HIGH                   │
  │  • Handles edge cases: None LF/HF, short data, confidence cap │
  └─────────────────────────────────────────────────────────────────┘
""")
