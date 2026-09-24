import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { useState } from 'react';
import {
  Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

import { Page } from '@/components/motion';
import {
  Empty, ErrorBox, Loading, PageHeader, Section, Stat, moneyShort,
} from '@/components/ui';
import { api } from '@/store/auth';

type Tab = 'trends' | 'agency' | 'ecom';

export default function Policy() {
  const [tab, setTab] = useState<Tab>('trends');
  const [days, setDays] = useState(90);

  const trends = useQuery({
    queryKey: ['macro', days],
    queryFn: () => api.macroTrends(days),
    enabled: tab === 'trends',
  });
  const graph = useQuery({
    queryKey: ['agency-graph'],
    queryFn: () => api.agencyGraph(),
    enabled: tab === 'agency',
  });
  const ecom = useQuery({
    queryKey: ['platform-scorecard'],
    queryFn: () => api.platformScorecard(),
    enabled: tab === 'ecom',
  });

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Ministry view</span>}
        title="Policy intelligence"
        subtitle="Where compliance across packaged commodities actually stands, and which direction each clause is moving."
        action={
          tab === 'trends' ? (
            /* A segmented control, not four standalone buttons: these are
               mutually exclusive views of one window, and the old `bg-white`
               active state was invisible in dark mode. */
            <div className="flex rounded-lg border border-line bg-surface-sunk p-0.5">
              {[30, 90, 180, 365].map((d) => (
                <button
                  key={d} type="button" onClick={() => setDays(d)}
                  aria-pressed={days === d}
                  className={clsx(
                    'nums rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                    days === d
                      ? 'bg-surface text-ink shadow-xs'
                      : 'text-ink-muted hover:text-ink',
                  )}
                >
                  {d}d
                </button>
              ))}
            </div>
          ) : undefined
        }
      />

      <nav className="flex gap-1 border-b border-line">
        {([
          ['trends', 'Compliance trends'],
          ['agency', 'Inter-agency graph'],
          ['ecom', 'E-commerce'],
        ] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key} type="button" onClick={() => setTab(key)}
            className={clsx(
              'border-b-2 px-4 py-2 text-sm font-semibold transition',
              tab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-ink-muted hover:text-ink-soft',
            )}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* ------------------------------------------------------- trends -- */}
      {tab === 'trends' && (
        trends.isLoading ? <Loading rows={4} />
        : trends.error ? <ErrorBox error={trends.error} retry={() => trends.refetch()} />
        : (() => {
          const t = trends.data!;
          const clauseData = t.most_violated_clauses.slice(0, 8).map((c) => ({
            name: c.rule_name.length > 26 ? `${c.rule_name.slice(0, 26)}…` : c.rule_name,
            rate: c.violation_rate,
            checks: c.applicable_inspections,
            clause: c.clause,
            direction: c.direction,
          }));

          return (
            <div className="space-y-6">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Stat
                  label="Inspections" icon="camera" value={t.headline.inspections_current}
                  hint={`vs ${t.headline.inspections_previous} in the prior ${days} days`}
                />
                <Stat
                  label="Compliance rate"
                  value={t.headline.overall_compliance_rate != null
                    ? `${t.headline.overall_compliance_rate}%` : '—'}
                  icon="checkCircle"
                  tone={(t.headline.overall_compliance_rate ?? 0) >= 70 ? 'good' : 'bad'}
                  hint={`of ${t.headline.inspections_current} inspections`}
                />
                <Stat
                  label="Penalty exposure"
                  value={moneyShort(t.headline.total_penalty_exposure)} tone="warn"
                  icon="rupee" hint="Across the window"
                />
                <Stat
                  label="Escalated" value={t.headline.cases_escalated}
                  icon="scale" hint="Sent to senior review"
                />
              </div>

              <Section
                title="Most violated clauses"
                subtitle="Ranked by violation rate over inspections where the rule applied — not by raw count."
              >
                {!clauseData.length ? (
                  <Empty title="No findings in this window" />
                ) : (
                  <div className="surface p-4">
                    <ResponsiveContainer width="100%" height={Math.max(240, clauseData.length * 42)}>
                      <BarChart data={clauseData} layout="vertical" margin={{ left: 8, right: 24 }}>
                        <XAxis type="number" unit="%" tick={{ fontSize: 11 }} />
                        <YAxis
                          type="category" dataKey="name" width={190}
                          tick={{ fontSize: 11 }} interval={0}
                        />
                        <Tooltip
                          formatter={(value, _name, item) => {
                            const d = item?.payload as (typeof clauseData)[number] | undefined;
                            return [`${value}% of ${d?.checks ?? 0} checks`, 'Violation rate'];
                          }}
                          labelFormatter={(_label, payload) =>
                            (payload?.[0]?.payload as { clause?: string } | undefined)?.clause ?? ''}
                          contentStyle={{ fontSize: 12, borderRadius: 8 }}
                        />
                        <Bar dataKey="rate" radius={[0, 4, 4, 0]}>
                          {clauseData.map((d, i) => (
                            <Cell
                              key={i}
                              fill={`hsl(var(--score-${d.rate >= 40 ? 5 : d.rate >= 20 ? 3 : 1}))`}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </Section>

              <div className="grid gap-4 lg:grid-cols-2">
                <Section title="Degrading categories">
                  {!t.degrading_categories.length ? (
                    <Empty title="Nothing degrading" hint="No category moved down materially." />
                  ) : (
                    <div className="surface divide-y divide-line">
                      {t.degrading_categories.map((c) => (
                        <div key={c.slug} className="p-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-medium">{c.name}</span>
                            <span className="chip bg-bad-soft text-bad tabular-nums">
                              {c.change?.toFixed(1)} pts
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-ink-muted">{c.note}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </Section>

                <Section title="Improving categories">
                  {!t.improving_categories.length ? (
                    <Empty title="Nothing improving" hint="No category moved up materially." />
                  ) : (
                    <div className="surface divide-y divide-line">
                      {t.improving_categories.map((c) => (
                        <div key={c.slug} className="p-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-medium">{c.name}</span>
                            <span className="chip bg-ok-soft text-ok tabular-nums">
                              +{c.change?.toFixed(1)} pts
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-ink-muted">{c.note}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </Section>
              </div>

              {t.upcoming_enforcement_windows.length > 0 && (
                <Section
                  title="Upcoming enforcement windows"
                  subtitle="Festival demand concentrates specific abuses in specific categories."
                >
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {t.upcoming_enforcement_windows.map((f) => (
                      <div key={f.festival} className="surface p-4">
                        <div className="flex items-center justify-between">
                          <span className="font-bold">{f.festival}</span>
                          <span className="chip bg-warn-soft text-warn">
                            ×{f.peak_multiplier}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-ink-muted">
                          In {f.days_until} days · watch from {f.watch_from}
                        </p>
                        <p className="mt-2 text-xs text-ink-soft">
                          {f.elevated_categories.slice(0, 4).join(', ').replace(/-/g, ' ')}
                        </p>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              <p className="surface bg-surface-sunk p-4 text-xs leading-relaxed text-ink-muted">
                <span className="font-semibold">Methodology. </span>{t.methodology}
              </p>
            </div>
          );
        })()
      )}

      {/* ------------------------------------------------------- agency -- */}
      {tab === 'agency' && (
        graph.isLoading ? <Loading rows={4} />
        : graph.error ? <ErrorBox error={graph.error} retry={() => graph.refetch()} />
        : (() => {
          const g = graph.data!;
          const flagged = g.entities.filter((e) => e.referrals.length > 0);
          return (
            <div className="space-y-6">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="Entities" value={g.entity_count} />
                <Stat label="High risk" value={g.high_risk_count} tone="bad" />
                <Stat label="Referrals" value={g.summary.total_referrals} tone="warn" />
                <Stat
                  label="Aggregate exposure"
                  value={moneyShort(g.summary.aggregate_penalty_exposure)} tone="warn"
                />
              </div>

              <Section
                title="Cross-agency referrals"
                subtitle="A Legal Metrology violation alongside a lapsed licence is a different problem from either alone."
              >
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(g.referrals_by_authority).map(([code, info]) => (
                    <div key={code} className="surface p-4">
                      <div className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                        {code}
                      </div>
                      <div className="mt-1 text-2xl font-bold">{info.count}</div>
                      <p className="mt-1 text-xs text-ink-muted">
                        {info.high_priority} high priority
                      </p>
                      <p className="mt-1 text-[11px] leading-snug text-ink-muted">
                        {info.authority_name}
                      </p>
                    </div>
                  ))}
                </div>
              </Section>

              <Section title={`Flagged entities (${flagged.length})`}>
                {!flagged.length ? (
                  <Empty title="No adverse correlations" />
                ) : (
                  <div className="space-y-3">
                    {flagged.slice(0, 20).map((e) => (
                      <article key={e.brand_name} className="surface p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="display text-lg font-semibold">{e.brand_name}</h3>
                          <span className={clsx(
                            'chip tabular-nums',
                            e.risk_index >= 7 ? 'bg-bad-soft text-bad'
                              : e.risk_index >= 4 ? 'bg-warn-soft text-warn'
                              : 'bg-surface-sunk text-ink-soft',
                          )}>
                            risk {e.risk_index}
                          </span>
                          {e.legal_metrology.violation_count > 0 && (
                            <span className="chip bg-surface-sunk text-ink-soft">
                              {e.legal_metrology.violation_count} LM findings
                            </span>
                          )}
                        </div>

                        <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                          {[
                            ['FSSAI', e.identifiers.fssai.number, e.identifiers.fssai.valid],
                            ['BIS', e.identifiers.bis.number, e.identifiers.bis.valid],
                            ['GSTIN', e.identifiers.gstin.number, e.identifiers.gstin.active],
                          ].filter(([, num]) => num).map(([label, , ok]) => (
                            <span
                              key={String(label)}
                              className={clsx(
                                'chip', ok ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad',
                              )}
                            >
                              {String(label)} {ok ? 'valid' : 'lapsed'}
                            </span>
                          ))}
                        </div>

                        <ul className="mt-2 space-y-0.5 text-xs text-ink-soft">
                          {e.flags.slice(0, 3).map((f) => <li key={f}>• {f}</li>)}
                        </ul>

                        {e.referrals.length > 0 && (
                          <div className="mt-3 space-y-2">
                            {e.referrals.map((r, i) => (
                              <div key={i} className="rounded-lg bg-surface-sunk p-3">
                                <div className="flex items-center gap-2">
                                  <span className={clsx(
                                    'chip',
                                    r.priority === 'HIGH' ? 'bg-bad-soft text-bad'
                                      : 'bg-warn-soft text-warn',
                                  )}>
                                    {r.priority}
                                  </span>
                                  <span className="text-xs font-bold">{r.authority_name}</span>
                                </div>
                                <p className="mt-1 text-xs text-ink-soft">{r.recommended_action}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </Section>
            </div>
          );
        })()
      )}

      {/* --------------------------------------------------------- ecom -- */}
      {tab === 'ecom' && (
        ecom.isLoading ? <Loading rows={3} />
        : ecom.error ? <ErrorBox error={ecom.error} retry={() => ecom.refetch()} />
        : (() => {
          const s = ecom.data!;
          return (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-3">
                <Stat label="Listings checked" value={s.listings_checked} />
                <Stat label="Non-compliant" value={s.non_compliant_listings} tone="bad" />
                <Stat
                  label="Non-compliance rate"
                  value={`${s.overall_non_compliance_rate}%`} tone="warn"
                />
              </div>

              <Section title="Platform scorecard">
                <div className="space-y-3">
                  {s.platforms.map((p) => (
                    <article key={p.platform} className="surface p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="display text-lg font-semibold">{p.platform}</h3>
                        <span className={clsx(
                          'chip tabular-nums',
                          p.non_compliance_rate >= 50 ? 'bg-bad-soft text-bad'
                            : p.non_compliance_rate >= 20 ? 'bg-warn-soft text-warn'
                            : 'bg-ok-soft text-ok',
                        )}>
                          {p.non_compliance_rate}% non-compliant
                        </span>
                      </div>
                      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-sunk">
                        <div
                          className={clsx(
                            'h-full rounded-full',
                            p.non_compliance_rate >= 50 ? 'bg-bad'
                              : p.non_compliance_rate >= 20 ? 'bg-warn' : 'bg-ok',
                          )}
                          style={{ width: `${p.non_compliance_rate}%` }}
                        />
                      </div>
                      <p className="mt-2 text-xs text-ink-muted">
                        {p.non_compliant_listings} of {p.listings_checked} listings
                      </p>
                      <ul className="mt-2 space-y-0.5 text-xs text-ink-soft">
                        {p.top_issues.map((i) => (
                          <li key={i.issue}>• {i.issue} ({i.count})</li>
                        ))}
                      </ul>
                      <p className="mt-2 text-xs font-medium text-accent">{p.assessment}</p>
                    </article>
                  ))}
                </div>
              </Section>

              <p className="surface bg-surface-sunk p-4 text-xs text-ink-muted">
                {s.legal_basis}
              </p>
            </div>
          );
        })()
      )}
    </Page>
  );
}
