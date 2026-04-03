# App Module 7: Triage System & User Modes

Owner: P2 (Signal Lead)

## Purpose

Implement the **Smart Triage System** — a color-coded urgency indicator that
combines all vital signs into a single at-a-glance assessment. Also implement
dual user modes that adapt the UI and actions based on the use case.

## 🚦 Triage System

### The Concept

Instead of showing raw numbers that users might not understand, the triage
system gives an **instant, actionable verdict**:

```
🔴 CRITICAL — Immediate attention needed
   "Your vitals show significant cardiac stress. Please rest immediately
    and seek medical attention if symptoms persist."

🟡 ELEVATED — Monitor closely  
   "Some indicators are outside normal range. Take a break,
    practice deep breathing, and re-check in 15 minutes."

🟢 STABLE — All vitals normal
   "Your cardiac health looks great! All measurements are within
    healthy ranges."
```

### Triage Logic

The triage level is computed from the **combined analysis results** — not just
stress level alone. It considers the full picture:

```
CRITICAL (🔴) — any of:
  • Heart rate > 120 BPM (tachycardia)
  • Heart rate < 45 BPM (severe bradycardia)
  • Stress = HIGH  AND  HR > 100
  • RMSSD < 12 ms (severe parasympathetic shutdown)

ELEVATED (🟡) — any of:
  • Stress = MODERATE
  • Stress = HIGH (but HR normal)
  • HR > 100 BPM (elevated)
  • HR < 50 BPM (bradycardia)
  • RMSSD < 20 ms
  • LF/HF > 4.0 (sympathetic overdrive)

STABLE (🟢) — all of:
  • Stress = LOW
  • 50 ≤ HR ≤ 100
  • RMSSD ≥ 20 ms
  • No warning flags
```

### Implementation

#### `src/services/triage.js`

```javascript
/**
 * Smart Triage System
 *
 * Combines all vital signs into a single triage level:
 *   🔴 CRITICAL — immediate attention
 *   🟡 ELEVATED — monitor closely
 *   🟢 STABLE   — all clear
 *
 * @param {object} result - API analysis result
 * @returns {object} { level, emoji, action, details[] }
 */
export function computeTriage(result) {
  const { bpm, stress_level, stress_confidence, hrv, sqi_level } = result;
  const details = [];

  // ── Signal quality check ──
  if (sqi_level === 'LOW') {
    return {
      level: 'UNKNOWN',
      emoji: '⚪',
      action: 'Signal quality too low for reliable assessment',
      details: ['Re-record with better lighting and hold still'],
    };
  }

  const rmssd = hrv?.rmssd;
  const lfhf = hrv?.lf_hf_ratio;

  // ══════════════════════════════
  //  🔴 CRITICAL — any one trigger
  // ══════════════════════════════
  if (bpm > 120) {
    details.push(`Heart rate dangerously high: ${bpm} BPM`);
  }
  if (bpm && bpm < 45) {
    details.push(`Heart rate dangerously low: ${bpm} BPM`);
  }
  if (stress_level === 'HIGH' && bpm > 100) {
    details.push('High stress combined with elevated heart rate');
  }
  if (rmssd != null && rmssd < 12) {
    details.push(`Severe HRV depression: RMSSD ${rmssd.toFixed(1)} ms`);
  }

  if (details.length > 0) {
    return {
      level: 'CRITICAL',
      emoji: '🔴',
      action: 'Immediate attention needed',
      details,
    };
  }

  // ══════════════════════════════
  //  🟡 ELEVATED — any one trigger
  // ══════════════════════════════
  if (stress_level === 'MODERATE') {
    details.push('Moderate stress detected');
  }
  if (stress_level === 'HIGH') {
    details.push('High stress detected');
  }
  if (bpm > 100) {
    details.push(`Elevated heart rate: ${bpm} BPM`);
  }
  if (bpm && bpm < 50) {
    details.push(`Low heart rate: ${bpm} BPM`);
  }
  if (rmssd != null && rmssd < 20) {
    details.push(`Low HRV: RMSSD ${rmssd.toFixed(1)} ms`);
  }
  if (lfhf != null && lfhf > 4.0) {
    details.push(`Sympathetic overdrive: LF/HF ${lfhf.toFixed(1)}`);
  }

  if (details.length > 0) {
    return {
      level: 'ELEVATED',
      emoji: '🟡',
      action: 'Monitor closely',
      details,
    };
  }

  // ══════════════════════════════
  //  🟢 STABLE
  // ══════════════════════════════
  return {
    level: 'STABLE',
    emoji: '🟢',
    action: 'All vitals normal',
    details: ['Heart rate, HRV, and stress levels are within healthy ranges'],
  };
}
```

### Triage UI Component

#### `src/components/TriageBanner.js`

```javascript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { TRIAGE } from '../theme/colors';

export default function TriageBanner({ triage, mode }) {
  const style = TRIAGE[triage.level] || TRIAGE.STABLE;

  return (
    <View style={[styles.banner, { backgroundColor: style.bg,
      borderColor: style.border }]}>

      {/* Triage header */}
      <View style={styles.headerRow}>
        <Text style={styles.emoji}>{triage.emoji}</Text>
        <Text style={[styles.level, { color: style.color }]}>
          {triage.level}
        </Text>
      </View>

      {/* Action text */}
      <Text style={[styles.action, { color: style.color }]}>
        {triage.action}
      </Text>

      {/* Details */}
      {triage.details?.map((d, i) => (
        <Text key={i} style={styles.detail}>• {d}</Text>
      ))}

      {/* Emergency mode: extra actions */}
      {mode === 'emergency' && triage.level === 'CRITICAL' && (
        <View style={styles.emergencyBox}>
          <Text style={styles.emergencyText}>
            🚑 Recommend immediate medical evaluation
          </Text>
          <Text style={styles.emergencyText}>
            📞 If experiencing chest pain, call emergency services
          </Text>
        </View>
      )}

      {/* Wellness mode: gentler suggestions */}
      {mode === 'wellness' && triage.level === 'ELEVATED' && (
        <View style={styles.wellnessBox}>
          <Text style={styles.wellnessText}>
            💆 Try a 2-minute breathing exercise
          </Text>
          <Text style={styles.wellnessText}>
            🔄 Re-check in 15 minutes after resting
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { borderRadius: 16, borderWidth: 1.5, padding: 20, marginBottom: 14 },
  headerRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  emoji: { fontSize: 28, marginRight: 10 },
  level: { fontSize: 22, fontWeight: '800', letterSpacing: 1 },
  action: { fontSize: 15, fontWeight: '600', marginBottom: 10 },
  detail: { fontSize: 13, color: '#b0b0b0', marginBottom: 3, paddingLeft: 4 },
  emergencyBox: { marginTop: 12, backgroundColor: 'rgba(239,68,68,0.15)',
    borderRadius: 10, padding: 12 },
  emergencyText: { fontSize: 13, color: '#fca5a5', marginBottom: 4,
    fontWeight: '500' },
  wellnessBox: { marginTop: 12, backgroundColor: 'rgba(108,156,252,0.1)',
    borderRadius: 10, padding: 12 },
  wellnessText: { fontSize: 13, color: '#93c5fd', marginBottom: 4 },
});
```

## 👤 User Modes

### Wellness Mode (Default)

For daily users doing routine stress monitoring.

**UI shows:**
- Full HRV metrics grid with explanations
- Stress level with confidence
- AI Insights card with wellness suggestions
- Trend tracking ("Compare with yesterday")
- Breathing exercise recommendation if elevated

**Triage behavior:**
- 🟢 "Great job! Your cardiac health is on track."
- 🟡 "Take a short break. Try the breathing exercise below."
- 🔴 "Your vitals are concerning. Rest and monitor. Consider consulting a doctor."

### Emergency Mode

For paramedics, disaster response, or anyone doing rapid triage.

**UI shows:**
- **LARGE** triage banner (🔴🟡🟢) — the first and most prominent element
- BPM in giant font
- Minimal HRV (just RMSSD — the most clinically relevant metric)
- Clear action statements
- Timestamp for documentation

**Triage behavior:**
- 🟢 "STABLE — Patient vitals within normal limits"
- 🟡 "ELEVATED — Continue monitoring, reassess in 15 min"
- 🔴 "CRITICAL — Immediate medical evaluation recommended. If chest pain present, activate EMS."

### How Mode Affects ResultsScreen

```javascript
// ResultsScreen.js — mode-adaptive rendering
const { mode } = route.params;

if (mode === 'emergency') {
  // Show: Giant triage banner → BPM → RMSSD only → action items
  return <EmergencyResultsView result={result} triage={triage} />;
} else {
  // Show: Triage banner → BPM → Full HRV grid → Stress → AI Insights
  return <WellnessResultsView result={result} triage={triage} />;
}
```

## Integration into ResultsScreen

Add to `ResultsScreen.js` (after imports):

```javascript
import TriageBanner from '../components/TriageBanner';
import { computeTriage } from '../services/triage';

// In the component:
const triage = computeTriage(result);
const { mode } = route.params || { mode: 'wellness' };

// In JSX (place FIRST, before everything else):
<TriageBanner triage={triage} mode={mode} />
```

## Testing Checklist

- [ ] Triage shows 🟢 STABLE for BPM=72, Stress=LOW, RMSSD=50
- [ ] Triage shows 🟡 ELEVATED for BPM=105, Stress=MODERATE
- [ ] Triage shows 🔴 CRITICAL for BPM=130, Stress=HIGH
- [ ] Emergency mode shows larger triage + emergency actions
- [ ] Wellness mode shows gentler suggestions
- [ ] Mode toggles on HomeScreen correctly pass to ResultsScreen
- [ ] Edge case: SQI=LOW shows "UNKNOWN" triage with re-record suggestion
