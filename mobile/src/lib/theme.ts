// Same dark slate and emerald palette as the web app.
export const C = {
  bg: '#080d13',
  card: '#0f172a',
  cardAlt: '#020617',
  border: '#334155',
  borderSoft: '#1e293b',
  text: '#f8fafc',
  textSoft: '#cbd5e1',
  textMuted: '#94a3b8',
  textFaint: '#64748b',
  accent: '#34d399',
  accentStrong: '#10b981',
  accentBg: 'rgba(16,185,129,0.15)',
  accentBorder: 'rgba(16,185,129,0.35)',
  warn: '#fcd34d',
  warnBg: 'rgba(245,158,11,0.12)',
  warnBorder: 'rgba(245,158,11,0.3)',
  danger: '#fca5a5',
  indica: '#c4b5fd',
  sativa: '#fdba74',
  hybrid: '#6ee7b7',
} as const;

export const MONO = process.env.EXPO_OS === 'ios' ? 'Menlo' : 'monospace';
export const MIN_TAP = 44;
// The browser preview draws its tab bar over the top of the screen; phones use the system tab bar at the bottom.
export const WEB_TOP = process.env.EXPO_OS === 'web' ? 76 : 0;
