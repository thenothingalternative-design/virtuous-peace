// Nothing Alternative — Design System
// Matches desktop app (nothing_alternative_mac.py / nothing_alternative_windows.py) exactly

export const Colors = {
  // Backgrounds
  bgBase:    '#0e0e0f',
  bgSurface: '#16161a',
  bgRaised:  '#1c1c22',
  border:    '#2a2a2e',

  // Accent
  accent:    '#3a3aff',
  accentHvr: '#5555ff',

  // Status
  green: '#00e676',
  red:   '#ee4455',
  amber: '#ffaa33',

  // Text
  textPri: '#ffffff',
  textSec: '#8888aa',
  textMut: '#3a3a44',

  // Subscription badge colours
  subTrial:   '#5555cc',
  subPremium: '#00e676',
  subUpgrade: '#ffaa33',

  // Chip backgrounds
  chipAllowedBg:     '#1c1c22',
  chipAllowedBorder: '#3a3aff',
  chipAllowedText:   '#7a7aff',
  chipBlockedBg:     '#1e0e10',
  chipBlockedBorder: '#3a1820',
  chipBlockedText:   '#aa4455',

  // Log colours
  logSystem:  '#3a3aff',
  logSniper:  '#ee4455',
  logBlocker: '#ffaa33',
} as const;

export const Fonts = {
  sans:     'DMSans',
  sansBold: 'DMSans-Bold',
  mono:     'DMMono',
} as const;

export const FontSizes = {
  xs:  9,
  sm:  11,
  md:  13,
  lg:  15,
  xl:  18,
  xxl: 22,
  h1:  28,
} as const;

export const Radius = {
  sm:  6,
  md:  10,
  lg:  14,
  pill: 999,
} as const;

export const Spacing = {
  xs:  4,
  sm:  8,
  md:  16,
  lg:  24,
  xl:  32,
} as const;

// Reusable shadow (subtle, dark-theme friendly)
export const shadow = {
  shadowColor: '#000',
  shadowOffset: { width: 0, height: 2 },
  shadowOpacity: 0.3,
  shadowRadius: 4,
  elevation: 4,
};
