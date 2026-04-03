// TODO: Implement Home Screen
// See docs/app/01_setup_navigation.md for full implementation guide
//
// This screen shows two main options:
//   1. "Face Scan" — navigates to CameraScreen (front camera, rPPG)
//   2. "Finger Pulse" — navigates to FingerScreen (back camera + flash)

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../theme/colors';

export default function HomeScreen({ navigation }) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>💓 PulseGuard</Text>
      <Text style={styles.subtitle}>Contact-Free Cardiac Monitoring</Text>
      {/* TODO: Add Face Scan and Finger Pulse buttons */}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background,
    justifyContent: 'center', alignItems: 'center', padding: 24 },
  title: { fontSize: 32, fontWeight: '700', color: COLORS.textPrimary },
  subtitle: { fontSize: 14, color: COLORS.textSecondary, marginTop: 4 },
});
