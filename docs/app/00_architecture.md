# PulseGuard Mobile App — Architecture & Setup

## Overview

The PulseGuard mobile app is built with **React Native + Expo** and communicates
with the existing Python FastAPI backend for all signal processing. The app
captures video from the phone's camera (much better quality than a webcam),
sends it to the server, and displays the results in a polished dashboard.

### Unique Features

1. **Contact-Free Face Scan** — rPPG pulse detection using front camera
2. **🫰 Finger Pulse Mode** — fingertip on camera + flashlight for higher accuracy (unique feature!)
3. **🚦 Smart Triage System** — color-coded urgency indicator (🔴🟡🟢) for instant decision-making
4. **🤖 Gemini AI Insights** — personalized health suggestions powered by Gemini
5. **👤 Dual User Modes** — Emergency (paramedic/disaster) vs Wellness (daily monitoring)

### Why React Native + Expo?

- Phone camera access with native quality (front + back camera)
- Builds to a real **.apk** file for Android distribution
- JavaScript — same language as the existing web frontend
- Cross-platform (Android + iOS) from one codebase

### APK Build Process

```bash
# Option 1: Local APK build (no Expo account needed)
cd app
npx expo install expo-dev-client
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease
# APK at: android/app/build/outputs/apk/release/app-release.apk

# Option 2: Cloud build via EAS (needs free Expo account)
npm install -g eas-cli
eas login
eas build --platform android --profile preview
# Downloads APK from Expo dashboard
```

## System Architecture

```
┌────────────────────────────────────┐        ┌────────────────────────────────┐
│     📱 Mobile App (React Native)   │  HTTP  │   🖥️ Python Backend (FastAPI)  │
│                                    │        │                                │
│  HomeScreen                        │        │  POST /api/analyze             │
│   ├── 🧑 Face Scan mode            │  ────► │   ROI → Signal → HRV → Stress │
│   ├── ☝️ Finger Pulse mode         │        │                                │
│   └── ⚙️ Mode: Emergency/Wellness  │        │  POST /api/triage             │
│                                    │  ────► │   Combined vitals → triage     │
│  CameraScreen / FingerScreen       │        │                                │
│   └── Records 30s video            │        │  POST /api/insights            │
│                                    │  ────► │   Gemini AI suggestions        │
│  ResultsScreen                     │        │                                │
│   ├── 🚦 Triage Banner             │  ◄──── │  Returns JSON results          │
│   ├── BPM + HRV + Stress           │        │                                │
│   ├── AI Insights                  │        └────────────────────────────────┘
│   └── Mode-specific actions        │
└────────────────────────────────────┘
```

## Project Structure

All app files live inside the existing `src/` folder alongside the Python modules:

```
src/
├── api/                           Python backend (already exists)
├── signal_processor.py            Module 02 (already done)
├── hrv_analyzer.py                Module 04 (already done)
├── stress_classifier.py           Module 05 (already done)
│
└── app/                           ← React Native app code
    ├── screens/
    │   ├── HomeScreen.js          Landing: mode selection + feature cards
    │   ├── CameraScreen.js        Face video recording + upload
    │   ├── FingerScreen.js        Finger-on-camera recording
    │   └── ResultsScreen.js       Full results + triage + AI insights
    ├── components/
    │   ├── BPMDisplay.js          Large animated BPM counter
    │   ├── WaveformChart.js       BVP line chart
    │   ├── HRVMetricsGrid.js      RMSSD / SDNN / pNN50 / LF-HF cards
    │   ├── StressIndicator.js     Stress level badge with color
    │   ├── SQIBadge.js            Signal quality traffic light
    │   ├── TriageBanner.js        🚦 Smart triage indicator (🔴🟡🟢)
    │   ├── AIInsightsCard.js      Gemini AI suggestions display
    │   ├── FeatureCard.js         Reusable feature card for HomeScreen
    │   └── RecordingTimer.js      30-second countdown overlay
    ├── services/
    │   ├── api.js                 REST client for FastAPI backend
    │   ├── triage.js              Triage logic (can run client-side)
    │   └── gemini.js              Gemini AI integration helper
    └── theme/
        └── colors.js              Design tokens (dark theme palette)
```

When initializing the Expo project, run `npx create-expo-app` from the
project root and point it to use `src/app/` as the source directory.
The `App.js`, `app.json`, `package.json`, and `eas.json` files will be
in the project root alongside `src/`.

## Module Breakdown

| # | Module | Guide | Key Files | Owner | Priority |
|---|--------|-------|-----------|-------|----------|
| 1 | Setup & Navigation | [01_setup_navigation.md](01_setup_navigation.md) | `App.js`, `HomeScreen.js`, `colors.js` | Any | P0 |
| 2 | Camera Capture | [02_camera_capture.md](02_camera_capture.md) | `CameraScreen.js`, `RecordingTimer.js` | P4 | P0 |
| 3 | API Client | [03_api_client.md](03_api_client.md) | `api.js` | P3 | P0 |
| 4 | Results Dashboard | [04_results_dashboard.md](04_results_dashboard.md) | `ResultsScreen.js`, all components/ | P4 | P1 |
| 5 | Finger PPG Mode | [05_finger_ppg.md](05_finger_ppg.md) | `FingerScreen.js` | P2 | P1 |
| 6 | Gemini AI Insights | [06_gemini_insights.md](06_gemini_insights.md) | `gemini.js`, `AIInsightsCard.js` | P3 | P2 |
| 7 | Triage & User Modes | [07_triage_user_modes.md](07_triage_user_modes.md) | `triage.js`, `TriageBanner.js` | P2 | P1 |

## Quick Start for Developers

```bash
# 1. Create the Expo project
cd app
npx -y create-expo-app@latest ./ --template blank

# 2. Install dependencies
npx expo install expo-camera expo-av
npm install @react-navigation/native @react-navigation/native-stack
npx expo install react-native-screens react-native-safe-area-context
npm install react-native-chart-kit react-native-svg

# 3. Start dev server
npx expo start

# 4. Start Python backend (in another terminal)
cd .. && uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```
