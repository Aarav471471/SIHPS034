/**
 * First-run tour.
 *
 * Enforcement software is not self-evident. An officer opening this for the
 * first time needs to know that the app proposes and they dispose — that a
 * score is a starting point for an inspection, not a verdict issued by a model.
 * Getting that across once, up front, is worth more than tooltips scattered
 * across six screens.
 *
 * It shows once per role and is re-openable from the command palette, because a
 * tour that cannot be replayed is a tour nobody dares skip.
 */
import clsx from 'clsx';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { create } from 'zustand';

import { Icon, type IconName } from '@/components/icons';
import { AnimatePresence, EASE, Overlay, SPRING, motion } from '@/components/motion';
import { useAuth } from '@/store/auth';

interface Step {
  eyebrow: string;
  title: string;
  body: string;
  icon: IconName;
  /** Rendered under the copy — a small, honest illustration of the idea. */
  figure?: 'pipeline' | 'scale' | 'evidence' | 'route';
}

const COMMON_CLOSE: Step = {
  eyebrow: 'Ground rule',
  title: 'The model proposes. The rules decide.',
  body:
    'Nothing here is issued on a model\'s word. A vision pass reads the pack, a '
    + 'second OCR pass re-reads the same pixels independently, and only then does '
    + 'deterministic code apply the Rules. Where the two readings disagree, '
    + 'confidence is capped below the auto-accept threshold and a human is asked.',
  icon: 'scale',
  figure: 'pipeline',
};

const TOURS: Record<string, Step[]> = {
  officer: [
    {
      eyebrow: 'Welcome',
      title: 'A shift\'s worth of inspections, in one place.',
      body:
        'MetriX checks packaged commodities against the Legal Metrology (Packaged '
        + 'Commodities) Rules 2011. You photograph a pack; it returns a scored, '
        + 'clause-by-clause finding you can act on or overrule.',
      icon: 'shield',
    },
    {
      eyebrow: 'Capture',
      title: 'Photograph every printed surface, not just the front.',
      body:
        'Front, back and side each carry different mandatory declarations. A '
        + 'declaration missing from the surfaces you captured is reported as "not '
        + 'found on the captured surfaces" — which is legally distinct from "not '
        + 'declared". Enter the pack width and height too: without them the Rule 11 '
        + 'character-height check cannot run at all.',
      icon: 'camera',
      figure: 'evidence',
    },
    {
      eyebrow: 'Read the score',
      title: 'A number with its working shown.',
      body:
        'Each pack starts at 100 and loses weight per breach, scaled by severity. '
        + 'Every finding cites the clause it rests on and the exact crop of the '
        + 'photograph that evidences it, so you can quote both on the spot.',
      icon: 'chart',
      figure: 'scale',
    },
    {
      eyebrow: 'Plan the day',
      title: 'Stops ranked by risk, then ordered for travel.',
      body:
        'The patrol route draws on inspection history, citizen leads, price '
        + 'anomalies and festival windows. It tells you when it has traded risk '
        + 'order for travel time, so you can overrule it.',
      icon: 'route',
      figure: 'route',
    },
    COMMON_CLOSE,
  ],
  senior_officer: [
    {
      eyebrow: 'Welcome',
      title: 'The queue that needs a second signature.',
      body:
        'Cases reach you when confidence is borderline, a unit price is contested, '
        + 'or the penalty exposure is high. Everything else closes without you.',
      icon: 'checkCircle',
    },
    {
      eyebrow: 'Deciding',
      title: 'A written reason is part of the decision.',
      body:
        'Approve, dismiss or modify — each requires remarks, recorded against your '
        + 'name and disclosable if the notice is contested. The evidence crops sit '
        + 'directly above the decision for exactly that reason.',
      icon: 'scale',
    },
    {
      eyebrow: 'Intelligence',
      title: 'Clause rates, not raw counts.',
      body:
        'The policy view reports breaches as a rate over the inspections where the '
        + 'clause actually applied. Raw counts just tell you where you inspected '
        + 'most.',
      icon: 'chart',
      figure: 'scale',
    },
    COMMON_CLOSE,
  ],
  consumer: [
    {
      eyebrow: 'Welcome',
      title: 'Check what a label is actually claiming.',
      body:
        'Scan a barcode or photograph a pack. MetriX reads the mandatory '
        + 'declarations and tells you which ones are missing, wrong, or priced '
        + 'inconsistently with the same product elsewhere.',
      icon: 'scan',
    },
    {
      eyebrow: 'Reporting',
      title: 'A report is a lead, not an accusation.',
      body:
        'What you submit is routed to the officer for that jurisdiction, ranked by '
        + 'your reporting record. Confirmed reports raise it; unfounded ones lower '
        + 'it. That record is why verified reporters get looked at first.',
      icon: 'flag',
    },
    {
      eyebrow: 'Read the score',
      title: 'A number with its working shown.',
      body:
        'Every score breaks down into the specific declarations checked, so you can '
        + 'see exactly what was wrong rather than trusting a rating.',
      icon: 'chart',
      figure: 'scale',
    },
  ],
  brand: [
    {
      eyebrow: 'Welcome',
      title: 'Audit artwork before it reaches a shelf.',
      body:
        'Upload label artwork and MetriX runs the same checks a field officer\'s '
        + 'capture would, including the Rule 11 character-height test against your '
        + 'declared pack dimensions.',
      icon: 'building',
    },
    {
      eyebrow: 'Disputes',
      title: 'Contest a specific clause, with evidence.',
      body:
        'Every finding against your products is traceable to a clause and an image '
        + 'crop. A dispute attaches to that finding, not to the inspection as a '
        + 'whole, and is decided by a senior officer.',
      icon: 'scale',
    },
    COMMON_CLOSE,
  ],
};

const PIPELINE = ['Capture', 'Preprocess', 'AI extract', 'Verify', 'Validate', 'Review'];
const BANDS: { label: string; range: string; cls: string }[] = [
  { label: 'Compliant', range: '90–100', cls: 'bg-score-1' },
  { label: 'Minor', range: '75–89', cls: 'bg-score-2' },
  { label: 'Several', range: '60–74', cls: 'bg-score-3' },
  { label: 'Serious', range: '40–59', cls: 'bg-score-4' },
  { label: 'Severe', range: '0–39', cls: 'bg-score-5' },
];

function Figure({ kind }: { kind: NonNullable<Step['figure']> }) {
  if (kind === 'pipeline') {
    return (
      <ol className="mt-6 flex flex-wrap items-center gap-1.5">
        {PIPELINE.map((s, i) => (
          <li key={s} className="flex items-center gap-1.5">
            <span
              className={clsx(
                'chip ring-1 ring-inset',
                i < 3
                  ? 'bg-accent-soft text-accent ring-accent/20'
                  : 'bg-ok-soft text-ok ring-ok/20',
              )}
            >
              {s}
            </span>
            {i < PIPELINE.length - 1 && <Icon.chevronRight size={12} className="text-ink-faint" />}
          </li>
        ))}
      </ol>
    );
  }

  if (kind === 'scale') {
    return (
      <div className="mt-6 space-y-2">
        <div className="flex gap-1">
          {BANDS.map((b) => (
            <span key={b.label} className={clsx('h-2 flex-1 rounded-full', b.cls)} />
          ))}
        </div>
        <div className="flex justify-between">
          {BANDS.map((b) => (
            <span key={b.label} className="text-center">
              <span className="nums block text-2xs font-semibold text-ink-soft">{b.range}</span>
              <span className="block text-[0.625rem] text-ink-faint">{b.label}</span>
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (kind === 'evidence') {
    return (
      <div className="mt-6 grid grid-cols-3 gap-2">
        {['Front', 'Back', 'Side'].map((face, i) => (
          <div key={face} className="panel px-3 py-4 text-center">
            <span className="mx-auto grid size-8 place-items-center rounded-lg bg-surface text-ink-faint ring-1 ring-line">
              <Icon.camera size={15} />
            </span>
            <p className="mt-2 text-2xs font-semibold text-ink-soft">{face}</p>
            <p className="text-[0.625rem] text-ink-faint">
              {['MRP, net qty', 'Mfr, origin', 'Batch, dates'][i]}
            </p>
          </div>
        ))}
      </div>
    );
  }

  return (
    <ol className="mt-6 space-y-1.5">
      {[
        { n: 1, name: 'Gupta General Store', risk: 100, cls: 'bg-score-5' },
        { n: 2, name: 'Karol Bagh Provisions', risk: 68, cls: 'bg-score-3' },
        { n: 3, name: 'New Delhi Kirana', risk: 34, cls: 'bg-score-1' },
      ].map((s) => (
        <li key={s.n} className="panel flex items-center gap-3 px-3 py-2">
          <span className={clsx('nums grid size-6 place-items-center rounded-full text-2xs font-bold text-white', s.cls)}>
            {s.n}
          </span>
          <span className="min-w-0 flex-1 truncate text-xs font-medium">{s.name}</span>
          <span className="nums chip bg-surface text-2xs text-ink-muted ring-1 ring-inset ring-line">
            risk {s.risk}
          </span>
        </li>
      ))}
    </ol>
  );
}

function storageKey(role: string) { return `metrix.tour.${role}`; }

/** Shared so the header button and the command palette can both reopen it. */
export const useTourStore = create<{ open: boolean; show: () => void; hide: () => void }>(
  (set) => ({
    open: false,
    show: () => set({ open: true }),
    hide: () => set({ open: false }),
  }),
);

/** Opens the tour once per role, on first sight of the app. */
export function useFirstRunTour() {
  const { user } = useAuth();
  const role = user?.role ?? '';
  const show = useTourStore((s) => s.show);

  useEffect(() => {
    if (!role || !TOURS[role]) return;
    try {
      if (!localStorage.getItem(storageKey(role))) show();
    } catch {
      // Private browsing can throw on storage access; a tour is not worth
      // failing the whole shell over.
    }
  }, [role, show]);
}

export function Tour() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const open = useTourStore((s) => s.open);
  const hide = useTourStore((s) => s.hide);
  const steps = TOURS[user?.role ?? ''] ?? [];
  const [i, setI] = useState(0);

  const onClose = () => {
    hide();
    try {
      localStorage.setItem(storageKey(user?.role ?? ''), new Date().toISOString());
    } catch { /* ignore */ }
  };

  useEffect(() => { if (open) setI(0); }, [open]);

  if (!steps.length) return null;
  const step = steps[Math.min(i, steps.length - 1)];
  const last = i === steps.length - 1;
  const Glyph = Icon[step.icon];

  return (
    <Overlay open={open} onClose={onClose} labelledBy="tour-title">
      <div className="surface-raised overflow-hidden">
        {/* Progress rail. Five dots is a promise about how long this takes. */}
        <div className="flex gap-1 px-6 pt-6">
          {steps.map((s, n) => (
            <button
              key={s.title}
              type="button"
              onClick={() => setI(n)}
              aria-label={`Step ${n + 1}: ${s.title}`}
              className="group h-1 flex-1 overflow-hidden rounded-full bg-surface-sunk"
            >
              <motion.span
                className="block h-full rounded-full bg-accent"
                initial={false}
                animate={{ width: n <= i ? '100%' : '0%' }}
                transition={EASE}
              />
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step.title}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -12 }}
            transition={SPRING}
            className="px-6 pb-2 pt-6 sm:px-8"
          >
            <div className="flex items-center gap-2.5">
              <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent">
                <Glyph size={16} />
              </span>
              <span className="eyebrow">{step.eyebrow}</span>
            </div>

            <h2 id="tour-title" className="display mt-4 text-pretty text-2xl font-semibold leading-tight">
              {step.title}
            </h2>
            <p className="mt-3 text-pretty text-sm leading-relaxed text-ink-soft">
              {step.body}
            </p>

            {step.figure && <Figure kind={step.figure} />}
          </motion.div>
        </AnimatePresence>

        <div className="mt-6 flex items-center justify-between gap-3 border-t border-line px-6 py-4 sm:px-8">
          <button type="button" onClick={onClose} className="btn-subtle btn-sm">
            Skip
          </button>

          <div className="flex items-center gap-2">
            <span className="nums text-2xs text-ink-faint">
              {i + 1} of {steps.length}
            </span>
            {i > 0 && (
              <button type="button" onClick={() => setI(i - 1)} className="btn-ghost btn-sm">
                Back
              </button>
            )}
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={() => (last ? onClose() : setI(i + 1))}
            >
              {last ? 'Start working' : 'Next'}
              {!last && <Icon.arrowRight size={14} />}
            </button>
          </div>
        </div>

        {last && (
          <button
            type="button"
            onClick={() => { onClose(); navigate('/how-it-works'); }}
            className="w-full border-t border-line bg-surface-sunk px-6 py-3 text-2xs font-semibold text-ink-muted transition-colors hover:text-accent sm:px-8"
          >
            Read the full method and scoring rules →
          </button>
        )}
      </div>
    </Overlay>
  );
}
