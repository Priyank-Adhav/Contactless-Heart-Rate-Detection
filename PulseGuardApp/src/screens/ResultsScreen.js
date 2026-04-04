import React, { useEffect } from 'react';
import {
  ScrollView, View, Text, Dimensions, StyleSheet,
  TouchableOpacity, SafeAreaView, StatusBar, Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LineChart } from 'react-native-chart-kit';
import { colors } from '../theme/colors';
import { computeTriage } from '../services/triage';

const W = Dimensions.get('window').width;

export default function ResultsScreen({ navigation, route }) {
  const result = route.params?.result;
  const mode = route.params?.mode || 'wellness';

  // Save to history
  useEffect(() => {
    if (!result || result.fromHome) return;
    const save = async () => {
      try {
        const raw = await AsyncStorage.getItem('pulseguard_history');
        const history = raw ? JSON.parse(raw) : [];
        history.unshift({
          result,
          time: new Date().toLocaleString(),
        });
        // Keep last 20
        await AsyncStorage.setItem('pulseguard_history', JSON.stringify(history.slice(0, 20)));
      } catch {}
    };
    save();
  }, [result]);

  // Empty state
  if (!result || result.fromHome) {
    return (
      <SafeAreaView style={styles.emptyScreen}>
        <View style={styles.blobG} />
        <View style={styles.blobP} />
        <Text style={styles.emptyTitle}>No Results Yet</Text>
        <Text style={styles.emptyDesc}>Complete a face scan, finger scan, or upload a video.</Text>
        <TouchableOpacity style={styles.goBtn} onPress={() => navigation.navigate('Home')} activeOpacity={0.85}>
          <Text style={styles.goBtnText}>Start a Scan</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  const isVisualMode = result.active_mode === 'visual_assessment';
  const triage = computeTriage(result);
  const triageColor = triage.level === 'CRITICAL' ? colors.statusRed
    : triage.level === 'ELEVATED' ? colors.statusYellow : colors.statusGreen;
  const triageBg = triage.level === 'CRITICAL' ? colors.statusRedBg
    : triage.level === 'ELEVATED' ? colors.statusYellowBg : colors.statusGreenBg;
  const sqiColor = result.sqi_level === 'HIGH' ? colors.statusGreen
    : result.sqi_level === 'MEDIUM' ? colors.statusYellow : colors.statusRed;

  // Waveform sampling
  const wave = result.bvp_waveform || [];
  const step = Math.max(1, Math.floor(wave.length / 80));
  const sampled = wave.filter((_, i) => i % step === 0);

  const visual = result.visual_assessment;

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.gradientStart} />
      <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
        <View style={styles.blobGS} />
        <View style={styles.blobPS} />

        {/* Mode Banner — TWIST 1 */}
        <View style={[styles.modeBanner, {
          backgroundColor: isVisualMode ? 'rgba(126,87,194,0.08)' : 'rgba(46,125,50,0.06)',
          borderColor: isVisualMode ? colors.borderPurple : colors.borderGreen,
        }]}>
          <View style={[styles.modeDot, {
            backgroundColor: isVisualMode ? colors.modeVisual : colors.modeBiometric,
          }]} />
          <View style={styles.modeBannerBody}>
            <Text style={[styles.modeLabel, {
              color: isVisualMode ? colors.modeVisual : colors.modeBiometric,
            }]}>
              {isVisualMode ? 'Visual Assessment Mode' : 'Biometric Mode'}
            </Text>
            <Text style={styles.modeReason}>{result.mode_reason || ''}</Text>
          </View>
        </View>

        {/* Triage Banner */}
        <View style={[styles.triageBanner, { backgroundColor: triageBg, borderColor: triageColor + '30' }]}>
          <View style={styles.triageHeader}>
            <View style={[styles.triageDot, { backgroundColor: triageColor }]} />
            <Text style={[styles.triageLevel, { color: triageColor }]}>{triage.level}</Text>
          </View>
          <Text style={[styles.triageAction, { color: triageColor }]}>{triage.action}</Text>
          {triage.details.map((d, i) => (
            <Text key={i} style={styles.triageDetail}>- {d}</Text>
          ))}
          {mode === 'emergency' && triage.level === 'CRITICAL' && (
            <View style={[styles.alertBox, { backgroundColor: colors.statusRedBg, borderColor: colors.statusRed + '20' }]}>
              <Text style={[styles.alertText, { color: colors.statusRed }]}>
                Recommend immediate medical evaluation
              </Text>
            </View>
          )}
        </View>

        {/* BPM Card — only in biometric mode */}
        {!isVisualMode && (
          <View style={styles.bpmCard}>
            <Text style={styles.bpmValue}>
              {result.bpm != null ? Math.round(result.bpm) : '--'}
            </Text>
            <Text style={styles.bpmLabel}>BPM</Text>
            <View style={styles.sqiRow}>
              <View style={[styles.sqiDot, { backgroundColor: sqiColor }]} />
              <Text style={styles.sqiText}>Signal: {result.sqi_level} ({Math.round((result.sqi_score || 0) * 100)}%)</Text>
            </View>
          </View>
        )}

        {/* Visual Assessment Card — TWIST 1 (Gemini Vision) */}
        {isVisualMode && visual && (
          <View style={styles.visualCard}>
            <View style={styles.visualHeader}>
              <Text style={styles.sectionTitle}>VISUAL DISTRESS ANALYSIS</Text>
              <View style={styles.methodBadge}>
                <Text style={styles.methodText}>
                  {visual.analysis_method === 'gemini_vision' ? 'Gemini AI' : 'Heuristic'}
                </Text>
              </View>
            </View>

            {/* Score + Urgency Row */}
            <View style={styles.visualScoreRow}>
              <View style={styles.visualScore}>
                <Text style={styles.visualScoreNum}>
                  {visual.visual_stress_score || 0}
                </Text>
                <Text style={styles.visualScoreLabel}>/ 10</Text>
              </View>
              {visual.urgency && (
                <View style={[styles.urgencyBadge, {
                  backgroundColor: visual.urgency === 'CRITICAL' || visual.urgency === 'HIGH'
                    ? colors.statusRedBg : visual.urgency === 'MODERATE'
                    ? colors.statusYellowBg : colors.statusGreenBg,
                }]}>
                  <Text style={[styles.urgencyText, {
                    color: visual.urgency === 'CRITICAL' || visual.urgency === 'HIGH'
                      ? colors.statusRed : visual.urgency === 'MODERATE'
                      ? colors.statusYellow : colors.statusGreen,
                  }]}>{visual.urgency}</Text>
                </View>
              )}
            </View>

            {/* Estimated HR */}
            {visual.estimated_heart_rate_range ? (
              <View style={styles.estHrBox}>
                <Text style={styles.estHrLabel}>Estimated Heart Rate</Text>
                <Text style={styles.estHrValue}>{visual.estimated_heart_rate_range}</Text>
              </View>
            ) : null}

            {/* Overall Assessment */}
            {visual.overall_assessment ? (
              <Text style={styles.visualAssessment}>{visual.overall_assessment}</Text>
            ) : null}

            {/* Recommendation */}
            {visual.recommended_action ? (
              <View style={styles.vmRecommend}>
                <Text style={styles.vmRecommendLabel}>Recommendation</Text>
                <Text style={styles.vmRecommendText}>{visual.recommended_action}</Text>
              </View>
            ) : null}

            {/* 5 Clinical Indicators */}
            <Text style={[styles.sectionTitle, { marginTop: 8 }]}>CLINICAL INDICATORS</Text>
            <View style={styles.visualGrid}>
              {['pallor', 'sweating', 'cyanosis', 'breathing', 'facial_distress'].map(key => {
                const ind = visual.indicators?.[key];
                if (!ind) return null;
                const label = key.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
                return (
                  <VisualIndicator key={key} label={label} score={ind.score}
                    description={ind.description} />
                );
              })}
            </View>

            {/* Wellness Tips */}
            {visual.wellness_tips && visual.wellness_tips.length > 0 && (
              <View style={styles.tipsSection}>
                <Text style={[styles.sectionTitle, { marginBottom: 8 }]}>WELLNESS RECOMMENDATIONS</Text>
                {visual.wellness_tips.map((tip, i) => (
                  <View key={i} style={styles.tipRow}>
                    <View style={styles.tipBullet} />
                    <Text style={styles.tipText}>{tip}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Waveform */}
        {!isVisualMode && sampled.length > 5 && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>BVP WAVEFORM</Text>
            <LineChart
              data={{ datasets: [{ data: sampled }] }}
              width={W - 80}
              height={120}
              withDots={false}
              withInnerLines={false}
              withOuterLines={false}
              withHorizontalLabels={false}
              withVerticalLabels={false}
              chartConfig={{
                backgroundColor: 'transparent',
                backgroundGradientFrom: '#fff',
                backgroundGradientTo: '#fff',
                decimalPlaces: 0,
                color: () => result.sqi_level === 'LOW' ? colors.statusRed : colors.green,
                propsForBackgroundLines: { stroke: 'transparent' },
              }}
              bezier
              style={{ borderRadius: 8, marginLeft: -16 }}
            />
          </View>
        )}

        {/* HRV Grid */}
        {!isVisualMode && result.hrv && (
          <>
            <Text style={styles.sectionTitle}>HRV METRICS</Text>
            <View style={styles.grid}>
              <MetricCard label="RMSSD" value={result.hrv.rmssd} unit="ms" />
              <MetricCard label="SDNN" value={result.hrv.sdnn} unit="ms" />
              <MetricCard label="pNN50" value={result.hrv.pnn50} unit="%" />
              <MetricCard label="LF / HF" value={result.hrv.lf_hf_ratio} unit="" />
              <MetricCard label="Mean HR" value={result.hrv.mean_hr} unit="BPM" />
            </View>
          </>
        )}

        {!isVisualMode && !result.hrv && (
          <View style={styles.card}>
            <Text style={styles.noData}>HRV data not available — signal quality may be insufficient</Text>
          </View>
        )}

        {/* Stress */}
        <StressCard level={result.stress_level} confidence={result.stress_confidence} />

        <Text style={styles.meta}>
          Processed in {((result.processing_time_ms || 0) / 1000).toFixed(1)} seconds
        </Text>

        <TouchableOpacity style={styles.newScanBtn} onPress={() => navigation.navigate('Home')} activeOpacity={0.85}>
          <Text style={styles.newScanText}>New Scan</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

// --- Sub-components ---

function MetricCard({ label, value, unit }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>
        {value != null ? (typeof value === 'number' ? value.toFixed(1) : value) : '--'}
      </Text>
      {unit ? <Text style={styles.metricUnit}>{unit}</Text> : null}
    </View>
  );
}

function VisualIndicator({ label, score, description }) {
  const s = score || 0;
  const barColor = s >= 6 ? colors.statusRed : s >= 3.5 ? colors.statusYellow : colors.statusGreen;
  return (
    <View style={styles.visualMetric}>
      <View style={styles.vmRow}>
        <Text style={styles.vmLabel}>{label}</Text>
        <Text style={[styles.vmScore, { color: barColor }]}>{s}/10</Text>
      </View>
      <View style={styles.vmBar}>
        <View style={[styles.vmBarFill, {
          width: `${Math.round(s * 10)}%`,
          backgroundColor: barColor,
        }]} />
      </View>
      <Text style={styles.vmDetail}>{description}</Text>
    </View>
  );
}

function StressCard({ level, confidence }) {
  const map = {
    LOW: { color: colors.statusGreen, bg: colors.statusGreenBg, label: 'Low Stress' },
    MODERATE: { color: colors.statusYellow, bg: colors.statusYellowBg, label: 'Moderate Stress' },
    HIGH: { color: colors.statusRed, bg: colors.statusRedBg, label: 'High Stress' },
    UNKNOWN: { color: colors.textMuted, bg: 'rgba(160,160,176,0.06)', label: 'Unknown' },
  };
  const s = map[level] || map.UNKNOWN;
  return (
    <View style={[styles.stressCard, { backgroundColor: s.bg, borderColor: s.color + '25' }]}>
      <View style={[styles.stressDot, { backgroundColor: s.color }]} />
      <Text style={[styles.stressLevel, { color: s.color }]}>{s.label}</Text>
      <Text style={styles.stressConf}>Confidence: {Math.round((confidence || 0) * 100)}%</Text>
    </View>
  );
}

// --- Styles ---

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.gradientStart },
  scroll: { flex: 1 },
  content: { padding: 20, paddingBottom: 48 },

  emptyScreen: { flex: 1, backgroundColor: colors.gradientStart, justifyContent: 'center',
    alignItems: 'center', padding: 32, overflow: 'hidden' },
  emptyTitle: { fontSize: 24, fontWeight: '800', color: colors.textPrimary, marginBottom: 8 },
  emptyDesc: { fontSize: 14, color: colors.textSecondary, textAlign: 'center', marginBottom: 24 },
  goBtn: { backgroundColor: colors.green, paddingVertical: 14, paddingHorizontal: 48, borderRadius: 16 },
  goBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },

  blobG: { position: 'absolute', top: -80, right: -80, width: 260, height: 260, borderRadius: 130, backgroundColor: colors.greenLight },
  blobP: { position: 'absolute', bottom: 120, left: -100, width: 300, height: 300, borderRadius: 150, backgroundColor: colors.purpleLight },
  blobGS: { position: 'absolute', top: -40, right: -40, width: 140, height: 140, borderRadius: 70, backgroundColor: colors.greenLight, opacity: 0.5 },
  blobPS: { position: 'absolute', bottom: 200, left: -60, width: 160, height: 160, borderRadius: 80, backgroundColor: colors.purpleLight, opacity: 0.4 },

  // Mode banner
  modeBanner: { flexDirection: 'row', alignItems: 'center', borderRadius: 14, borderWidth: 1.5,
    padding: 14, marginBottom: 12 },
  modeDot: { width: 10, height: 10, borderRadius: 5, marginRight: 12 },
  modeBannerBody: { flex: 1 },
  modeLabel: { fontSize: 14, fontWeight: '700' },
  modeReason: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },

  // Triage
  triageBanner: { borderRadius: 18, borderWidth: 1.5, padding: 18, marginBottom: 14 },
  triageHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  triageDot: { width: 12, height: 12, borderRadius: 6, marginRight: 10 },
  triageLevel: { fontSize: 20, fontWeight: '800', letterSpacing: 0.5 },
  triageAction: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  triageDetail: { fontSize: 13, color: colors.textSecondary, marginBottom: 2, paddingLeft: 4 },
  alertBox: { marginTop: 10, borderRadius: 10, borderWidth: 1, padding: 12 },
  alertText: { fontSize: 13, fontWeight: '500' },

  // BPM
  bpmCard: { backgroundColor: colors.white, borderRadius: 20, borderWidth: 1, borderColor: colors.border,
    padding: 28, alignItems: 'center', marginBottom: 14,
    ...Platform.select({ ios: { shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 4 } }) },
  bpmValue: { fontSize: 60, fontWeight: '800', color: colors.textPrimary, letterSpacing: -2 },
  bpmLabel: { fontSize: 14, fontWeight: '600', color: colors.textMuted, marginTop: -4 },
  sqiRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  sqiDot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  sqiText: { fontSize: 12, color: colors.textSecondary },

  // Visual assessment
  visualCard: { backgroundColor: colors.white, borderRadius: 18, borderWidth: 1.5,
    borderColor: colors.borderPurple, padding: 20, marginBottom: 14,
    ...Platform.select({ ios: { shadowColor: colors.purple, shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 4 } }) },
  visualHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  methodBadge: { backgroundColor: 'rgba(126,87,194,0.1)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  methodText: { fontSize: 10, fontWeight: '700', color: colors.purple, letterSpacing: 0.3 },
  visualScoreRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginBottom: 12 },
  visualScore: { alignItems: 'center' },
  visualScoreNum: { fontSize: 52, fontWeight: '800', color: colors.purple },
  visualScoreLabel: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
  urgencyBadge: { marginLeft: 16, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 12 },
  urgencyText: { fontSize: 13, fontWeight: '800', letterSpacing: 0.5 },
  estHrBox: { backgroundColor: 'rgba(126,87,194,0.05)', borderRadius: 12, padding: 12, marginBottom: 12,
    alignItems: 'center', borderWidth: 1, borderColor: colors.borderPurple },
  estHrLabel: { fontSize: 10, fontWeight: '600', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  estHrValue: { fontSize: 20, fontWeight: '800', color: colors.purple, marginTop: 2 },
  visualAssessment: { fontSize: 13, color: colors.textPrimary, textAlign: 'center',
    lineHeight: 20, marginBottom: 12, fontStyle: 'italic', paddingHorizontal: 4 },
  vmRecommend: { backgroundColor: 'rgba(46,125,50,0.06)', borderRadius: 12,
    padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.borderGreen },
  vmRecommendLabel: { fontSize: 10, fontWeight: '700', color: colors.green, textTransform: 'uppercase',
    letterSpacing: 0.5, marginBottom: 4 },
  vmRecommendText: { fontSize: 13, color: colors.green, fontWeight: '500', lineHeight: 19 },
  visualGrid: {},
  visualMetric: { marginBottom: 12 },
  vmRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  vmLabel: { fontSize: 13, fontWeight: '700', color: colors.textPrimary },
  vmScore: { fontSize: 12, fontWeight: '700' },
  vmBar: { height: 6, borderRadius: 3, backgroundColor: 'rgba(0,0,0,0.06)', marginBottom: 4, overflow: 'hidden' },
  vmBarFill: { height: 6, borderRadius: 3 },
  vmDetail: { fontSize: 11, color: colors.textSecondary, lineHeight: 16 },
  tipsSection: { marginTop: 8, backgroundColor: 'rgba(46,125,50,0.03)', borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: colors.borderGreen },
  tipRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 8 },
  tipBullet: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.green, marginRight: 10, marginTop: 5 },
  tipText: { flex: 1, fontSize: 12, color: colors.textPrimary, lineHeight: 17 },

  // Cards
  card: { backgroundColor: colors.white, borderRadius: 16, borderWidth: 1, borderColor: colors.border,
    padding: 18, marginBottom: 14,
    ...Platform.select({ ios: { shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 10, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 } }) },
  sectionTitle: { fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'uppercase',
    letterSpacing: 1.2, marginBottom: 10 },
  noData: { color: colors.textMuted, textAlign: 'center', fontSize: 13 },

  // HRV Grid
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginBottom: 14 },
  metricCard: { width: '48%', backgroundColor: colors.white, borderRadius: 16, borderWidth: 1,
    borderColor: colors.border, padding: 18, marginBottom: 10, alignItems: 'center',
    ...Platform.select({ ios: { shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 } }) },
  metricLabel: { fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'uppercase',
    letterSpacing: 0.5, marginBottom: 6 },
  metricValue: { fontSize: 26, fontWeight: '800', color: colors.textPrimary },
  metricUnit: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },

  // Stress
  stressCard: { borderRadius: 16, borderWidth: 1, padding: 22, alignItems: 'center', marginBottom: 14 },
  stressDot: { width: 14, height: 14, borderRadius: 7, marginBottom: 6 },
  stressLevel: { fontSize: 22, fontWeight: '700' },
  stressConf: { fontSize: 12, color: colors.textSecondary, marginTop: 4 },

  // Warnings
  warnBox: { backgroundColor: colors.statusYellowBg, borderRadius: 14, borderWidth: 1,
    borderColor: colors.statusYellow + '25', padding: 16, marginBottom: 14 },
  warnTitle: { fontSize: 12, fontWeight: '700', color: colors.statusYellow, marginBottom: 6,
    textTransform: 'uppercase', letterSpacing: 0.5 },
  warnText: { color: colors.textSecondary, fontSize: 13, marginBottom: 3, lineHeight: 18 },

  meta: { color: colors.textMuted, textAlign: 'center', fontSize: 11, marginBottom: 16 },
  newScanBtn: { backgroundColor: colors.green, borderRadius: 18, paddingVertical: 16, alignItems: 'center',
    shadowColor: colors.green, shadowOpacity: 0.25, shadowRadius: 10, elevation: 5 },
  newScanText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});