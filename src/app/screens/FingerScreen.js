// TODO: Implement Finger Screen (Finger PPG mode)
// See docs/app/05_finger_ppg.md for full implementation guide
//
// Flow:
//   1. Show instructions (turn on flashlight, place finger on back camera)
//   2. Use BACK camera with flash/torch ON
//   3. Record 30 seconds of red-channel pulsation
//   4. Upload to backend for analysis
//   5. Navigate to Results screen

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../theme/colors';

export default function FingerScreen({ navigation }) {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Finger Screen — TODO</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background,
    justifyContent: 'center', alignItems: 'center' },
  text: { color: COLORS.textPrimary, fontSize: 18 },
});
