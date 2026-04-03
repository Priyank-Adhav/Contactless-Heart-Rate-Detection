// TODO: Implement Camera Screen (Face Scan mode)
// See docs/app/02_camera_capture.md for full implementation guide
//
// Flow:
//   1. Request camera permission
//   2. Show front camera preview
//   3. User taps record → 30-second countdown
//   4. Upload video to backend via api.analyzeVideo()
//   5. Navigate to Results screen with response data

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../theme/colors';

export default function CameraScreen({ navigation }) {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Camera Screen — TODO</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background,
    justifyContent: 'center', alignItems: 'center' },
  text: { color: COLORS.textPrimary, fontSize: 18 },
});
