/**
 * Shared presentational primitives.
 *
 * The same vocabulary as the web app's components/ui.tsx -- Card, Verdict,
 * Chip, Stat, Empty, ErrorBox -- so a screen written here reads like a screen
 * written there, and neither surface grows its own private set of styles.
 */
import { useMemo } from 'react';
import {
  ActivityIndicator, Pressable, StyleSheet, Text, View,
  useColorScheme, type StyleProp, type TextStyle, type ViewStyle,
} from 'react-native';

import {
  BAND_BLURB, BAND_LABEL, bandFor, dark, light, radius, shadow, space,
  type Palette,
} from '@/theme';

export function usePalette(): Palette {
  const scheme = useColorScheme();
  return scheme === 'dark' ? dark : light;
}

/** Display face, with a graceful fall back to the platform serif. */
export function useDisplayFont(): TextStyle {
  return useMemo(() => ({ fontFamily: 'Fraunces_600SemiBold' }), []);
}

// ------------------------------------------------------------------ layout --
export function Card({
  children, style, tone,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  tone?: 'default' | 'sunk' | 'accent';
}) {
  const p = usePalette();
  return (
    <View
      style={[
        {
          backgroundColor:
            tone === 'sunk' ? p.surfaceSunk : tone === 'accent' ? p.accentSoft : p.surface,
          borderColor: p.line,
          borderWidth: StyleSheet.hairlineWidth * 2,
          borderRadius: radius.lg,
          padding: space.lg,
        },
        shadow.card,
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function Screen({
  children, style,
}: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  const p = usePalette();
  return <View style={[{ flex: 1, backgroundColor: p.bg }, style]}>{children}</View>;
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  const p = usePalette();
  return (
    <Text
      style={{
        color: p.inkMuted,
        fontSize: 11,
        fontWeight: '700',
        letterSpacing: 1.1,
        textTransform: 'uppercase',
      }}
    >
      {children}
    </Text>
  );
}

export function Title({
  children, size = 26, style,
}: { children: React.ReactNode; size?: number; style?: StyleProp<TextStyle> }) {
  const p = usePalette();
  const display = useDisplayFont();
  return (
    <Text style={[display, { color: p.ink, fontSize: size, lineHeight: size * 1.15 }, style]}>
      {children}
    </Text>
  );
}

export function Body({
  children, muted, style, size = 14,
}: {
  children: React.ReactNode; muted?: boolean;
  style?: StyleProp<TextStyle>; size?: number;
}) {
  const p = usePalette();
  return (
    <Text style={[{ color: muted ? p.inkMuted : p.inkSoft, fontSize: size, lineHeight: size * 1.5 }, style]}>
      {children}
    </Text>
  );
}

// ------------------------------------------------------------------ verdict --
/**
 * The score block. Deliberately the same shape as the web `Verdict`: a large
 * banded figure, the plain-language band beneath it, and the ramp shown in
 * place so the number is interpretable without a legend elsewhere.
 */
export function Verdict({
  score, title, subtitle, state = 'scored', note,
}: {
  score?: number | null;
  title: string;
  subtitle?: string;
  state?: 'scored' | 'pending' | 'unassessable';
  note?: string;
}) {
  const p = usePalette();
  const display = useDisplayFont();
  const band = bandFor(score);
  const withheld = state !== 'scored';
  const colour = withheld ? p.inkFaint : p.score[band];

  return (
    <Card>
      <View style={{ flexDirection: 'row', gap: space.lg, alignItems: 'flex-start' }}>
        <View style={{ minWidth: 96 }}>
          <View style={{ flexDirection: 'row', alignItems: 'baseline' }}>
            <Text style={[display, { color: colour, fontSize: 52, lineHeight: 54 }]}>
              {withheld || score == null ? '—' : Math.round(score)}
            </Text>
            {!withheld && score != null && (
              <Text style={{ color: p.inkFaint, fontSize: 13, fontWeight: '600' }}>/100</Text>
            )}
          </View>
          <Text style={{ color: withheld ? p.inkMuted : colour, fontWeight: '700', fontSize: 13, marginTop: 2 }}>
            {state === 'pending' ? 'Checking'
              : state === 'unassessable' ? 'Not assessable'
                : BAND_LABEL[band]}
          </Text>
          <Text style={{ color: p.inkMuted, fontSize: 11, lineHeight: 15, marginTop: 2 }}>
            {state === 'pending' ? 'The rules engine has not finished'
              : state === 'unassessable' ? 'Nothing could be read from the evidence'
                : BAND_BLURB[band]}
          </Text>

          {!withheld && (
            <View style={{ flexDirection: 'row', gap: 3, marginTop: space.md }}>
              {p.score.map((c, i) => (
                <View
                  key={c}
                  style={{
                    flex: 1, height: 5, borderRadius: 3, backgroundColor: c,
                    opacity: i === band ? 1 : 0.22,
                  }}
                />
              ))}
            </View>
          )}
        </View>

        <View style={{ flex: 1, minWidth: 0 }}>
          <Title size={20}>{title}</Title>
          {subtitle && <Body muted style={{ marginTop: 3 }} size={13}>{subtitle}</Body>}
        </View>
      </View>

      {note && (
        <Text
          style={{
            color: p.inkMuted, fontSize: 12, lineHeight: 17,
            marginTop: space.lg, paddingTop: space.md,
            borderTopWidth: StyleSheet.hairlineWidth * 2, borderTopColor: p.line,
          }}
        >
          {note}
        </Text>
      )}
    </Card>
  );
}

// -------------------------------------------------------------------- chips --
type ChipTone = 'neutral' | 'ok' | 'warn' | 'bad' | 'info' | 'accent';

export function Chip({
  children, tone = 'neutral', icon,
}: { children: React.ReactNode; tone?: ChipTone; icon?: React.ReactNode }) {
  const p = usePalette();
  const map: Record<ChipTone, [string, string]> = {
    neutral: [p.surfaceSunk, p.inkMuted],
    ok: [p.okSoft, p.ok],
    warn: [p.warnSoft, p.warn],
    bad: [p.badSoft, p.bad],
    info: [p.infoSoft, p.info],
    accent: [p.accentSoft, p.accent],
  };
  const [bg, fg] = map[tone];
  return (
    <View
      style={{
        flexDirection: 'row', alignItems: 'center', gap: 4,
        backgroundColor: bg, borderRadius: radius.pill,
        paddingHorizontal: 9, paddingVertical: 4,
      }}
    >
      {icon}
      <Text style={{ color: fg, fontSize: 11, fontWeight: '700', letterSpacing: 0.2 }}>
        {children}
      </Text>
    </View>
  );
}

/** Maps an API status string onto a tone, mirroring the web StatusChip. */
export function StatusChip({ status }: { status?: string | null }) {
  if (!status) return null;
  const tone: ChipTone =
    ['COMPLIANT', 'COMPLETED', 'VERIFIED', 'UPLOADED'].includes(status) ? 'ok'
      : ['NON_COMPLIANT', 'FLAGGED', 'FAILED', 'PRIORITY'].includes(status) ? 'bad'
        : ['WARNING', 'INVESTIGATING', 'LEAD'].includes(status) ? 'warn'
          : ['PROCESSING', 'SUBMITTED', 'UPLOADING', 'PEER_REVIEW'].includes(status) ? 'info'
            : 'neutral';
  return <Chip tone={tone}>{status.replace(/_/g, ' ')}</Chip>;
}

// ------------------------------------------------------------------ actions --
export function Button({
  label, onPress, tone = 'primary', disabled, busy, style, icon,
}: {
  label: string;
  onPress?: () => void;
  tone?: 'primary' | 'ghost' | 'danger' | 'ok';
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
  icon?: React.ReactNode;
}) {
  const p = usePalette();
  const map = {
    primary: [p.accent, p.accentFg, p.accent],
    ghost: [p.surface, p.inkSoft, p.lineStrong],
    danger: [p.bad, '#fff', p.bad],
    ok: [p.ok, '#fff', p.ok],
  } as const;
  const [bg, fg, border] = map[tone];
  const off = disabled || busy;

  return (
    <Pressable
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [
        {
          flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
          gap: space.sm,
          backgroundColor: bg, borderColor: border,
          borderWidth: StyleSheet.hairlineWidth * 2,
          borderRadius: radius.md,
          paddingVertical: 13, paddingHorizontal: space.lg,
          opacity: off ? 0.5 : pressed ? 0.85 : 1,
        },
        style,
      ]}
      accessibilityRole="button"
      accessibilityState={{ disabled: Boolean(off) }}
    >
      {busy ? <ActivityIndicator color={fg} size="small" /> : icon}
      <Text style={{ color: fg, fontWeight: '700', fontSize: 15 }}>{label}</Text>
    </Pressable>
  );
}

// ------------------------------------------------------------------- states --
export function Empty({
  title, hint, action,
}: { title: string; hint?: string; action?: React.ReactNode }) {
  const p = usePalette();
  return (
    <Card style={{ alignItems: 'center', paddingVertical: space.xxl }}>
      <Title size={17}>{title}</Title>
      {hint && (
        <Body muted style={{ textAlign: 'center', marginTop: space.sm }} size={13}>
          {hint}
        </Body>
      )}
      {action && <View style={{ marginTop: space.lg, alignSelf: 'stretch' }}>{action}</View>}
      <View style={{ height: 0, backgroundColor: p.line }} />
    </Card>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const p = usePalette();
  const message = error instanceof Error ? error.message : String(error ?? 'Something went wrong');
  return (
    <Card style={{ borderColor: p.bad, backgroundColor: p.badSoft }}>
      <Text style={{ color: p.bad, fontWeight: '700', fontSize: 14 }}>{message}</Text>
      {onRetry && (
        <Button label="Try again" tone="ghost" onPress={onRetry} style={{ marginTop: space.md }} />
      )}
    </Card>
  );
}

export function Loading({ label }: { label?: string }) {
  const p = usePalette();
  return (
    <View style={{ padding: space.xxl, alignItems: 'center', gap: space.md }}>
      <ActivityIndicator color={p.accent} />
      {label && <Body muted size={13}>{label}</Body>}
    </View>
  );
}

export function Callout({
  tone = 'info', title, children,
}: { tone?: 'info' | 'warn' | 'bad' | 'ok'; title?: string; children?: React.ReactNode }) {
  const p = usePalette();
  const map = {
    info: [p.infoSoft, p.info],
    warn: [p.warnSoft, p.warn],
    bad: [p.badSoft, p.bad],
    ok: [p.okSoft, p.ok],
  } as const;
  const [bg, fg] = map[tone];
  return (
    <View
      style={{
        backgroundColor: bg, borderRadius: radius.md,
        borderLeftWidth: 3, borderLeftColor: fg,
        padding: space.md,
      }}
    >
      {title && <Text style={{ color: fg, fontWeight: '700', fontSize: 13.5 }}>{title}</Text>}
      {typeof children === 'string'
        ? <Text style={{ color: fg, fontSize: 12.5, lineHeight: 18, marginTop: title ? 3 : 0 }}>{children}</Text>
        : children}
    </View>
  );
}

// --------------------------------------------------------------- formatters --
export function money(v?: number | null): string {
  if (v == null) return '—';
  return `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function moneyShort(v?: number | null): string {
  if (v == null) return '—';
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}k`;
  return `₹${Math.round(v).toLocaleString('en-IN')}`;
}

export function when(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function ago(iso?: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return when(iso);
}
