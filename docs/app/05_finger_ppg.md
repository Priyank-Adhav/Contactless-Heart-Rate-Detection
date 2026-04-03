# App Module 5: Finger PPG Mode

Owner: P2 (Signal Lead)

## Purpose

Provide an alternative measurement mode where the user places their fingertip
on the **back camera** with the **flashlight ON**. This produces a much stronger
pulse signal than face-based rPPG (10-100x better SNR).

## How It Works

```
💡 Flashlight ON → 🫰 Finger covers camera → 📹 Red glow pulsates
                                                     │
                             Extract red channel intensity per frame
                                                     │
                              Same pipeline: filter → BPM → HRV → Stress
```

The light passes through the fingertip. Blood absorbs light with each pulse,
creating a very clear oscillating red signal. This is the same principle as
hospital pulse oximeters.

## Important Note

> ⚠️ This is NOT blood pressure measurement. It measures the same things as
> face mode: pulse rate, HRV, and stress indicators — just with better quality.

## Dependencies

- `expo-camera` — back camera access
- `expo-torch` or camera flashlight control
- Module 3 (`api.js`) — same upload endpoint works

## Backend Changes Required

A new endpoint `POST /api/analyze/finger` that processes finger video differently:
- Extract **red** channel (not green) — blood absorbs more in red band
- Skip face detection entirely — just read average pixel intensity per frame
- Same downstream pipeline: bandpass → BPM → HRV → Stress

## Implementation Guide

### `src/screens/FingerScreen.js`

```javascript
import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert,
         ActivityIndicator } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { COLORS } from '../theme/colors';
import { analyzeVideo } from '../services/api';

const DURATION = 30;

export default function FingerScreen({ navigation }) {
  const [permission, requestPermission] = useCameraPermissions();
  const [recording, setRecording] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [seconds, setSeconds] = useState(DURATION);
  const camRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => () => clearInterval(timerRef.current), []);

  if (!permission) return <View style={styles.center} />;
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.msg}>Camera permission is needed</Text>
        <TouchableOpacity style={styles.btn} onPress={requestPermission}>
          <Text style={styles.btnText}>Allow Camera</Text>
        </TouchableOpacity>
      </View>
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
      const video = await camRef.current.recordAsync({
        maxDuration: DURATION,
        quality: '720p',
      });

      setRecording(false);
      clearInterval(timerRef.current);
      setAnalyzing(true);

      // Uses same endpoint — backend auto-detects mode or
      // use a separate /api/analyze/finger endpoint
      const result = await analyzeVideo(video.uri);
      setAnalyzing(false);
      navigation.replace('Results', { result });
    } catch (err) {
      setRecording(false);
      setAnalyzing(false);
      clearInterval(timerRef.current);
      Alert.alert('Error', err.message);
    }
  };

  const stop = () => camRef.current?.stopRecording();

  if (analyzing) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.success} />
        <Text style={[styles.msg, { marginTop: 16 }]}>Analyzing pulse...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Instructions (shown before recording) */}
      {!recording && (
        <View style={styles.instructions}>
          <Text style={styles.stepTitle}>How to use Finger Pulse mode:</Text>
          <Text style={styles.step}>1. Turn ON your phone's flashlight 💡</Text>
          <Text style={styles.step}>2. Place your index finger over the back camera</Text>
          <Text style={styles.step}>3. Press firmly — you should see a red glow</Text>
          <Text style={styles.step}>4. Tap the record button below</Text>
          <Text style={styles.step}>5. Hold still for 30 seconds</Text>
        </View>
      )}

      {/* Camera (back-facing for finger) */}
      <CameraView
        ref={camRef}
        style={recording ? styles.cameraFull : styles.cameraSmall}
        facing="back"
        mode="video"
        enableTorch={recording}
      >
        {recording && (
          <View style={styles.overlay}>
            <View style={styles.timerRing}>
              <Text style={styles.timerNum}>{seconds}</Text>
            </View>
            <Text style={styles.hint}>Keep finger pressed firmly</Text>
          </View>
        )}
      </CameraView>

      <View style={styles.controls}>
        {!recording ? (
          <TouchableOpacity style={styles.recBtn} onPress={start}>
            <View style={styles.recDot} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={styles.recBtn} onPress={stop}>
            <View style={styles.stopSquare} />
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: COLORS.background },
  center:       { flex: 1, backgroundColor: COLORS.background,
                  justifyContent: 'center', alignItems: 'center', padding: 32 },
  instructions: { padding: 24 },
  stepTitle:    { fontSize: 18, fontWeight: '600', color: COLORS.textPrimary,
                  marginBottom: 16 },
  step:         { fontSize: 15, color: COLORS.textSecondary,
                  marginBottom: 8, lineHeight: 22 },
  cameraFull:   { flex: 1 },
  cameraSmall:  { height: 200, borderRadius: 12, overflow: 'hidden',
                  marginHorizontal: 24 },
  overlay:      { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)',
                  justifyContent: 'center', alignItems: 'center' },
  timerRing:    { width: 110, height: 110, borderRadius: 55, borderWidth: 3,
                  borderColor: COLORS.success, justifyContent: 'center',
                  alignItems: 'center' },
  timerNum:     { fontSize: 44, fontWeight: '700', color: '#fff' },
  hint:         { color: '#ddd', fontSize: 15, marginTop: 20 },
  controls:     { padding: 20, alignItems: 'center' },
  recBtn:       { width: 68, height: 68, borderRadius: 34, borderWidth: 3,
                  borderColor: '#fff', justifyContent: 'center',
                  alignItems: 'center' },
  recDot:       { width: 52, height: 52, borderRadius: 26,
                  backgroundColor: COLORS.success },
  stopSquare:   { width: 26, height: 26, borderRadius: 4,
                  backgroundColor: COLORS.danger },
  msg:          { color: '#fff', fontSize: 16, textAlign: 'center' },
  btn:          { marginTop: 16, backgroundColor: COLORS.success,
                  paddingVertical: 14, paddingHorizontal: 32, borderRadius: 12 },
  btnText:      { color: '#fff', fontWeight: '600' },
});
```

## Testing Checklist

- [ ] Back camera activates (not front)
- [ ] Flashlight/torch turns ON when recording starts
- [ ] Instructions visible before recording
- [ ] Red glow visible through finger on camera preview
- [ ] Recording completes and uploads successfully
- [ ] Results screen shows data from finger measurement
