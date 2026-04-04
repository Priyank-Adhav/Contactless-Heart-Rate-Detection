import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Alert, Vibration,
  ActivityIndicator, SafeAreaView, StatusBar, Animated, Platform,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { colors } from '../theme/colors';
import { analyzeVideo } from '../services/api';

export default function CameraScreen({ navigation, route }) {
  const mode = route.params?.mode || 'wellness';
  const forceVisual = route.params?.forceVisual || false;

  // Visual mode needs only 10s, biometric needs 15s
  const DURATION = forceVisual ? 10 : 15;

  const [permission, requestPermission] = useCameraPermissions();
  const [recording, setRecording] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [seconds, setSeconds] = useState(DURATION);
  const [faceStatus, setFaceStatus] = useState('searching'); // 'searching' | 'detected' | 'lost'
  const camRef = useRef(null);
  const timerRef = useRef(null);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const faceAlertShown = useRef(false);

  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.15, duration: 600, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
      ])
    );
    pulse.start();
    return () => { pulse.stop(); clearInterval(timerRef.current); };
  }, []);

  // Haptic feedback on face detection status change
  useEffect(() => {
    if (faceStatus === 'detected') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } else if (faceStatus === 'lost' && recording) {
      // Much more aggressive haptic and vibration setting
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Vibration.vibrate([0, 400, 200, 400, 200, 400]); // triple heavy buzz
    }
  }, [faceStatus, recording]);

  if (!permission) return <View style={styles.center} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permScreen}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.permCard}>
          <View style={[styles.permIcon, { backgroundColor: forceVisual ? colors.purpleLight : colors.greenLight }]}>
            <Text style={[styles.permIconText, { color: forceVisual ? colors.purple : colors.green }]}>
              {forceVisual ? 'V' : 'C'}
            </Text>
          </View>
          <Text style={styles.permTitle}>Camera Access</Text>
          <Text style={styles.permDesc}>
            {forceVisual
              ? 'Gemini AI needs a face video to analyze physical distress indicators.'
              : 'PulseGuard detects your heart rate by analyzing subtle skin color changes.'}
          </Text>
          <TouchableOpacity style={[styles.permBtn, { backgroundColor: forceVisual ? colors.purple : colors.green }]}
            onPress={requestPermission} activeOpacity={0.85}>
            <Text style={styles.permBtnText}>Allow Camera</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const start = async () => {
    if (!camRef.current) return;
    setRecording(true);
    setSeconds(DURATION);
    setFaceStatus('searching');
    faceAlertShown.current = false;

    // Haptic on start
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    timerRef.current = setInterval(() => {
      setSeconds(prev => {
        if (prev <= 1) { clearInterval(timerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);

    try {
      const video = await camRef.current.recordAsync({ maxDuration: DURATION, quality: '720p' });
      setRecording(false);
      clearInterval(timerRef.current);
      setAnalyzing(true);

      // Haptic feedback — recording done
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

      // Send with forceVisual flag
      const result = await analyzeVideo(video.uri, forceVisual);
      setAnalyzing(false);
      navigation.replace('Results', { result, mode });
    } catch (err) {
      setRecording(false);
      setAnalyzing(false);
      clearInterval(timerRef.current);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert('Error', err.message || 'Recording failed. Check backend is running.');
    }
  };

  const stop = () => camRef.current?.stopRecording();

  // Handle face detection events from camera
  const handleFacesDetected = ({ faces }) => {
    if (!recording) return;

    if (faces && faces.length > 0) {
      if (faceStatus !== 'detected') {
        setFaceStatus('detected');
      }
      faceAlertShown.current = false;
    } else {
      if (faceStatus === 'detected') {
        setFaceStatus('lost');
        if (!faceAlertShown.current) {
          faceAlertShown.current = true;
          // Don't show blocking alert — just update UI indicator
        }
      }
    }
  };

  // Analyzing screen
  if (analyzing) {
    return (
      <SafeAreaView style={[styles.analyzeScreen, forceVisual && { backgroundColor: colors.gradientEnd }]}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.blobG} />
        <View style={styles.blobP} />
        <ActivityIndicator size="large" color={forceVisual ? colors.purple : colors.green} />
        <Text style={styles.analyzeTitle}>
          {forceVisual ? 'VLM Analysis processing...' : 'Analyzing...'}
        </Text>
        <Text style={styles.analyzeDesc}>
          {forceVisual
            ? 'Analyzing facial indicators: pallor, sweating, cyanosis, breathing, distress'
            : 'ROI extraction → Signal processing → HRV analysis → Stress classification'}
        </Text>
      </SafeAreaView>
    );
  }

  // Face status indicator color
  const faceColor = faceStatus === 'detected' ? '#4CAF50'
    : faceStatus === 'lost' ? '#e53935' : '#FF9800';
  const faceMsg = faceStatus === 'detected' ? 'Face detected'
    : faceStatus === 'lost' ? 'Face lost! Stay in frame'
    : 'Searching for face...';

  return (
    <View style={styles.container}>
      {/* Mode pill at top */}
      {forceVisual && (
        <View style={styles.visualBadge}>
          <Text style={styles.visualBadgeText}>Visual Assessment Mode</Text>
        </View>
      )}
      <CameraView ref={camRef} style={styles.camera} facing="front" mode="video">
        {!recording && (
          <View style={styles.guideOverlay}>
            <View style={[styles.faceGuide, forceVisual && { borderColor: 'rgba(126,87,194,0.6)' }]} />
            <Text style={styles.guideText}>Position your face in the oval</Text>
            {forceVisual && (
              <Text style={styles.guideSub}>Gemini AI will analyze physical stress indicators</Text>
            )}
          </View>
        )}
        {recording && (
          <View style={styles.recordOverlay}>
            {/* Face status indicator */}
            <View style={[styles.faceStatusBar, { backgroundColor: faceColor + '20', borderColor: faceColor + '40' }]}>
              <View style={[styles.faceStatusDot, { backgroundColor: faceColor }]} />
              <Text style={[styles.faceStatusText, { color: faceColor }]}>{faceMsg}</Text>
            </View>

            <View style={styles.timerBox}>
              <Animated.View style={[styles.timerPulse, {
                transform: [{ scale: pulseAnim }],
                backgroundColor: forceVisual ? 'rgba(126,87,194,0.3)' : 'rgba(67,160,71,0.3)',
              }]} />
              <Text style={styles.timerNum}>{seconds}</Text>
            </View>
            <Text style={styles.recHint}>
              {forceVisual ? 'Hold still — capturing face for AI analysis' : 'Hold still — detecting skin color changes'}
            </Text>

            {/* Alert when face lost */}
            {faceStatus === 'lost' && (
              <View style={styles.faceAlert}>
                <Text style={styles.faceAlertText}>
                  Stay in the scanning area. Remove glasses or obstructions if possible.
                </Text>
              </View>
            )}
          </View>
        )}
      </CameraView>
      <View style={[styles.controls, forceVisual && { backgroundColor: colors.gradientEnd }]}>
        {!recording ? (
          <TouchableOpacity style={styles.recBtn} onPress={start} activeOpacity={0.8}>
            <View style={[styles.recInner, forceVisual && { backgroundColor: colors.purple }]} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={styles.recBtn} onPress={stop} activeOpacity={0.8}>
            <View style={styles.stopInner} />
          </TouchableOpacity>
        )}
        <Text style={styles.hint}>
          {recording ? 'Tap to stop early' : `Tap to begin ${DURATION}-second scan`}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, backgroundColor: colors.gradientStart },
  camera: { flex: 1 },

  // Visual mode badge
  visualBadge: { position: 'absolute', top: 50, alignSelf: 'center', zIndex: 10,
    backgroundColor: 'rgba(126,87,194,0.85)', paddingHorizontal: 16, paddingVertical: 6, borderRadius: 20 },
  visualBadgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },

  // Permission screen
  permScreen: { flex: 1, backgroundColor: colors.gradientStart, justifyContent: 'center', alignItems: 'center' },
  permCard: { backgroundColor: colors.white, borderRadius: 24, padding: 32, marginHorizontal: 24,
    alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 20, elevation: 6 },
  permIcon: { width: 56, height: 56, borderRadius: 28, justifyContent: 'center', alignItems: 'center', marginBottom: 16 },
  permIconText: { fontSize: 22, fontWeight: '700' },
  permTitle: { fontSize: 22, fontWeight: '800', color: colors.textPrimary, marginBottom: 8 },
  permDesc: { fontSize: 14, color: colors.textSecondary, textAlign: 'center', lineHeight: 20, marginBottom: 24 },
  permBtn: { paddingVertical: 14, paddingHorizontal: 48, borderRadius: 16 },
  permBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },

  // Analyzing
  analyzeScreen: { flex: 1, backgroundColor: colors.gradientStart, justifyContent: 'center',
    alignItems: 'center', padding: 32, overflow: 'hidden' },
  blobG: { position: 'absolute', top: -60, right: -60, width: 200, height: 200, borderRadius: 100,
    backgroundColor: colors.greenLight, opacity: 0.5 },
  blobP: { position: 'absolute', bottom: 80, left: -80, width: 250, height: 250, borderRadius: 125,
    backgroundColor: colors.purpleLight, opacity: 0.4 },
  analyzeTitle: { fontSize: 24, fontWeight: '800', color: colors.textPrimary, marginTop: 20 },
  analyzeDesc: { fontSize: 13, color: colors.textSecondary, marginTop: 8, textAlign: 'center', lineHeight: 19 },

  // Guide overlay
  guideOverlay: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  faceGuide: { width: 200, height: 260, borderRadius: 100, borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.5)', borderStyle: 'dashed' },
  guideText: { color: 'rgba(255,255,255,0.8)', fontSize: 14, marginTop: 14, fontWeight: '500' },
  guideSub: { color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 4 },

  // Face status indicator
  faceStatusBar: { position: 'absolute', top: 20, alignSelf: 'center',
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 20, borderWidth: 1 },
  faceStatusDot: { width: 8, height: 8, borderRadius: 4, marginRight: 8 },
  faceStatusText: { fontSize: 12, fontWeight: '600' },

  // Face lost alert
  faceAlert: { position: 'absolute', bottom: 20, marginHorizontal: 20,
    backgroundColor: 'rgba(229,57,53,0.85)', borderRadius: 12, padding: 12 },
  faceAlertText: { color: '#fff', fontSize: 12, fontWeight: '500', textAlign: 'center', lineHeight: 17 },

  // Recording overlay
  recordOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.15)', justifyContent: 'center', alignItems: 'center' },
  timerBox: { width: 100, height: 100, justifyContent: 'center', alignItems: 'center' },
  timerPulse: { position: 'absolute', width: 100, height: 100, borderRadius: 50 },
  timerNum: { fontSize: 42, fontWeight: '700', color: '#fff' },
  recHint: { color: 'rgba(255,255,255,0.85)', fontSize: 14, marginTop: 18, fontWeight: '500' },

  // Controls
  controls: { paddingVertical: 24, alignItems: 'center', backgroundColor: colors.gradientStart },
  recBtn: { width: 72, height: 72, borderRadius: 36, borderWidth: 3,
    borderColor: colors.textPrimary, justifyContent: 'center', alignItems: 'center' },
  recInner: { width: 54, height: 54, borderRadius: 27, backgroundColor: colors.statusRed },
  stopInner: { width: 28, height: 28, borderRadius: 4, backgroundColor: colors.statusRed },
  hint: { color: colors.textMuted, marginTop: 10, fontSize: 13 },
});