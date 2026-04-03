# App Module 1: Setup & Navigation

Owner: Any team member (first task — do this before anything else)

## Purpose

Initialize the Expo project, install dependencies, configure navigation,
and build the HomeScreen with feature cards including the unique Finger Pulse
highlight and user mode selection (Emergency vs Wellness).

## Step 1: Create Project

```bash
cd app
npx -y create-expo-app@latest ./ --template blank
npx expo install expo-camera expo-av
npm install @react-navigation/native @react-navigation/native-stack
npx expo install react-native-screens react-native-safe-area-context
npm install react-native-chart-kit react-native-svg
```

## Step 2: APK Build Configuration

Create `app/eas.json`:

```json
{
  "cli": { "version": ">= 3.0.0" },
  "build": {
    "preview": {
      "distribution": "internal",
      "android": { "buildType": "apk" }
    },
    "production": {
      "android": { "buildType": "apk" }
    }
  }
}
```

## Step 3: Navigation Setup

### `App.js`

```javascript
import React, { useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';

import HomeScreen from './src/screens/HomeScreen';
import CameraScreen from './src/screens/CameraScreen';
import FingerScreen from './src/screens/FingerScreen';
import ResultsScreen from './src/screens/ResultsScreen';

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Stack.Navigator
        initialRouteName="Home"
        screenOptions={{
          headerStyle: { backgroundColor: '#0a0e1a' },
          headerTintColor: '#ffffff',
          headerTitleStyle: { fontWeight: '600' },
          contentStyle: { backgroundColor: '#0a0e1a' },
        }}
      >
        <Stack.Screen name="Home" component={HomeScreen}
          options={{ title: 'PulseGuard' }} />
        <Stack.Screen name="Camera" component={CameraScreen}
          options={{ title: 'Face Scan' }} />
        <Stack.Screen name="Finger" component={FingerScreen}
          options={{ title: 'Finger Pulse' }} />
        <Stack.Screen name="Results" component={ResultsScreen}
          options={{ title: 'Results' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

## Step 4: Design Tokens

### `src/theme/colors.js`

```javascript
export const COLORS = {
  background:  '#0a0e1a',
  card:        'rgba(255, 255, 255, 0.04)',
  cardBorder:  'rgba(255, 255, 255, 0.08)',
  accent:      '#6c9cfc',
  accentLight: 'rgba(108, 156, 252, 0.15)',
  textPrimary:   '#ffffff',
  textSecondary: '#9aa0a6',
  textMuted:     '#5f6368',
  success: '#34d399',
  warning: '#fbbf24',
  danger:  '#f87171',

  // Triage
  triageCritical:  '#ef4444',
  triageElevated:  '#f59e0b',
  triageStable:    '#10b981',

  // Modes
  modeEmergency: '#ef4444',
  modeWellness:  '#6c9cfc',
};

export const TRIAGE = {
  CRITICAL: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',
    border: 'rgba(239,68,68,0.4)', emoji: '🔴',
    label: 'CRITICAL', action: 'Immediate attention needed' },
  ELEVATED: { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)',
    border: 'rgba(245,158,11,0.4)', emoji: '🟡',
    label: 'ELEVATED', action: 'Monitor closely' },
  STABLE:   { color: '#10b981', bg: 'rgba(16,185,129,0.12)',
    border: 'rgba(16,185,129,0.4)', emoji: '🟢',
    label: 'STABLE', action: 'All vitals normal' },
};
```

## Step 5: Home Screen with Feature Cards + Mode Toggle

### `src/screens/HomeScreen.js`

```javascript
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { COLORS } from '../theme/colors';

export default function HomeScreen({ navigation }) {
  const [mode, setMode] = useState('wellness'); // 'wellness' or 'emergency'

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.container}>

      {/* ── App Title ── */}
      <Text style={styles.title}>💓 PulseGuard</Text>
      <Text style={styles.subtitle}>Contact-Free Cardiac Monitoring</Text>

      {/* ── User Mode Toggle ── */}
      <View style={styles.modeRow}>
        <TouchableOpacity
          style={[styles.modeBtn,
            mode === 'wellness' && styles.modeBtnActiveWellness]}
          onPress={() => setMode('wellness')}
        >
          <Text style={styles.modeEmoji}>👤</Text>
          <Text style={[styles.modeText,
            mode === 'wellness' && styles.modeTextActive]}>Wellness</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.modeBtn,
            mode === 'emergency' && styles.modeBtnActiveEmergency]}
          onPress={() => setMode('emergency')}
        >
          <Text style={styles.modeEmoji}>🚑</Text>
          <Text style={[styles.modeText,
            mode === 'emergency' && styles.modeTextActive]}>Emergency</Text>
        </TouchableOpacity>
      </View>

      {/* ── Mode Description ── */}
      <View style={styles.modeDesc}>
        {mode === 'wellness' ? (
          <Text style={styles.modeInfo}>
            📊 Daily stress monitoring • Wellness tracking • Long-term insights
          </Text>
        ) : (
          <Text style={[styles.modeInfo, { color: COLORS.danger }]}>
            ⚡ Rapid triage • Instant 🔴🟡🟢 assessment • Emergency protocols
          </Text>
        )}
      </View>

      {/* ── Scan Options ── */}
      <TouchableOpacity
        style={[styles.card, styles.faceCard]}
        onPress={() => navigation.navigate('Camera', { mode })}
      >
        <Text style={styles.cardEmoji}>🧑</Text>
        <Text style={styles.cardTitle}>Face Scan</Text>
        <Text style={styles.cardDesc}>
          Point front camera at your face for 30 seconds.{'\n'}
          No touching required — completely contactless.
        </Text>
      </TouchableOpacity>

      {/* ── ⭐ UNIQUE FEATURE: Finger Pulse Card ── */}
      <TouchableOpacity
        style={[styles.card, styles.fingerCard]}
        onPress={() => navigation.navigate('Finger', { mode })}
      >
        <View style={styles.badgeRow}>
          <Text style={styles.cardEmoji}>☝️</Text>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>⭐ HIGHER ACCURACY</Text>
          </View>
        </View>
        <Text style={styles.cardTitle}>Finger Pulse</Text>
        <Text style={styles.cardDesc}>
          Place fingertip on the back camera with flashlight ON.{'\n'}
          Uses PPG (same as hospital pulse oximeters) for stronger signal.
        </Text>
        <View style={styles.fingerSteps}>
          <Text style={styles.step}>💡 Turn on flashlight</Text>
          <Text style={styles.step}>☝️ Cover camera with finger</Text>
          <Text style={styles.step}>📊 Get 10-100x stronger pulse signal</Text>
        </View>
      </TouchableOpacity>

      {/* ── Triage Legend ── */}
      <View style={styles.triageLegend}>
        <Text style={styles.legendTitle}>🚦 Smart Triage System</Text>
        <View style={styles.legendRow}>
          <Text style={styles.legendItem}>🔴 Critical — Immediate attention</Text>
        </View>
        <View style={styles.legendRow}>
          <Text style={styles.legendItem}>🟡 Elevated — Monitor closely</Text>
        </View>
        <View style={styles.legendRow}>
          <Text style={styles.legendItem}>🟢 Stable — All vitals normal</Text>
        </View>
      </View>

      <Text style={styles.disclaimer}>
        ⚠️ Not a medical device. For wellness monitoring only.
        Always consult a healthcare provider for medical concerns.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: COLORS.background },
  container: { padding: 24, paddingBottom: 48 },
  title: { fontSize: 32, fontWeight: '700', color: COLORS.textPrimary,
    textAlign: 'center', marginTop: 20 },
  subtitle: { fontSize: 14, color: COLORS.textSecondary,
    textAlign: 'center', marginBottom: 24 },

  // Mode toggle
  modeRow: { flexDirection: 'row', marginBottom: 8 },
  modeBtn: { flex: 1, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'center', paddingVertical: 14, borderRadius: 12,
    borderWidth: 1, borderColor: COLORS.cardBorder, marginHorizontal: 4,
    backgroundColor: COLORS.card },
  modeBtnActiveWellness: { borderColor: 'rgba(108,156,252,0.5)',
    backgroundColor: 'rgba(108,156,252,0.12)' },
  modeBtnActiveEmergency: { borderColor: 'rgba(239,68,68,0.5)',
    backgroundColor: 'rgba(239,68,68,0.12)' },
  modeEmoji: { fontSize: 20, marginRight: 8 },
  modeText: { fontSize: 15, color: COLORS.textSecondary, fontWeight: '500' },
  modeTextActive: { color: COLORS.textPrimary, fontWeight: '600' },
  modeDesc: { marginBottom: 20, paddingHorizontal: 4 },
  modeInfo: { fontSize: 12, color: COLORS.textSecondary,
    textAlign: 'center', lineHeight: 18 },

  // Feature cards
  card: { padding: 20, borderRadius: 16, marginBottom: 14, borderWidth: 1 },
  faceCard: { backgroundColor: COLORS.accentLight,
    borderColor: 'rgba(108,156,252,0.3)' },
  fingerCard: { backgroundColor: 'rgba(52,211,153,0.08)',
    borderColor: 'rgba(52,211,153,0.35)' },
  badgeRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  badge: { backgroundColor: 'rgba(251,191,36,0.2)', paddingHorizontal: 10,
    paddingVertical: 3, borderRadius: 20, marginLeft: 10 },
  badgeText: { color: COLORS.warning, fontSize: 11, fontWeight: '700' },
  cardEmoji: { fontSize: 32, marginBottom: 6 },
  cardTitle: { fontSize: 20, fontWeight: '600', color: COLORS.textPrimary,
    marginBottom: 4 },
  cardDesc: { fontSize: 13, color: COLORS.textSecondary, lineHeight: 18 },
  fingerSteps: { marginTop: 12, backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: 10, padding: 12 },
  step: { fontSize: 12, color: COLORS.textSecondary, marginBottom: 4 },

  // Triage legend
  triageLegend: { backgroundColor: COLORS.card, borderRadius: 12, borderWidth: 1,
    borderColor: COLORS.cardBorder, padding: 16, marginBottom: 16 },
  legendTitle: { fontSize: 14, fontWeight: '600', color: COLORS.textPrimary,
    marginBottom: 10 },
  legendRow: { marginBottom: 4 },
  legendItem: { fontSize: 13, color: COLORS.textSecondary },

  disclaimer: { fontSize: 11, color: COLORS.textMuted,
    textAlign: 'center', lineHeight: 16, marginTop: 8 },
});
```

## Testing

```bash
npx expo start
# Verify: Home screen renders with mode toggle, both cards, triage legend
# Tap mode toggle — switches between Wellness/Emergency
# Tap Face Scan — navigates to Camera
# Tap Finger Pulse — navigates to Finger
```
