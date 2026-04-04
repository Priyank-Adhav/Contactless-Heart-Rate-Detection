import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet, Alert,
  ActivityIndicator, SafeAreaView, StatusBar, Animated, Platform,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { colors } from '../theme/colors';
import { analyzeFingerVideo } from '../services/api';

const DURATION = 30;

export default function FingerScreen({ navigation }) {
  const [permission, requestPermission] = useCameraPermissions();
  const [recording, setRecording] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [seconds, setSeconds] = useState(DURATION);
  const [ready, setReady] = useState(false);
  const camRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => () => clearInterval(timerRef.current), []);

  if (!permission) return <View style={{ flex: 1, backgroundColor: colors.gradientStart }} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permScreen}>
        <View style={styles.permCard}>
          <View style={[styles.permIcon, { backgroundColor: colors.purpleLight }]}>
            <Text style={[styles.permIconText, { color: colors.purple }]}>F</Text>
          </View>
          <Text style={styles.permTitle}>Camera Required</Text>
          <Text style={styles.permDesc}>
            The camera sensor detects light pulsation through your fingertip
            while the flashlight illuminates it from below.
          </Text>
          <TouchableOpacity style={[styles.permBtn, { backgroundColor: colors.purple }]}
            onPress={requestPermission}>
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
      // POST to /api/analyze/finger → red channel → bandpass → BPM → HRV → Stress
      const result = await analyzeFingerVideo(video.uri);
      setAnalyzing(false);
      navigation.replace('Results', { result });
    } catch (err) {
      setRecording(false);
      setAnalyzing(false);
      clearInterval(timerRef.current);
      Alert.alert('Error', err.message || 'Failed. Check backend is running.');
    }
  };

  const stop = () => camRef.current?.stopRecording();

  // Analyzing screen
  if (analyzing) {
    return (
      <SafeAreaView style={styles.analyzeScreen}>
        <View style={styles.blobG} />
        <View style={styles.blobP} />
        <ActivityIndicator size="large" color={colors.purple} />
        <Text style={styles.analyzeTitle}>Analyzing Pulse...</Text>
        <Text style={styles.analyzeDesc}>
          Extracting heart rate from blood flow patterns in red channel
        </Text>
      </SafeAreaView>
    );
  }

  // Step-by-step instructions (before camera opens)
  if (!ready && !recording) {
    return (
      <SafeAreaView style={styles.instrScreen}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.blobG} />
        <View style={styles.blobP} />
        <ScrollView contentContainerStyle={styles.instrContent}>
          <Text style={styles.instrTitle}>Finger Pulse Mode</Text>
          <Text style={styles.instrSub}>
            Same technology used in hospital pulse oximeters — but using your phone's flashlight
          </Text>

          <View style={styles.stepsCard}>
            <Step num="1" title="Place finger on the flashlight"
              desc="Gently press your index fingertip over the flashlight lens on the back of your phone." />
            <View style={styles.stepDivider} />
            <Step num="2" title="Flashlight activates automatically"
              desc="When recording starts, the light turns on and shines through your finger. Your screen will glow red — that's your blood." />
            <View style={styles.stepDivider} />
            <Step num="3" title="Hold still for 30 seconds"
              desc="Don't move or lift your finger. The app measures tiny brightness changes caused by each heartbeat." />
          </View>

          <View style={styles.tipBox}>
            <Text style={styles.tipTitle}>Tips for accuracy</Text>
            <Text style={styles.tipText}>
              Warm fingers give stronger signals. Press firmly but not too hard. Avoid moving your hand.
            </Text>
          </View>

          <TouchableOpacity style={styles.startBtn} onPress={() => setReady(true)} activeOpacity={0.85}>
            <Text style={styles.startBtnText}>I'm Ready — Start Measurement</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // Camera recording screen
  return (
    <View style={styles.container}>
      <CameraView ref={camRef} style={styles.camera} facing="back" mode="video" enableTorch={recording}>
        {recording ? (
          <View style={styles.recordOverlay}>
            <View style={styles.timerCircle}>
              <Text style={styles.timerNum}>{seconds}</Text>
              <Text style={styles.timerLabel}>sec</Text>
            </View>
            <Text style={styles.recHint}>Keep your finger pressed on the flashlight</Text>
          </View>
        ) : (
          <View style={styles.readyOverlay}>
            <Text style={styles.readyText}>Place finger on flashlight, then tap record below</Text>
          </View>
        )}
      </CameraView>
      <View style={styles.controls}>
        {!recording ? (
          <TouchableOpacity style={styles.recBtn} onPress={start} activeOpacity={0.8}>
            <View style={[styles.recInner, { backgroundColor: colors.purple }]} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={styles.recBtn} onPress={stop} activeOpacity={0.8}>
            <View style={styles.stopInner} />
          </TouchableOpacity>
        )}
        <Text style={styles.hint}>{recording ? 'Tap to stop' : 'Tap to start recording'}</Text>
      </View>
    </View>
  );
}

function Step({ num, title, desc }) {
  return (
    <View style={styles.stepRow}>
      <View style={styles.stepNumCircle}>
        <Text style={styles.stepNumText}>{num}</Text>
      </View>
      <View style={styles.stepBody}>
        <Text style={styles.stepTitle}>{title}</Text>
        <Text style={styles.stepDesc}>{desc}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { flex: 1 },

  // Permission
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
  analyzeScreen: { flex: 1, backgroundColor: colors.gradientEnd, justifyContent: 'center', alignItems: 'center', padding: 32, overflow: 'hidden' },
  blobG: { position: 'absolute', top: -60, right: -60, width: 200, height: 200, borderRadius: 100, backgroundColor: colors.greenLight },
  blobP: { position: 'absolute', bottom: 80, left: -80, width: 250, height: 250, borderRadius: 125, backgroundColor: colors.purpleLight },
  analyzeTitle: { fontSize: 24, fontWeight: '800', color: colors.textPrimary, marginTop: 20 },
  analyzeDesc: { fontSize: 13, color: colors.textSecondary, marginTop: 8, textAlign: 'center' },

  // Instructions
  instrScreen: { flex: 1, backgroundColor: colors.gradientEnd, overflow: 'hidden' },
  instrContent: { padding: 24, paddingBottom: 48 },
  instrTitle: { fontSize: 26, fontWeight: '800', color: colors.textPrimary, textAlign: 'center', marginTop: 12 },
  instrSub: { fontSize: 13, color: colors.textSecondary, textAlign: 'center', marginTop: 4, marginBottom: 28, lineHeight: 18 },
  stepsCard: { backgroundColor: colors.white, borderRadius: 20, padding: 20, marginBottom: 16,
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 16, shadowOffset: { width: 0, height: 4 }, elevation: 4,
    borderWidth: 1, borderColor: colors.border },
  stepRow: { flexDirection: 'row', paddingVertical: 6 },
  stepNumCircle: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.purpleLight,
    justifyContent: 'center', alignItems: 'center', marginRight: 14, marginTop: 2 },
  stepNumText: { fontSize: 14, fontWeight: '700', color: colors.purple },
  stepBody: { flex: 1 },
  stepTitle: { fontSize: 15, fontWeight: '700', color: colors.textPrimary, marginBottom: 3 },
  stepDesc: { fontSize: 12, color: colors.textSecondary, lineHeight: 17 },
  stepDivider: { height: 1, backgroundColor: colors.border, marginVertical: 14 },
  tipBox: { backgroundColor: colors.white, borderRadius: 14, padding: 16, marginBottom: 20,
    borderWidth: 1, borderColor: colors.borderGreen },
  tipTitle: { fontSize: 13, fontWeight: '700', color: colors.green, marginBottom: 4 },
  tipText: { fontSize: 12, color: colors.textSecondary, lineHeight: 17 },
  startBtn: { backgroundColor: colors.purple, paddingVertical: 16, borderRadius: 18, alignItems: 'center',
    shadowColor: colors.purple, shadowOpacity: 0.3, shadowRadius: 12, elevation: 6 },
  startBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },

  // Recording
  recordOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.2)', justifyContent: 'center', alignItems: 'center' },
  timerCircle: { width: 100, height: 100, borderRadius: 50, borderWidth: 3, borderColor: '#fff',
    justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.3)' },
  timerNum: { fontSize: 38, fontWeight: '700', color: '#fff' },
  timerLabel: { fontSize: 11, color: 'rgba(255,255,255,0.7)', marginTop: -2 },
  recHint: { color: 'rgba(255,255,255,0.85)', fontSize: 14, marginTop: 18, fontWeight: '500' },
  readyOverlay: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.5)' },
  readyText: { color: '#fff', fontSize: 16, fontWeight: '500', textAlign: 'center', paddingHorizontal: 24 },

  // Controls
  controls: { paddingVertical: 24, alignItems: 'center', backgroundColor: colors.gradientStart },
  recBtn: { width: 72, height: 72, borderRadius: 36, borderWidth: 3,
    borderColor: colors.textPrimary, justifyContent: 'center', alignItems: 'center' },
  recInner: { width: 54, height: 54, borderRadius: 27 },
  stopInner: { width: 28, height: 28, borderRadius: 4, backgroundColor: colors.statusRed },
  hint: { color: colors.textMuted, marginTop: 10, fontSize: 13 },
});