// TODO: Implement Results Screen
// See docs/app/04_results_dashboard.md for full implementation guide
//
// Displays:
//   - BPM (large number) + SQI badge
//   - BVP waveform chart
//   - HRV metrics grid (RMSSD, SDNN, pNN50, LF/HF, Mean HR)
//   - Stress indicator (LOW/MODERATE/HIGH with color)
//   - AI Insights card (from Gemini)
//   - Warnings (if any)

import React from 'react';
import { ScrollView, View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../theme/colors';

export default function ResultsScreen({ route }) {
  const { result } = route.params;

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <Text style={styles.bpm}>
        {result.bpm != null ? Math.round(result.bpm) : '--'} BPM
      </Text>
      <Text style={styles.sqi}>
        SQI: {result.sqi_level} ({Math.round(result.sqi_score * 100)}%)
      </Text>
      <Text style={styles.stress}>
        Stress: {result.stress_level}
      </Text>
      {/* TODO: Add WaveformChart, HRVMetricsGrid, StressIndicator,
               AIInsightsCard components from docs/app/04_results_dashboard.md */}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll:  { flex: 1, backgroundColor: COLORS.background },
  content: { padding: 24, alignItems: 'center' },
  bpm:     { fontSize: 56, fontWeight: '700', color: COLORS.textPrimary },
  sqi:     { fontSize: 14, color: COLORS.textSecondary, marginTop: 4 },
  stress:  { fontSize: 20, fontWeight: '600', color: COLORS.accent, marginTop: 16 },
});
