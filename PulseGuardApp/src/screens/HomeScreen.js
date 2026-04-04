import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  Animated, Dimensions, StatusBar, SafeAreaView, Alert, Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import { useFocusEffect } from '@react-navigation/native';
import { colors } from '../theme/colors';
import { analyzeVideo } from '../services/api';

const { width } = Dimensions.get('window');

export default function HomeScreen({ navigation }) {
  const [mode, setMode] = useState('wellness');
  const [history, setHistory] = useState([]);
  const [uploading, setUploading] = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(30)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.timing(slideAnim, { toValue: 0, duration: 700, useNativeDriver: true }),
    ]).start();
    const pulse = Animated.loop(Animated.sequence([
      Animated.timing(pulseAnim, { toValue: 1.12, duration: 700, useNativeDriver: true }),
      Animated.timing(pulseAnim, { toValue: 1, duration: 700, useNativeDriver: true }),
    ]));
    pulse.start();
    return () => pulse.stop();
  }, []);

  // Load past results on focus
  useFocusEffect(useCallback(() => {
    AsyncStorage.getItem('pulseguard_history').then(data => {
      if (data) setHistory(JSON.parse(data));
    }).catch(() => {});
  }, []));

  // TWIST 2: Upload pre-recorded video
  const handleUpload = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      quality: 0.7,
    });
    if (result.canceled) return;
    setUploading(true);
    try {
      const analysisResult = await analyzeVideo(result.assets[0].uri);
      setUploading(false);
      navigation.navigate('Results', { result: analysisResult, mode });
    } catch (err) {
      setUploading(false);
      Alert.alert('Error', err.message || 'Upload failed. Is the backend running?');
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.gradientStart} />
      <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
        {/* Decorative blobs */}
        <View style={styles.blobGreen} />
        <View style={styles.blobPurple} />

        <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>

          {/* Logo */}
          <View style={styles.logoWrap}>
            <Animated.View style={[styles.pulseBg, { transform: [{ scale: pulseAnim }] }]} />
            <View style={styles.logoCircle}>
              <Text style={styles.logoText}>+</Text>
            </View>
          </View>
          <Text style={styles.brand}>PulseGuard</Text>
          <Text style={styles.tagline}>Your personal heart health companion</Text>

          {/* Mode Toggle */}
          <View style={styles.modeRow}>
            <TouchableOpacity
              style={[styles.modeBtn, mode === 'wellness' && styles.modeActiveG]}
              onPress={() => setMode('wellness')} activeOpacity={0.8}>
              <Text style={[styles.modeLbl, mode === 'wellness' && styles.modeLblActiveG]}>Wellness</Text>
              <Text style={styles.modeSub}>Daily monitoring</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeBtn, mode === 'emergency' && styles.modeActiveR]}
              onPress={() => setMode('emergency')} activeOpacity={0.8}>
              <Text style={[styles.modeLbl, mode === 'emergency' && styles.modeLblActiveR]}>Emergency</Text>
              <Text style={styles.modeSub}>Rapid triage</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.divider} />

          <Text style={styles.sectionLabel}>CHOOSE METHOD</Text>

          {/* Finger Scan Card */}
          <TouchableOpacity style={[styles.card, styles.cardGreen]}
            onPress={() => navigation.navigate('Finger', { mode })} activeOpacity={0.85}>
            <View style={styles.cardIcon}>
              <View style={styles.iconCircleGreen}><Text style={styles.iconText}>F</Text></View>
            </View>
            <View style={styles.cardBody}>
              <Text style={styles.cardTitle}>Finger Scan</Text>
              <Text style={styles.cardDesc}>Cover the flashlight with your fingertip</Text>
            </View>
            <Text style={styles.cardArrow}>›</Text>
          </TouchableOpacity>

          {/* Face Scan Card */}
          <TouchableOpacity style={[styles.card, styles.cardPurple]}
            onPress={() => navigation.navigate('Camera', { mode })} activeOpacity={0.85}>
            <View style={styles.cardIcon}>
              <View style={styles.iconCirclePurple}><Text style={styles.iconText}>C</Text></View>
            </View>
            <View style={styles.cardBody}>
              <Text style={styles.cardTitle}>Face Scan</Text>
              <Text style={styles.cardDesc}>Contactless detection via front camera</Text>
            </View>
            <Text style={styles.cardArrow}>›</Text>
          </TouchableOpacity>

          {/* TWIST 2: Upload Video Card */}
          <TouchableOpacity style={[styles.card, { borderColor: colors.border }]}
            onPress={handleUpload} activeOpacity={0.85} disabled={uploading}>
            <View style={styles.cardIcon}>
              <View style={[styles.iconCircleGreen, { backgroundColor: 'rgba(0,0,0,0.04)' }]}>
                <Text style={[styles.iconText, { color: colors.textSecondary }]}>
                  {uploading ? '...' : 'U'}
                </Text>
              </View>
            </View>
            <View style={styles.cardBody}>
              <Text style={styles.cardTitle}>{uploading ? 'Uploading...' : 'Upload Video'}</Text>
              <Text style={styles.cardDesc}>Analyze a pre-recorded 10+ second clip</Text>
            </View>
            <Text style={styles.cardArrow}>›</Text>
          </TouchableOpacity>

          {/* Triage Legend */}
          <View style={styles.legendCard}>
            <Text style={styles.legendTitle}>Smart Triage System</Text>
            <View style={styles.legendRow}>
              <View style={[styles.legendDot, { backgroundColor: colors.statusRed }]} />
              <Text style={styles.legendText}>Critical — Immediate attention</Text>
            </View>
            <View style={styles.legendRow}>
              <View style={[styles.legendDot, { backgroundColor: colors.statusYellow }]} />
              <Text style={styles.legendText}>Elevated — Monitor closely</Text>
            </View>
            <View style={styles.legendRow}>
              <View style={[styles.legendDot, { backgroundColor: colors.statusGreen }]} />
              <Text style={styles.legendText}>Stable — All vitals normal</Text>
            </View>
            <View style={[styles.dividerSmall, { marginVertical: 10 }]} />
            <Text style={[styles.legendTitle, { marginBottom: 6 }]}>Mode Indicator</Text>
            <View style={styles.legendRow}>
              <View style={[styles.legendDot, { backgroundColor: colors.modeBiometric }]} />
              <Text style={styles.legendText}>Biometric — rPPG signal analysis</Text>
            </View>
            <View style={styles.legendRow}>
              <View style={[styles.legendDot, { backgroundColor: colors.modeVisual }]} />
              <Text style={styles.legendText}>Visual Assessment — distress indicators</Text>
            </View>
          </View>

          {/* Past Results */}
          {history.length > 0 && (
            <View>
              <Text style={styles.sectionLabel}>RECENT RESULTS</Text>
              {history.slice(0, 5).map((item, i) => (
                <TouchableOpacity key={i} style={styles.historyRow}
                  onPress={() => navigation.navigate('Results', { result: item.result, mode })}
                  activeOpacity={0.8}>
                  <View style={[styles.histDot, {
                    backgroundColor: item.result.stress_level === 'HIGH' ? colors.statusRed
                      : item.result.stress_level === 'MODERATE' ? colors.statusYellow
                      : colors.statusGreen }]} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.histBpm}>
                      {item.result.bpm ? Math.round(item.result.bpm) + ' BPM' : 'N/A'}
                      {' — '}
                      {item.result.active_mode === 'visual_assessment' ? 'Visual' : 'Biometric'}
                    </Text>
                    <Text style={styles.histTime}>{item.time}</Text>
                  </View>
                  <Text style={styles.cardArrow}>›</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          <Text style={styles.disclaimer}>Not a medical device. For wellness monitoring only.</Text>
        </Animated.View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.gradientStart },
  scroll: { flex: 1, overflow: 'hidden' },
  content: { paddingHorizontal: 24, paddingTop: 32, paddingBottom: 48 },
  blobGreen: { position: 'absolute', top: -80, right: -80, width: 260, height: 260,
    borderRadius: 130, backgroundColor: colors.greenLight, opacity: 0.5 },
  blobPurple: { position: 'absolute', bottom: 100, left: -100, width: 300, height: 300,
    borderRadius: 150, backgroundColor: colors.purpleLight, opacity: 0.4 },

  // Logo
  logoWrap: { alignSelf: 'center', marginBottom: 16, alignItems: 'center', justifyContent: 'center' },
  pulseBg: { position: 'absolute', width: 90, height: 90, borderRadius: 45,
    backgroundColor: colors.greenGlow },
  logoCircle: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.white,
    alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: colors.borderGreen,
    ...Platform.select({ ios: { shadowColor: colors.green, shadowOpacity: 0.3, shadowRadius: 14, shadowOffset: { width: 0, height: 5 } },
      android: { elevation: 8 } }) },
  logoText: { fontSize: 32, color: colors.green, fontWeight: '800' },
  brand: { fontSize: 32, fontWeight: '800', color: colors.textPrimary, textAlign: 'center',
    letterSpacing: -0.5, marginBottom: 4 },
  tagline: { fontSize: 13, color: colors.textSecondary, textAlign: 'center', marginBottom: 24 },

  // Mode
  modeRow: { flexDirection: 'row', marginBottom: 20 },
  modeBtn: { flex: 1, paddingVertical: 14, borderRadius: 16, marginHorizontal: 4,
    backgroundColor: colors.white, borderWidth: 1.5, borderColor: colors.border, alignItems: 'center',
    ...Platform.select({ ios: { shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 } }) },
  modeActiveG: { borderColor: colors.borderGreen, backgroundColor: 'rgba(46,125,50,0.05)' },
  modeActiveR: { borderColor: 'rgba(229,57,53,0.3)', backgroundColor: colors.statusRedBg },
  modeLbl: { fontSize: 15, fontWeight: '600', color: colors.textMuted },
  modeLblActiveG: { color: colors.green },
  modeLblActiveR: { color: colors.statusRed },
  modeSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },

  divider: { width: width * 0.4, height: 1.5, backgroundColor: colors.border,
    borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  dividerSmall: { height: 1, backgroundColor: colors.border },
  sectionLabel: { fontSize: 11, fontWeight: '700', color: colors.textMuted,
    letterSpacing: 1.5, marginBottom: 12 },

  // Cards
  card: { width: '100%', flexDirection: 'row', alignItems: 'center', borderRadius: 18, padding: 16,
    marginBottom: 12, backgroundColor: colors.white, borderWidth: 1.5,
    ...Platform.select({ ios: { shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 3 } },
      android: { elevation: 3 } }) },
  cardGreen: { borderColor: colors.borderGreen },
  cardPurple: { borderColor: colors.borderPurple },
  cardIcon: { marginRight: 14 },
  iconCircleGreen: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.greenLight,
    alignItems: 'center', justifyContent: 'center' },
  iconCirclePurple: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.purpleLight,
    alignItems: 'center', justifyContent: 'center' },
  iconText: { fontSize: 17, fontWeight: '700', color: colors.textPrimary },
  cardBody: { flex: 1 },
  cardTitle: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, marginBottom: 2 },
  cardDesc: { fontSize: 12, color: colors.textSecondary, lineHeight: 17 },
  cardArrow: { fontSize: 24, color: colors.textMuted, fontWeight: '300' },

  // Legend
  legendCard: { backgroundColor: colors.white, borderRadius: 16, padding: 16, marginBottom: 16,
    borderWidth: 1, borderColor: colors.border,
    ...Platform.select({ ios: { shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 } }) },
  legendTitle: { fontSize: 12, fontWeight: '700', color: colors.textPrimary, marginBottom: 8 },
  legendRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 5 },
  legendDot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  legendText: { fontSize: 12, color: colors.textSecondary },

  // History
  historyRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.white,
    borderRadius: 14, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: colors.border },
  histDot: { width: 10, height: 10, borderRadius: 5, marginRight: 12 },
  histBpm: { fontSize: 14, fontWeight: '600', color: colors.textPrimary },
  histTime: { fontSize: 11, color: colors.textMuted, marginTop: 2 },

  disclaimer: { fontSize: 10, color: colors.textMuted, textAlign: 'center', marginTop: 16 },
});