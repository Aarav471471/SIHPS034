import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link, useParams } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { Item, Page, Stagger } from '@/components/motion';
import {
  Callout, Card, ComplianceBadge, Empty, ErrorBox, Loading, ScoreRing, ScoreScale,
  Section, SeverityChip, Verdict, money, when,
} from '@/components/ui';
import { api } from '@/store/auth';

interface Dossier {
  product: Record<string, any>;
  price_intelligence: {
    modal_mrp?: number | null;
    median_mrp?: number | null;
    sample_count: number;
    outliers_rejected: number;
    confidence: number;
    note: string;
    market_revision?: string | null;
    gouging_findings: Array<Record<string, any>>;
  };
  inspection_history: Array<Record<string, any>>;
}

export default function ProductDetail() {
  const { barcode } = useParams<{ barcode: string }>();

  const q = useQuery({
    queryKey: ['product', barcode],
    queryFn: () => api.product(barcode!) as unknown as Promise<Dossier>,
    enabled: Boolean(barcode),
  });

  const ecom = useQuery({
    queryKey: ['ecom', barcode],
    queryFn: () => api.ecomCrossCheck(barcode!),
    enabled: Boolean(barcode),
    retry: false,
  });

  if (q.isLoading) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;

  const d = q.data!;
  const p = d.product;
  const pi = d.price_intelligence;
  const history = d.inspection_history;

  return (
    <Page className="mx-auto max-w-4xl space-y-8">
      <Verdict
        score={p.avg_score}
        state={p.avg_score == null ? 'unassessable' : 'scored'}
        title={p.product_name}
        subtitle={
          <>
            {p.brand_name}
            {p.category ? ` · ${p.category}` : ''}
          </>
        }
        meta={
          <>
            <ComplianceBadge level={p.badge_level} />
            <code className="font-mono text-2xs text-ink-faint">{p.barcode}</code>
          </>
        }
        aside={
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            {[
              ['MRP', money(p.official_mrp)],
              ['Net quantity', p.net_quantity ?? '—'],
              ['Unit price', p.unit_price ? `₹${p.unit_price}` : '—'],
              ['Origin', p.country_of_origin ?? '—'],
            ].map(([k, v]) => (
              <div key={String(k)}>
                <dt className="eyebrow">{k}</dt>
                <dd className="nums mt-1 text-sm font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        }
        note={
          history.length
            ? `Averaged over ${history.length} field inspection${history.length === 1 ? '' : 's'}, most recently ${when(history[0]?.created_at)}. Every one is listed below.`
            : 'No field inspection on record yet. This entry reflects the declared label only.'
        }
      />

      {/* --------------------------------------------- price intelligence */}
      <Section
        title="Price intelligence"
        subtitle="What this pack actually sells for, across consumer and officer scans."
      >
        <Card className="p-5">
          <dl className="grid gap-5 sm:grid-cols-4">
            {[
              ['Standard MRP', money(pi.modal_mrp), 'the modal price'],
              ['Median seen', money(pi.median_mrp), 'across all scans'],
              ['Scans used', String(pi.sample_count), `${pi.outliers_rejected} rejected as outliers`],
              ['Confidence', pi.confidence.toFixed(2), 'in this estimate'],
            ].map(([k, v, hint]) => (
              <div key={k}>
                <dt className="eyebrow">{k}</dt>
                <dd className="nums display mt-1.5 text-2xl font-semibold leading-none">{v}</dd>
                <p className="mt-1.5 text-2xs text-ink-muted">{hint}</p>
              </div>
            ))}
          </dl>

          {/* Stating the method matters: a mean would be dragged by one
              mis-typed price, and the officer is entitled to know it wasn't. */}
          <p className="mt-4 border-t border-line pt-4 text-2xs leading-relaxed text-ink-muted">
            {pi.note}
          </p>
        </Card>

        {pi.market_revision && (
          <Callout tone="info" title="Market-wide revision detected">
            {pi.market_revision}
          </Callout>
        )}

        {pi.gouging_findings.length > 0 && (
          <Stagger className="space-y-2">
            {pi.gouging_findings.slice(0, 6).map((f, i) => (
              <Item key={`${f.store_name}-${i}`}>
                <Card
                  className={clsx(
                    'border-l-[3px] p-4',
                    f.severity === 'PRIORITY' ? 'border-l-bad' : 'border-l-warn',
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{f.store_name}</span>
                    <span
                      className={clsx(
                        'chip ring-1 ring-inset',
                        f.severity === 'PRIORITY'
                          ? 'bg-bad/10 text-bad ring-bad/25'
                          : 'bg-warn/10 text-warn ring-warn/25',
                      )}
                    >
                      {f.severity}
                    </span>
                    <span className="chip nums ml-auto bg-surface-sunk text-ink-soft">
                      +{f.overcharge_pct}% over MRP
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{f.reasons?.[0]}</p>
                </Card>
              </Item>
            ))}
          </Stagger>
        )}
      </Section>

      {/* ----------------------------------------------- e-commerce ------ */}
      {ecom.data && ecom.data.listings_checked > 0 && (
        <Section
          title="E-commerce cross-check"
          subtitle={`${ecom.data.listings_checked} online listing${ecom.data.listings_checked === 1 ? '' : 's'} compared against the verified physical pack — Rule 6(10).`}
        >
          <Card className="divide-y divide-line overflow-hidden">
            {ecom.data.ecom_listings.map((l, i) => (
              <div key={i} className="flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="font-semibold">{l.platform}</p>
                  <p className="truncate text-2xs text-ink-muted">
                    {l.listing_title ?? l.listing_url}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="nums font-semibold">{money(l.listed_mrp)}</p>
                  <span
                    className={clsx(
                      'chip mt-1 ring-1 ring-inset',
                      l.discrepancy
                        ? 'bg-bad/10 text-bad ring-bad/25'
                        : 'bg-ok/10 text-ok ring-ok/25',
                    )}
                  >
                    {l.discrepancy
                      ? `${l.issue_count} issue${l.issue_count === 1 ? '' : 's'}`
                      : 'compliant'}
                  </span>
                </div>
              </div>
            ))}
          </Card>

          {ecom.data.findings.length > 0 && (
            <Stagger className="space-y-2">
              {ecom.data.findings.slice(0, 5).map((f, i) => (
                <Item key={i}>
                  <Card className="border-l-[3px] border-l-warn p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{f.platform}</span>
                      <SeverityChip severity={f.severity} />
                    </div>
                    <p className="mt-1.5 text-sm font-medium">{f.issue}</p>
                    <p className="mt-1 text-2xs font-semibold text-accent">{f.legal_clause}</p>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{f.detail}</p>
                  </Card>
                </Item>
              ))}
            </Stagger>
          )}
        </Section>
      )}

      {/* -------------------------------------------------- history ------ */}
      <Section
        title="Inspection history"
        subtitle={
          history.length
            ? `${history.length} field inspection${history.length === 1 ? '' : 's'} on record.`
            : undefined
        }
      >
        {!history.length ? (
          <Empty
            icon="camera"
            title="No field inspection yet"
            hint="This commodity is in the catalogue from its declared label, but no officer has photographed a physical pack."
          />
        ) : (
          <Stagger className="space-y-2">
            {history.map((s) => (
              <Item key={s.session_id}>
                <Link to={`/officer/sessions/${s.session_id}`} className="block">
                  <Card interactive className="flex items-start gap-4 p-4">
                    <ScoreRing score={s.overall_score} size={44} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="font-semibold">{s.store_name ?? 'Unknown premises'}</span>
                        <span className="nums ml-auto text-2xs text-ink-muted">
                          {when(s.created_at)}
                        </span>
                      </div>
                      {s.violations?.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {s.violations.map((v: any, i: number) => (
                            <li key={i} className="flex gap-2 text-2xs leading-relaxed text-ink-soft">
                              <Icon.alert size={11} className="mt-0.5 shrink-0 text-bad" />
                              <span>
                                <span className="font-semibold">{v.rule_name}</span>
                                {v.legal_clause ? ` — ${v.legal_clause}` : ''}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-1.5 text-2xs text-ok">No contravention recorded.</p>
                      )}
                    </div>
                  </Card>
                </Link>
              </Item>
            ))}
          </Stagger>
        )}
      </Section>

      <ScoreScale />
    </Page>
  );
}
