/**
 * Method and scoring, in the open.
 *
 * An enforcement score that cannot be interrogated is worth very little: the
 * brand it penalises will contest it, and the officer relying on it has to be
 * able to explain it in a hearing. This page is the published method — what is
 * checked, in what order, how the number is produced, and what the system
 * refuses to decide on its own.
 */
import { Link } from 'react-router-dom';

import { Icon, type IconName } from '@/components/icons';
import { Item, Page, Stagger } from '@/components/motion';
import { Callout, Card, PageHeader, ScoreScale, Section } from '@/components/ui';

const STAGES: { n: number; name: string; what: string; icon: IconName }[] = [
  {
    n: 1, name: 'Capture', icon: 'camera',
    what:
      'Each printed surface is photographed and hashed with SHA-256 at the moment '
      + 'it is taken. The hash chain is what makes the evidence defensible later; '
      + 'nothing downstream can alter an image without breaking the seal.',
  },
  {
    n: 2, name: 'Preprocess', icon: 'scan',
    what:
      'The pack is located, deskewed and — where the label wraps a bottle or tin — '
      + 'unwarped from its cylinder. Glare is removed only where it is a local '
      + 'excess, never across a whole bright panel, because over-aggressive '
      + 'inpainting erases pale packaging along with the reflection.',
  },
  {
    n: 3, name: 'AI extract', icon: 'sparkle',
    what:
      'A vision model reads the declarations and returns each one with the pixel '
      + 'box it came from. This is the only step where a model has an opinion, and '
      + 'its opinion is a proposal — never a finding.',
  },
  {
    n: 4, name: 'Verify', icon: 'checkCircle',
    what:
      'A separate OCR engine re-reads the same crop, independently. Agreement '
      + 'raises confidence; disagreement caps it below the auto-accept threshold '
      + 'and routes the case to a human. A reading nobody could confirm is never '
      + 'treated as fact.',
  },
  {
    n: 5, name: 'Validate', icon: 'scale',
    what:
      'Deterministic code applies the Rules: arithmetic on unit sale price, metric '
      + 'units, character heights measured in millimetres against the pack '
      + 'dimensions, FSSAI licence structure, EAN-13 check digits. No model is '
      + 'consulted here at all.',
  },
  {
    n: 6, name: 'Review', icon: 'users',
    what:
      'Borderline confidence, a contested unit price or a high penalty exposure '
      + 'sends the case to a senior officer, who must record a written reason with '
      + 'their decision.',
  },
];

const CHECKS: { clause: string; title: string; body: string }[] = [
  {
    clause: 'Rule 6(1)(a)–(g)',
    title: 'The mandatory declarations',
    body:
      'Manufacturer or packer name and address, common name of the commodity, net '
      + 'quantity, month and year of manufacture, retail sale price, consumer care '
      + 'details, and country of origin for imports.',
  },
  {
    clause: 'Rule 6(2)',
    title: 'Unit sale price',
    body:
      'Recomputed from the declared MRP and net quantity rather than trusted as '
      + 'printed. A unit price that does not follow from the other two numbers is '
      + 'the arithmetic error consumers actually lose money to.',
  },
  {
    clause: 'Rule 8',
    title: 'Metric units',
    body:
      'Quantities must be declared in the units the Act prescribes. Imperial or '
      + 'mixed declarations are a breach regardless of how legible they are.',
  },
  {
    clause: 'Rule 9',
    title: 'Principal display panel',
    body:
      'Declarations have to appear on the panel a consumer sees at the point of '
      + 'sale — not only somewhere on the pack.',
  },
  {
    clause: 'Rule 11 · Second Schedule',
    title: 'Minimum character height',
    body:
      'Measured in millimetres from the ink extents of the printed text, scaled by '
      + 'the pack dimensions you enter. Without those dimensions the check is '
      + 'reported as not assessable rather than guessed at.',
  },
  {
    clause: 'FSSAI · GS1',
    title: 'Licence and barcode integrity',
    body:
      'The 14-digit FSSAI licence is structurally validated, and EAN-13 barcodes '
      + 'are checked against their modulo-10 check digit.',
  },
];

export default function HowItWorks() {
  return (
    <Page className="mx-auto max-w-4xl space-y-10 pb-4">
      <PageHeader
        eyebrow={<span className="eyebrow">Method</span>}
        title="How a pack is judged"
        subtitle="The full pipeline, the clauses it applies, and the point at which it stops and asks a person. Published because a score that cannot be interrogated is not worth acting on."
      />

      <Callout tone="info" icon="scale" title="The guarantee">
        A model reads. Deterministic code decides. Every finding on this platform
        traces to a clause of the Legal Metrology (Packaged Commodities) Rules
        2011 and to a specific crop of the original photograph — never to a
        model's unverified assertion.
      </Callout>

      {/* --------------------------------------------------- pipeline ---- */}
      <Section
        title="Six stages"
        subtitle="Each one is observable while it runs; the session page streams them live."
      >
        <Stagger className="space-y-2.5">
          {STAGES.map((s) => {
            const Glyph = Icon[s.icon];
            return (
              <Item key={s.n}>
                <Card className="flex gap-4 p-5">
                  <div className="flex shrink-0 flex-col items-center gap-2">
                    <span className="display nums text-2xl font-semibold leading-none text-ink-faint">
                      {s.n}
                    </span>
                    <span className="grid size-8 place-items-center rounded-lg bg-surface-sunk text-ink-muted">
                      <Glyph size={15} />
                    </span>
                  </div>
                  <div className="min-w-0">
                    <h3 className="display text-lg font-semibold">{s.name}</h3>
                    <p className="mt-1.5 text-pretty text-sm leading-relaxed text-ink-soft">
                      {s.what}
                    </p>
                  </div>
                </Card>
              </Item>
            );
          })}
        </Stagger>
      </Section>

      {/* ---------------------------------------------------- scoring ---- */}
      <Section
        title="How the number is produced"
        subtitle="A pack starts at 100 and loses weight per breach, scaled by severity. It is a count of what is wrong, not a judgement of the brand."
      >
        <ScoreScale />
        <Callout tone="warn" icon="alert" title="Zero findings is not automatically a pass">
          If nothing could be extracted from the photographs, no clause was
          tested, and the result is reported as <strong>not assessable</strong> —
          never as compliant. An enforcement tool that clears a pack it failed to
          read is worse than one that reads nothing at all.
        </Callout>
      </Section>

      {/* ----------------------------------------------------- clauses --- */}
      <Section
        title="What is checked"
        subtitle="Every applicable clause, and what the engine does with it."
      >
        <Stagger className="grid gap-3 sm:grid-cols-2">
          {CHECKS.map((c) => (
            <Item key={c.clause}>
              <Card className="h-full p-5">
                <p className="text-xs font-semibold text-accent">{c.clause}</p>
                <h3 className="mt-1.5 font-semibold">{c.title}</h3>
                <p className="mt-2 text-pretty text-sm leading-relaxed text-ink-muted">
                  {c.body}
                </p>
              </Card>
            </Item>
          ))}
        </Stagger>
      </Section>

      {/* ------------------------------------------------------ limits --- */}
      <Section
        title="What it will not do"
        subtitle="The limits are part of the method."
      >
        <Stagger className="space-y-2.5">
          {[
            [
              'Issue a notice on its own',
              'Auto-accept requires both readings to agree and confidence above threshold. Everything else goes to a person, and a senior decision needs written remarks.',
            ],
            [
              'Distinguish "missing" from "not photographed"',
              'A declaration absent from the surfaces you captured is reported as not found on those surfaces. Only an officer confirming they photographed every printed panel can turn that into "not declared".',
            ],
            [
              'Guess a character height',
              'Rule 11 needs the physical pack dimensions. Without them the check is skipped and said to be skipped, because a fabricated measurement would not survive a hearing.',
            ],
            [
              'Treat one high price as gouging',
              'Price findings use median-absolute-deviation against comparable listings, and a rise across many retailers is classified as a market-wide revision rather than an offence by any one of them.',
            ],
          ].map(([t, b]) => (
            <Item key={t}>
              <Card className="flex gap-3.5 p-5">
                <span className="mt-0.5 shrink-0 text-ink-faint"><Icon.minus size={18} /></span>
                <div>
                  <h3 className="font-semibold">{t}</h3>
                  <p className="mt-1.5 text-pretty text-sm leading-relaxed text-ink-muted">{b}</p>
                </div>
              </Card>
            </Item>
          ))}
        </Stagger>
      </Section>

      <div className="flex flex-wrap gap-2 border-t border-line pt-6">
        <Link to="/catalogue" className="btn-primary">
          <Icon.box size={16} />
          Browse the compliance catalogue
        </Link>
        <Link to="/" className="btn-ghost">Back to work</Link>
      </div>
    </Page>
  );
}
