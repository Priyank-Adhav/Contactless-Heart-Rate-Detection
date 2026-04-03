# App Module 6: Gemini AI Insights (Explainable AI)

Owner: P3 (Backend Lead)

## Purpose

After the analysis completes, send the results to Google's Gemini API to
generate personalized, plain-language health insights including:
- A summary of the user's cardiac state
- Alerts for any abnormal values
- Actionable suggestions (breathing exercises, hydration, etc.)

## Architecture

```
ResultsScreen                  FastAPI Backend               Gemini API
     │                              │                            │
     ├── POST /api/insights ──────► │                            │
     │   { bpm, hrv, stress }       ├── build prompt ──────────► │
     │                              │                            │
     │                              │ ◄── JSON response ────────┤
     │ ◄── { summary, alerts,  ─────┤                            │
     │       suggestions }          │                            │
     │                              │                            │
     └── Display in AIInsightsCard
```

## Backend Implementation

### Add to `requirements.txt`

```
google-generativeai>=0.8.0
python-dotenv>=1.0.0
```

### Create `.env` file in project root

```env
GEMINI_API_KEY=your_api_key_here
```

Get a free key from: https://aistudio.google.com/apikey

### Add to `src/api/main.py`

```python
import json
import os

from dotenv import load_dotenv

load_dotenv()  # Load .env file


@app.post("/api/insights")
async def get_insights(analysis: dict):
    """Generate AI health insights from analysis results using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return JSONResponse(
            content={"summary": "AI insights unavailable (no API key configured)",
                     "alerts": [], "suggestions": [], "emoji": "⚪"},
            status_code=200,
        )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = _build_insights_prompt(analysis)
        response = model.generate_content(prompt)

        # Parse JSON from Gemini's response
        text = response.text.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(text)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error("Gemini API failed: %s", e)
        return JSONResponse(
            content={"summary": "AI analysis temporarily unavailable.",
                     "alerts": [], "suggestions": [], "emoji": "⚪"},
            status_code=200,
        )


def _build_insights_prompt(data: dict) -> str:
    """Build the Gemini prompt from analysis results."""
    hrv = data.get("hrv") or {}

    return f"""You are a wellness assistant for PulseGuard, a contact-free 
cardiac monitoring app. Analyze these measurements from a 30-second video 
and provide health insights.

MEASUREMENTS:
- Heart Rate: {data.get('bpm', 'N/A')} BPM (normal resting: 60-100)
- Signal Quality: {data.get('sqi_level', 'N/A')} ({data.get('sqi_score', 0):.0%})
- RMSSD: {hrv.get('rmssd', 'N/A')} ms (normal: 19-75, higher = more relaxed)
- SDNN: {hrv.get('sdnn', 'N/A')} ms (normal: 30-100, higher = better adaptability)  
- pNN50: {hrv.get('pnn50', 'N/A')}% (normal: 1-50%)
- LF/HF Ratio: {hrv.get('lf_hf_ratio', 'N/A')} (normal: 0.5-2.0, higher = more stressed)
- Stress Level: {data.get('stress_level', 'N/A')} (confidence: {data.get('stress_confidence', 0):.0%})

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "summary": "2-3 sentence plain-language summary of cardiac state",
  "alerts": ["list of concerning values, empty if all normal"],
  "suggestions": ["2-3 actionable wellness tips based on the data"],
  "emoji": "🟢 for good, 🟡 for caution, 🔴 for concern"
}}

RULES:
- Be encouraging but honest
- NEVER diagnose medical conditions
- Always end summary with: "This is not medical advice."
- Keep language simple — user may not know medical terms
- If stress is HIGH, suggest breathing exercises or breaks
- If heart rate is elevated, suggest hydration and rest"""
```

## App Component

### `src/components/AIInsightsCard.js`

```javascript
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { COLORS } from '../theme/colors';
import { getInsights } from '../services/api';

export default function AIInsightsCard({ analysisResult }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInsights(analysisResult)
      .then(setInsights)
      .catch(() => setInsights(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <View style={styles.card}>
        <ActivityIndicator color={COLORS.accent} />
        <Text style={styles.loadText}>Generating AI insights...</Text>
      </View>
    );
  }

  if (!insights) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.header}>🤖 AI Health Insights</Text>

      <Text style={styles.emoji}>{insights.emoji}</Text>
      <Text style={styles.summary}>{insights.summary}</Text>

      {insights.alerts?.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>⚠️ Alerts</Text>
          {insights.alerts.map((a, i) => (
            <Text key={i} style={styles.alertText}>• {a}</Text>
          ))}
        </View>
      )}

      {insights.suggestions?.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>💡 Suggestions</Text>
          {insights.suggestions.map((s, i) => (
            <Text key={i} style={styles.sugText}>• {s}</Text>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card:         { backgroundColor: 'rgba(108,156,252,0.08)', borderRadius: 12,
                  borderWidth: 1, borderColor: 'rgba(108,156,252,0.2)',
                  padding: 20, marginBottom: 12 },
  header:       { fontSize: 16, fontWeight: '600', color: COLORS.accent,
                  marginBottom: 12 },
  emoji:        { fontSize: 28, textAlign: 'center', marginBottom: 8 },
  summary:      { fontSize: 14, color: COLORS.textPrimary, lineHeight: 20,
                  marginBottom: 12 },
  section:      { marginTop: 8 },
  sectionTitle: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary,
                  marginBottom: 6 },
  alertText:    { fontSize: 13, color: COLORS.warning, marginBottom: 3 },
  sugText:      { fontSize: 13, color: COLORS.textSecondary, marginBottom: 3 },
  loadText:     { color: COLORS.textSecondary, textAlign: 'center',
                  marginTop: 8, fontSize: 13 },
});
```

Then add to `ResultsScreen.js`:
```javascript
import AIInsightsCard from '../components/AIInsightsCard';

// In the JSX, after StressIndicator:
<AIInsightsCard analysisResult={result} />
```

## Testing Checklist

- [ ] Get Gemini API key from aistudio.google.com
- [ ] Set key in `.env` file
- [ ] `POST /api/insights` returns valid JSON
- [ ] AIInsightsCard shows loading spinner, then content
- [ ] Gracefully handles missing API key (shows fallback message)
- [ ] Gracefully handles Gemini API errors
- [ ] Response includes summary, alerts, suggestions
