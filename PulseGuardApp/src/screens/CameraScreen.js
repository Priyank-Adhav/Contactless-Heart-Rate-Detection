import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Alert,
  ActivityIndicator, SafeAreaView, StatusBar, Animated,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { colors } from '../theme/colors';
import { analyzeVideo } from '../services/api';

const DURATION = 30;

export default function CameraScreen({ navigation }) {
  const [permission, requestPermission] = useCameraPermissions();
  const [recording, setRecording] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [seconds, setSeconds] = useState(DURATION);
  const camRef = useRef(null);
  const timerRef = useRef(null);
  const pulseAnim = useRef(new Animated.Value(1)).current;

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

  if (!permission) return <View style={styles.center} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permScreen}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.permCard}>
          <View style={styles.permIcon}><Text style={styles.permIconText}>C</Text></View>
          <Text style={styles.permTitle}>Camera Access</Text>
          <Text style={styles.permDesc}>
            PulseGuard detects your heart rate by analyzing subtle skin color
            changes captured through your front camera.
          </Text>
          <TouchableOpacity style={styles.permBtn} onPress={requestPermission} activeOpacity={0.85}>
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
      // POST to /api/analyze → runs ROI → Signal → HRV → Stress pipeline
      const result = await analyzeVideo(video.uri);
      setAnalyzing(false);
      navigation.replace('Results', { result });
    } catch (err) {
      setRecording(false);
      setAnalyzing(false);
      clearInterval(timerRef.current);
      Alert.alert('Error', err.message || 'Recording failed. Check backend is running.');
    }
  };

  const stop = () => camRef.current?.stopRecording();

  if (analyzing) {
    return (
      <SafeAreaView style={styles.analyzeScreen}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.blobG} />
        <View style={styles.blobP} />
        <ActivityIndicator size="large" color={colors.green} />
        <Text style={styles.analyzeTitle}>Analyzing...</Text>
        <Text style={styles.analyzeDesc}>
          Running: ROI extraction → Signal processing → HRV analysis → Stress classification
        </Text>
      </SafeAreaView>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView ref={camRef} style={styles.camera} facing="front" mode="video">
        {!recording && (
          <View style={styles.guideOverlay}>
            <View style={styles.faceGuide} />
            <Text style={styles.guideText}>Position your face in the oval</Text>
          </View>
        )}
        {recording && (
          <View style={styles.recordOverlay}>
            <Text style={styles.recDot}>●</Text>
            <View style={styles.timerBox}>
              <Animated.View style={[styles.timerPulse, { transform: [{ scale: pulseAnim }] }]} />
              <Text style={styles.timerNum}>{seconds}</Text>
            </View>
            <Text style={styles.recHint}>Hold still — detecting skin color changes</Text>
          </View>
        )}
      </CameraView>
      <View style={styles.controls}>
        {!recording ? (
          <TouchableOpacity style={styles.recBtn} onPress={start} activeOpacity={0.8}>
            <View style={styles.recInner} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={styles.recBtn} onPress={stop} activeOpacity={0.8}>
            <View style={styles.stopInner} />
          </TouchableOpacity>
        )}
        <Text style={styles.hint}>
          {recording ? 'Tap to stop early' : 'Tap to begin 30-second scan'}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, backgroundColor: colors.gradientStart },
  camera: { flex: 1 },

  // Permission screen
  permScreen: { flex: 1, backgroundColor: colors.gradientStart, justifyContent: 'center', alignItems: 'center' },
  permCard: { backgroundColor: colors.white, borderRadius: 24, padding: 32, marginHorizontal: 24,
    alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 20, elevation: 6 },
  permIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.greenLight,
    justifyContent: 'center', alignItems: 'center', marginBottom: 16 },
  permIconText: { fontSize: 22, fontWeight: '700', color: colors.green },
  permTitle: { fontSize: 22, fontWeight: '800', color: colors.textPrimary, marginBottom: 8 },
  permDesc: { fontSize: 14, color: colors.textSecondary, textAlign: 'center', lineHeight: 20, marginBottom: 24 },
  permBtn: { backgroundColor: colors.green, paddingVertical: 14, paddingHorizontal: 48, borderRadius: 16 },
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

  // Recording overlay
  recordOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.15)', justifyContent: 'center', alignItems: 'center' },
  recDot: { color: '#e53935', fontSize: 18, position: 'absolute', top: 20, left: 20 },
  timerBox: { width: 100, height: 100, justifyContent: 'center', alignItems: 'center' },
  timerPulse: { position: 'absolute', width: 100, height: 100, borderRadius: 50,
    backgroundColor: 'rgba(67,160,71,0.3)' },
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