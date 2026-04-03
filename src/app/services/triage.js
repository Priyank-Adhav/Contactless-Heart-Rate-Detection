// Smart Triage System
// See docs/app/07_triage_user_modes.md for full logic documentation
//
// Combines all vitals into a single triage level:
//
// 🔴 CRITICAL — HR > 120, HR < 45, HIGH stress + HR > 100, RMSSD < 12
// 🟡 ELEVATED — MODERATE stress, HR > 100, RMSSD < 20, LF/HF > 4.0
// 🟢 STABLE   — everything within normal ranges
//
// Usage:
//   import { computeTriage } from '../services/triage';
//   const triage = computeTriage(apiResult);
//   // triage = { level: 'STABLE', emoji: '🟢', action: '...', details: [...] }

export function computeTriage(result) {
  // TODO: Implement full triage logic from docs/app/07_triage_user_modes.md

  // Placeholder — returns STABLE for now
  return {
    level: 'STABLE',
    emoji: '🟢',
    action: 'All vitals normal',
    details: ['Placeholder — implement from docs/app/07_triage_user_modes.md'],
  };
}
