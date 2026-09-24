/** Shared presentational primitives, built on the token system. */
import clsx from 'clsx';
import type { ReactNode } from 'react';

import { Icon } from '@/components/icons';
import { Counter, Item, Lift, Stagger, motion } from '@/components/motion';
import type { BadgeLevel, Severity } from '@shared/types';

// ============================================================== badges =====
const BADGE: Record<string, string> = {
  GOLD: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 ring-amber-500/25',
  SILVER: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 ring-slate-500/25',
  BRONZE: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 ring-orange-500/25',
  STANDARD: 'bg-info/10 text-info ring-info/25',
  FLAGGED: 'bg-bad/10 text-bad ring-bad/25',
};

export function ComplianceBadge({
  level, score, size = 'md',
}: { level?: BadgeLevel | null; score?: number | null; size?: 'sm' | 'md' }) {
  const key = level ?? 'STANDARD';
  return (
    <span
      className={clsx(
        'chip ring-1 ring-inset', BADGE[key] ?? BADGE.STANDARD,
        size === 'sm' && 'px-2 py-0.5 text-[0.625rem]',
      )}
    >
      {key}
      {score != null && <span className="nums opacity-70">{score}</span>}
    </span>
  );
}

const SEVERITY: Record<string, string> = {
  CRITICAL: 'bg-bad/10 text-bad ring-bad/25',
  MAJOR: 'bg-warn/10 text-warn ring-warn/25',
  MINOR: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 ring-amber-500/25',
};

export function SeverityChip({ severity }: { severity?: Severity | null }) {
  return (
    <span className={clsx('chip ring-1 ring-inset', SEVERITY[severity ?? 'MAJOR'])}>
      {severity ?? 'MAJOR'}
    </span>
  );
}

const STATUS: Record<string, string> = {
  COMPLIANT: 'bg-ok/10 text-ok ring-ok/25',
  NON_COMPLIANT: 'bg-bad/10 text-bad ring-bad/25',
  WARNING: 'bg-warn/10 text-warn ring-warn/25',
  PENDING: 'bg-ink-muted/10 text-ink-muted ring-ink-muted/20',
  PROCESSING: 'bg-info/10 text-info ring-info/25',
  COMPLETED: 'bg-ok/10 text-ok ring-ok/25',
  FLAGGED: 'bg-bad/10 text-bad ring-bad/25',
  PEER_REVIEW: 'bg-violet-500/10 text-violet-700 dark:text-violet-400 ring-violet-500/25',
  APPEALED: 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 ring-indigo-500/25',
  RESOLVED: 'bg-ink-muted/10 text-ink-muted ring-ink-muted/20',
  FAILED: 'bg-bad/10 text-bad ring-bad/25',
  SUBMITTED: 'bg-info/10 text-info ring-info/25',
  VERIFIED: 'bg-ok/10 text-ok ring-ok/25',
  INVESTIGATING: 'bg-warn/10 text-warn ring-warn/25',
  REJECTED: 'bg-ink-muted/10 text-ink-muted ring-ink-muted/20',
  PRIORITY: 'bg-bad/10 text-bad ring-bad/25',
  LEAD: 'bg-warn/10 text-warn ring-warn/25',
  WATCH: 'bg-ink-muted/10 text-ink-muted ring-ink-muted/20',
  UPLOADING: 'bg-info/10 text-info ring-info/25',
  UPLOADED: 'bg-ok/10 text-ok ring-ok/25',
};

export function StatusChip({ status, dot }: { status?: string | null; dot?: boolean }) {
  if (!status) return null;
  const cls = STATUS[status] ?? STATUS.PENDING;
  return (
    <span className={clsx('chip ring-1 ring-inset', cls)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {status.replace(/_/g, ' ')}
    </span>
  );
}

// =============================================================== score =====
export function ScoreRing({
  score, size = 64, label,
}: { score?: number | null; size?: number; label?: string }) {
  const value = Math.max(0, Math.min(100, score ?? 0));
  // Same five-band ramp the Verdict block uses, so a ring in a list and the
  // hero score on the detail page can never disagree about what 62 means.
  const tone = `var(--score-${bandFor(score)})`;
  const stroke = size >= 60 ? 5 : 4;
  const r = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90 overflow-visible">
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="hsl(var(--border))" strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={`hsl(${tone})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - value / 100) }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center leading-none">
        <div className="text-center">
          <div
            className="nums font-bold"
            style={{ color: `hsl(${tone})`, fontSize: size / 3.4 }}
          >
            {score == null ? '—' : <Counter value={value} />}
          </div>
          {label && size >= 64 && (
            <div className="mt-0.5 text-[0.5rem] font-semibold uppercase tracking-wider text-ink-faint">
              {label}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ================================================================ stat =====
type Tone = 'default' | 'good' | 'warn' | 'bad' | 'accent';

const TONE_TEXT: Record<Tone, string> = {
  default: 'text-ink', good: 'text-ok', warn: 'text-warn',
  bad: 'text-bad', accent: 'text-accent',
};

export function Stat({
  label, value, hint, tone = 'default', icon, delta, className,
}: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: Tone;
  icon?: keyof typeof Icon; delta?: number | null; className?: string;
}) {
  const Glyph = icon ? Icon[icon] : null;
  return (
    <Item className={clsx('surface sheen group relative overflow-hidden p-4', className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-2xs font-semibold uppercase tracking-wider text-ink-muted">
            {label}
          </p>
          <p className={clsx('nums mt-1.5 text-2xl font-bold leading-none', TONE_TEXT[tone])}>
            {value}
          </p>
        </div>
        {Glyph && (
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface-sunk text-ink-faint transition-colors group-hover:text-accent">
            <Glyph size={17} />
          </span>
        )}
      </div>

      {(hint || delta != null) && (
        <div className="mt-2.5 flex items-center gap-1.5 text-2xs text-ink-muted">
          {delta != null && delta !== 0 && (
            <span className={clsx(
              'inline-flex items-center gap-0.5 font-semibold',
              delta > 0 ? 'text-ok' : 'text-bad',
            )}>
              {delta > 0 ? <Icon.arrowUp size={11} /> : <Icon.arrowDown size={11} />}
              {Math.abs(delta).toFixed(1)}
            </span>
          )}
          {hint}
        </div>
      )}
    </Item>
  );
}

// =============================================================== cards =====
export function Card({
  children, className, interactive, ...rest
}: {
  children: ReactNode; className?: string; interactive?: boolean;
} & React.HTMLAttributes<HTMLDivElement>) {
  const content = (
    <div
      className={clsx(
        'surface sheen',
        interactive && 'transition-colors hover:border-line-strong',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
  return interactive ? <Lift>{content}</Lift> : content;
}

export function Section({
  title, subtitle, action, children, className,
}: {
  title: string; subtitle?: string; action?: ReactNode;
  children: ReactNode; className?: string;
}) {
  return (
    <section className={clsx('space-y-3.5', className)}>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="display text-xl font-semibold">{title}</h2>
          {subtitle && (
            <p className="mt-1 max-w-2xl text-pretty text-sm leading-relaxed text-ink-muted">
              {subtitle}
            </p>
          )}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function PageHeader({
  title, subtitle, action, eyebrow,
}: {
  title: string; subtitle?: string; action?: ReactNode; eyebrow?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <h1 className="display text-display-sm font-semibold">{title}</h1>
        {subtitle && (
          <p className="mt-1.5 max-w-2xl text-pretty text-sm leading-relaxed text-ink-muted">
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="flex shrink-0 flex-wrap gap-2">{action}</div>}
    </header>
  );
}

// ============================================================ verdicts =====
/**
 * The compliance ramp.
 *
 * Five bands rather than pass/fail, because a score is a measurement and 74 and
 * 41 are not the same failure. The wording is what an officer would write in a
 * report, not a colour name -- "Serious contraventions" is actionable where
 * "orange" is not.
 */
export type Band = 1 | 2 | 3 | 4 | 5;

const BANDS: Record<Band, { label: string; blurb: string; min: number }> = {
  1: { label: 'Compliant', blurb: 'Every applicable declaration present and correct', min: 90 },
  2: { label: 'Minor issues', blurb: 'Technically deficient, no consumer harm established', min: 75 },
  3: { label: 'Several breaches', blurb: 'Multiple declarations deficient or missing', min: 60 },
  4: { label: 'Serious breaches', blurb: 'Mandatory declarations absent or misstated', min: 40 },
  5: { label: 'Severe breaches', blurb: 'Consumer-facing misdeclaration; prosecution range', min: 0 },
};

export function bandFor(score?: number | null): Band {
  if (score == null) return 3;
  const v = Math.max(0, Math.min(100, score));
  if (v >= 90) return 1;
  if (v >= 75) return 2;
  if (v >= 60) return 3;
  if (v >= 40) return 4;
  return 5;
}

export const bandMeta = (b: Band) => BANDS[b];

const BAND_TEXT: Record<Band, string> = {
  1: 'text-score-1', 2: 'text-score-2', 3: 'text-score-3', 4: 'text-score-4', 5: 'text-score-5',
};
const BAND_BG: Record<Band, string> = {
  1: 'bg-score-1', 2: 'bg-score-2', 3: 'bg-score-3', 4: 'bg-score-4', 5: 'bg-score-5',
};

/**
 * Verdict block -- the hero of any page that judges something.
 *
 * The score leads at display size because it is the answer to the question the
 * page exists to settle, and everything else on the page is the working behind
 * it. The plain-language band sits directly under the number so the figure is
 * never left to be interpreted; a 62 means nothing on its own.
 */
export function Verdict({
  score, title, subtitle, meta, aside, note, state = 'scored',
}: {
  score?: number | null;
  title: string;
  subtitle?: ReactNode;
  meta?: ReactNode;
  aside?: ReactNode;
  note?: ReactNode;
  /**
   * Why there is no verdict yet.
   * `pending` -- the checks have not finished. `unassessable` -- they finished
   * and there was nothing to check. Both withhold the score rather than
   * defaulting it, because a band rendered over a null score reads as a real
   * finding to anyone glancing at the page.
   */
  state?: 'scored' | 'pending' | 'unassessable';
}) {
  const band = bandFor(score);
  const m = BANDS[band];
  const withheld = state !== 'scored';

  return (
    <Item className="surface sheen overflow-hidden">
      <div className="grid gap-6 p-6 md:grid-cols-[auto_1fr] md:gap-8 lg:p-8">
        {/* ------------------------------------------------- the number -- */}
        <div className="flex items-center gap-5 md:flex-col md:items-start md:gap-3">
          <div className="relative">
            <div
              className={clsx(
                'display text-display-lg font-semibold leading-none nums lg:text-display-xl',
                withheld ? 'text-ink-faint' : BAND_TEXT[band],
              )}
            >
              {withheld || score == null ? '—' : <Counter value={Math.round(score)} />}
            </div>
            {!withheld && score != null && (
              <span className="absolute -right-6 bottom-1.5 text-xs font-semibold text-ink-faint">
                /100
              </span>
            )}
          </div>

          <div className="md:w-full">
            <p className={clsx('text-sm font-bold', withheld ? 'text-ink-muted' : BAND_TEXT[band])}>
              {state === 'pending' ? 'Checking' : state === 'unassessable' ? 'Not assessable' : m.label}
            </p>
            <p className="mt-0.5 max-w-[22ch] text-pretty text-2xs leading-snug text-ink-muted">
              {state === 'pending'
                ? 'The rules engine has not finished'
                : state === 'unassessable'
                  ? 'Nothing could be read from the evidence'
                  : m.blurb}
            </p>

            {/* The ramp, shown in place. Someone seeing a 62 should be able to
                tell at a glance how far from clean that is without hunting for
                a methodology page. */}
            {!withheld && (
              <div className="mt-3 flex w-full max-w-[13rem] gap-1" aria-hidden="true">
                {([1, 2, 3, 4, 5] as Band[]).map((b) => (
                  <span
                    key={b}
                    className={clsx(
                      'h-1.5 flex-1 rounded-full transition-opacity',
                      BAND_BG[b],
                      b === band ? 'opacity-100' : 'opacity-20',
                    )}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* -------------------------------------------------- the claim -- */}
        <div className="min-w-0 border-t border-line pt-5 md:border-l md:border-t-0 md:pl-8 md:pt-0">
          <h1 className="display text-pretty text-display-sm font-semibold leading-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{subtitle}</p>
          )}
          {meta && <div className="mt-4 flex flex-wrap items-center gap-1.5">{meta}</div>}
          {aside && <div className="mt-5 border-t border-line pt-4">{aside}</div>}
        </div>
      </div>

      {note && (
        <div className="border-t border-line bg-surface-sunk px-6 py-3 text-2xs leading-relaxed text-ink-muted lg:px-8">
          {note}
        </div>
      )}
    </Item>
  );
}

/**
 * One judged clause.
 *
 * A coloured spine carries the severity so a page of these can be scanned
 * vertically for the serious ones, and the legal citation sits with the finding
 * rather than in a footnote -- an officer has to be able to quote it on the
 * spot, and a brand has to be able to contest exactly that clause.
 */
export function RuleRow({
  tone = 'bad', title, clause, code, children, observed, expected, action, evidence,
}: {
  tone?: 'ok' | 'warn' | 'bad' | 'muted';
  title: string;
  clause?: string | null;
  code?: string | null;
  children?: ReactNode;
  observed?: ReactNode;
  expected?: ReactNode;
  action?: ReactNode;
  evidence?: ReactNode;
}) {
  const spine = {
    ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', muted: 'bg-line-strong',
  }[tone];

  return (
    <Item className="rule-row">
      <span className={clsx('w-1 shrink-0 rounded-full', spine)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h3 className="font-semibold leading-snug">{title}</h3>
          {code && (
            <code className="font-mono text-[0.625rem] text-ink-faint">{code}</code>
          )}
          <div className="ml-auto flex shrink-0 items-center gap-1.5">{action}</div>
        </div>

        {clause && (
          <p className="mt-1 text-xs font-medium text-accent">{clause}</p>
        )}

        {children && (
          <div className="mt-2 text-pretty text-sm leading-relaxed text-ink-soft">{children}</div>
        )}

        {(observed || expected) && (
          <dl className="panel mt-3 grid grid-cols-2 gap-3 p-3 text-sm">
            <div className="min-w-0">
              <dt className="text-2xs font-semibold uppercase tracking-wider text-ink-muted">
                Observed
              </dt>
              <dd className="nums mt-0.5 truncate font-semibold">{observed ?? '—'}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-2xs font-semibold uppercase tracking-wider text-ink-muted">
                Required
              </dt>
              <dd className="nums mt-0.5 truncate font-semibold text-ok">{expected ?? '—'}</dd>
            </div>
          </dl>
        )}

        {evidence}
      </div>
    </Item>
  );
}

/** The ramp explained. Methodology in the open, the way EWG publishes theirs. */
export function ScoreScale({ className }: { className?: string }) {
  return (
    <div className={clsx('surface overflow-hidden', className)}>
      <div className="border-b border-line px-4 py-3">
        <p className="eyebrow">How the score is built</p>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">
          Each mandatory declaration under the Legal Metrology (Packaged
          Commodities) Rules 2011 is checked independently. A pack starts at 100
          and loses weight per breach, scaled by severity — so the number is a
          count of what is wrong, not an opinion.
        </p>
      </div>
      <ul className="divide-y divide-line">
        {([1, 2, 3, 4, 5] as Band[]).map((b) => {
          const m = BANDS[b];
          const hi = b === 1 ? 100 : BANDS[(b - 1) as Band].min - 1;
          return (
            <li key={b} className="flex items-center gap-3 px-4 py-2.5">
              <span className={clsx('size-2.5 shrink-0 rounded-full', BAND_BG[b])} />
              <span className="nums w-16 shrink-0 text-xs font-semibold text-ink-soft">
                {m.min}–{hi}
              </span>
              <span className={clsx('w-32 shrink-0 text-xs font-bold', BAND_TEXT[b])}>
                {m.label}
              </span>
              <span className="min-w-0 flex-1 text-pretty text-2xs text-ink-muted">
                {m.blurb}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ============================================================== states =====
export function Empty({
  title, hint, action, icon = 'box',
}: { title: string; hint?: string; action?: ReactNode; icon?: keyof typeof Icon }) {
  const Glyph = Icon[icon];
  return (
    <div className="surface grid place-items-center gap-3 px-6 py-14 text-center">
      <span className="grid size-12 place-items-center rounded-xl bg-surface-sunk text-ink-faint">
        <Glyph size={22} />
      </span>
      <div>
        <p className="font-semibold">{title}</p>
        {hint && <p className="mx-auto mt-1 max-w-md text-pretty text-sm text-ink-muted">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

/** Skeletons mirror the shape of what is loading, so nothing jumps on arrival. */
export function Loading({ rows = 3, variant = 'list' }: { rows?: number; variant?: 'list' | 'stats' }) {
  if (variant === 'stats') {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="surface p-4">
            <div className="skeleton h-3 w-20" />
            <div className="skeleton mt-3 h-7 w-16" />
            <div className="skeleton mt-3 h-2.5 w-24" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="surface flex items-center gap-4 p-4">
          <div className="skeleton size-12 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3.5 w-1/3" />
            <div className="skeleton h-2.5 w-2/3" />
            <div className="skeleton h-2.5 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error ?? 'Something went wrong');
  return (
    <div className="surface flex items-start gap-3 border-bad/30 bg-bad-soft p-4">
      <span className="mt-0.5 shrink-0 text-bad"><Icon.alert size={18} /></span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-bad">{message}</p>
        {retry && (
          <button type="button" onClick={retry} className="btn-ghost btn-sm mt-3">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function Callout({
  tone = 'info', title, children, icon,
}: {
  tone?: 'info' | 'warn' | 'bad' | 'ok'; title?: string;
  children: ReactNode; icon?: keyof typeof Icon;
}) {
  const styles = {
    info: 'border-info/25 bg-info-soft text-info',
    warn: 'border-warn/25 bg-warn-soft text-warn',
    bad: 'border-bad/25 bg-bad-soft text-bad',
    ok: 'border-ok/25 bg-ok-soft text-ok',
  }[tone];
  const Glyph = Icon[icon ?? (tone === 'ok' ? 'checkCircle' : tone === 'info' ? 'info' : 'alert')];

  return (
    <div className={clsx('surface flex items-start gap-3 p-4', styles)}>
      <span className="mt-0.5 shrink-0"><Glyph size={18} /></span>
      <div className="min-w-0 flex-1 text-sm">
        {title && <p className="font-semibold">{title}</p>}
        <div className={clsx('text-pretty leading-relaxed', title && 'mt-1 opacity-90')}>
          {children}
        </div>
      </div>
    </div>
  );
}

/** Horizontal meter, used for rates and progress. */
export function Meter({
  value, tone, className,
}: { value: number; tone?: 'ok' | 'warn' | 'bad' | 'accent'; className?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  const auto = pct >= 50 ? 'bad' : pct >= 20 ? 'warn' : 'ok';
  const colour = {
    ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', accent: 'bg-accent',
  }[tone ?? auto];

  return (
    <div className={clsx('h-1.5 w-full overflow-hidden rounded-full bg-surface-sunk', className)}>
      <motion.div
        className={clsx('h-full rounded-full', colour)}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      />
    </div>
  );
}

export { Stagger, Item, Lift, Counter };

// =========================================================== formatters ====
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
