import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { Page } from '@/components/motion';
import {
  Empty, ErrorBox, Loading, PageHeader, StatusChip, ago, money,
} from '@/components/ui';
import { api } from '@/store/auth';

export default function Leads() {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [notes, setNotes] = useState('');

  const leads = useQuery({ queryKey: ['leads'], queryFn: () => api.leads() });

  const decide = useMutation({
    mutationFn: (v: { ref: string; verdict: 'VERIFIED' | 'REJECTED' | 'INVESTIGATING' }) =>
      api.decideLead(v.ref, v.verdict, notes),
    onSuccess: () => {
      setOpen(null);
      setNotes('');
      qc.invalidateQueries({ queryKey: ['leads'] });
    },
  });

  if (leads.isLoading) return <Loading rows={4} />;
  if (leads.error) return <ErrorBox error={leads.error} retry={() => leads.refetch()} />;

  const items = leads.data ?? [];

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Public tip-offs</span>}
        title="Citizen leads"
        subtitle="Ordered by reporter trust, not arrival time. A confirmed report raises the reporter's standing; a false one costs them twice as much."
      />

      {!items.length ? (
        <Empty title="No pending leads" hint="Reports submitted by consumers appear here." />
      ) : (
        <div className="space-y-3">
          {items.map((lead) => (
            <article key={lead.report_ref} className="surface overflow-hidden">
              <div className="flex flex-col gap-4 p-4 sm:flex-row">
                {lead.image_url && (
                  <img
                    src={api.resolveUrl(lead.image_url)}
                    alt="Reported violation"
                    className="h-32 w-full rounded-lg object-cover sm:w-32"
                    loading="lazy"
                  />
                )}

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="display text-lg font-semibold">{lead.store_name}</h2>
                    <StatusChip status={lead.violation_category} />
                    <StatusChip status={lead.status} />
                    {lead.reporter_verified && (
                      <span className="chip border border-ok/30 bg-ok-soft text-ok">
                        Verified reporter
                      </span>
                    )}
                    <span className="chip bg-surface-sunk text-ink-soft tabular-nums">
                      priority {lead.priority_score}
                    </span>
                  </div>

                  {lead.store_address && (
                    <p className="mt-0.5 text-xs text-ink-muted">{lead.store_address}</p>
                  )}

                  {lead.citizen_remarks && (
                    <p className="mt-2 rounded-lg bg-surface-sunk px-3 py-2 text-sm italic text-ink-soft">
                      “{lead.citizen_remarks}”
                    </p>
                  )}

                  <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-muted">
                    <div>
                      <dt className="inline">Reported by </dt>
                      <dd className="inline font-semibold text-ink-soft">
                        {lead.reporter_name ?? 'Anonymous'}
                        {lead.reporter_trust_score != null &&
                          ` (trust ${Math.round(lead.reporter_trust_score)})`}
                      </dd>
                    </div>
                    <div>
                      <dt className="inline">Filed </dt>
                      <dd className="inline font-semibold text-ink-soft">{ago(lead.created_at)}</dd>
                    </div>
                    {lead.claimed_mrp != null && lead.charged_price != null && (
                      <div>
                        <dt className="inline">Claim </dt>
                        <dd className="inline font-semibold text-bad">
                          {money(lead.claimed_mrp)} charged as {money(lead.charged_price)}
                        </dd>
                      </div>
                    )}
                  </dl>

                  {open === lead.report_ref ? (
                    <div className="mt-3 space-y-2">
                      <textarea
                        className="input" rows={3} value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="What did you find at the premises? This is recorded against the report."
                      />
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button" className="btn-ok"
                          disabled={notes.length < 3 || decide.isPending}
                          onClick={() => decide.mutate({ ref: lead.report_ref, verdict: 'VERIFIED' })}
                        >
                          Confirm violation
                        </button>
                        <button
                          type="button" className="btn-ghost"
                          disabled={notes.length < 3 || decide.isPending}
                          onClick={() => decide.mutate({ ref: lead.report_ref, verdict: 'INVESTIGATING' })}
                        >
                          Mark investigating
                        </button>
                        <button
                          type="button" className="btn-danger"
                          disabled={notes.length < 3 || decide.isPending}
                          onClick={() => decide.mutate({ ref: lead.report_ref, verdict: 'REJECTED' })}
                        >
                          Not substantiated
                        </button>
                        <button
                          type="button" className="btn-ghost"
                          onClick={() => { setOpen(null); setNotes(''); }}
                        >
                          Cancel
                        </button>
                      </div>
                      {decide.error && <ErrorBox error={decide.error} />}
                    </div>
                  ) : (
                    <button
                      type="button" className="btn-primary mt-3"
                      onClick={() => { setOpen(lead.report_ref); setNotes(''); }}
                    >
                      Record a verdict
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </Page>
  );
}
