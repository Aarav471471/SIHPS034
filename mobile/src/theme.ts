/**
 * Design tokens, mirrored from the web app's `index.css`.
 *
 * Kept as literal hex rather than imported, because React Native has no CSS
 * custom properties and no runtime hsl() -- but the VALUES are the same warm
 * paper palette and the same five-band compliance ramp, so an officer moving
 * between the phone and the console sees one product rather than two.
 *
 * If a token changes in web/src/index.css it must change here too. That
 * duplication is deliberate: the alternative is a build step that would make
 * the Expo project depend on the web project's toolchain.
 */

export interface Palette {
  bg: string;
  bgSubtle: string;
  surface: string;
  surfaceSunk: string;
  line: string;
  lineStrong: string;
  ink: string;
  inkSoft: string;
  inkMuted: string;
  inkFaint: string;
  accent: string;
  accentSoft: string;
  accentFg: string;
  ok: string;
  okSoft: string;
  warn: string;
  warnSoft: string;
  bad: string;
  badSoft: string;
  info: string;
  infoSoft: string;
  /** Five-band compliance ramp: index 0 is the clean end, 4 the severe end. */
  score: [string, string, string, string, string];
  /** Scrim over camera preview -- the one place a literal black is correct. */
  scrim: string;
}

export const light: Palette = {
  bg: '#f9f6f1',
  bgSubtle: '#f2ede4',
  surface: '#ffffff',
  surfaceSunk: '#f5f1ea',
  line: '#e8e2d9',
  lineStrong: '#cdc5ba',
  ink: '#1f1b18',
  inkSoft: '#4a453f',
  inkMuted: '#7a736b',
  inkFaint: '#a89f94',
  accent: '#19306b',
  accentSoft: '#eef1f9',
  accentFg: '#ffffff',
  ok: '#1d6b45',
  okSoft: '#e9f5ee',
  warn: '#a75a10',
  warnSoft: '#fbf0dd',
  bad: '#b82a24',
  badSoft: '#fbebe9',
  info: '#1a5fbf',
  infoSoft: '#e9f0fc',
  score: ['#20794f', '#5b7a29', '#b78a0b', '#c86518', '#b82f29'],
  scrim: 'rgba(0,0,0,0.55)',
};

export const dark: Palette = {
  bg: '#141210',
  bgSubtle: '#1a1715',
  surface: '#221e1b',
  surfaceSunk: '#1a1715',
  line: '#3d3834',
  lineStrong: '#565049',
  ink: '#f5f3ef',
  inkSoft: '#cdc6bd',
  inkMuted: '#9d958b',
  inkFaint: '#726b63',
  accent: '#7fa5ef',
  accentSoft: '#1b2740',
  accentFg: '#12161f',
  ok: '#57c48c',
  okSoft: '#16281f',
  warn: '#e5a33c',
  warnSoft: '#2a2015',
  bad: '#e8756c',
  badSoft: '#2b1917',
  info: '#6fa8f5',
  infoSoft: '#152234',
  score: ['#57c48c', '#9ec45f', '#efc143', '#ef9a52', '#e8756c'],
  scrim: 'rgba(0,0,0,0.6)',
};

/** Band index 0-4 for a 0-100 compliance score. Mirrors `bandFor` on the web. */
export function bandFor(score?: number | null): 0 | 1 | 2 | 3 | 4 {
  if (score == null) return 2;
  const v = Math.max(0, Math.min(100, score));
  if (v >= 90) return 0;
  if (v >= 75) return 1;
  if (v >= 60) return 2;
  if (v >= 40) return 3;
  return 4;
}

export const BAND_LABEL = [
  'Compliant',
  'Minor issues',
  'Several breaches',
  'Serious breaches',
  'Severe breaches',
] as const;

export const BAND_BLURB = [
  'Every applicable declaration present and correct',
  'Small defects, nothing that misleads a buyer',
  'Declarations missing or wrong enough to mislead',
  'Multiple contraventions including price or quantity',
  'Pervasive contravention across the pack',
] as const;

/**
 * Risk uses the same ramp inverted -- a risk of 80 is where a score of 20 would
 * sit. Getting this backwards paints the worst shop green, so it lives in one
 * place rather than being re-derived per screen.
 */
export function riskBand(risk: number): 0 | 1 | 2 | 3 | 4 {
  if (risk >= 70) return 4;
  if (risk >= 40) return 2;
  return 0;
}

export const space = {
  xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32,
} as const;

export const radius = { sm: 8, md: 12, lg: 14, xl: 20, pill: 999 } as const;

export const type = {
  display: 'Fraunces_600SemiBold',
  displayFallback: 'serif',
  body: undefined as string | undefined,   // system sans
  mono: undefined as string | undefined,
} as const;

/** Shadow that reads on both platforms without looking like a sticker. */
export const shadow = {
  card: {
    shadowColor: '#1f1b18',
    shadowOpacity: 0.07,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  raised: {
    shadowColor: '#1f1b18',
    shadowOpacity: 0.12,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
} as const;
