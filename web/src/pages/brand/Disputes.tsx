import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Page } from '@/components/motion';
import { Empty, ErrorBox, Loading, PageHeader, money, when } from '@/components/ui';
import { api, useAuth } from '@/store/auth';

export default function Disputes() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [remarks, setRemarks] = useState('');

  const isAppellate = user?.role === 'senior_officer' || user?.role === 'admin';

  const q = useQuery({
    queryKey: ['disputes', isAppellate],
    queryFn: () => api.appellateQueue(),
    enabled: isAppellate,
  });

  const decide = useMutation({
    mutationFn: (v: { token: string; decision: 'ACCEPTED' | 'REJECTED' }) =>
      api.decideDispute(v.token, v.decision, remarks),
    onSuccess: () => {
      setOpen(null);
      setRemarks('');
      qc.invalidateQueries({ queryKey: ['disputes'] });
    },
  });

  if (!isAppellate) {
    return (
      <div className="mx-auto max-w-lg">
        <Empty
          title="Appeals are opened by notice"
          hint="When a notice is served against your brand you receive a secure link. That link opens the appeal portal directly — no account needed."
        />
      </div>
    );
  }

  if (q.isLoading) return <Loading rows={3} />;
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;

  const items = q.data ?? [];

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Adjudication</span>}
        title="Appellate queue"
        subtitle="Appeals filed against issued notices. Read the brand's grounds alongside the original inspection evidence before deciding — a decision here is final for that notice."
      />

      {!items.length ? (
        <Empty title="No appeals awaiting decision" />
      ) : (
        <div className="space-y-3">
          {items.map((d) => (
            <article key={d.dispute_token} className="surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="display text-lg font-semibold">{d.brand_name ?? 'Unnamed brand'}</h2>
                <span className="chip bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                  {d.appellate_status.replace(/_/g, ' ')}
                </span>
                {d.estimated_penalty != null && (
                  <span className="chip bg-warn-soft text-warn">
                    {money(d.estimated_penalty)}
                  </span>
                )}
                <span className="ml-auto text-xs text-ink-muted">
                  filed {when(d.created_at)}
                </span>
              </div>

              <p className="mt-1 text-sm text-ink-muted">
                {d.product_name ?? '—'} · {d.store_name ?? '—'} · score{' '}
                {d.overall_score ?? '—'}/100
              </p>

              {d.grounds_of_appeal && (
                <blockquote className="mt-3 rounded-lg bg-surface-sunk px-3 py-2 text-sm italic text-ink-soft">
                  {d.grounds_of_appeal}
                </blockquote>
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  to={`/brand/dispute/${d.dispute_token}`}
                  className="btn-ghost"
                  target="_blank"
                >
                  View the full case
                </Link>
                {open !== d.dispute_token && (
                  <button
                    type="button" className="btn-primary"
                    onClick={() => { setOpen(d.dispute_token); setRemarks(''); }}
                  >
                    Decide
                  </button>
                )}
              </div>

              {open === d.dispute_token && (
                <div className="mt-3 space-y-2">
                  <textarea
                    className="input" rows={3} value={remarks}
                    onChange={(e) => setRemarks(e.target.value)}
                    placeholder="Reasons for your decision. These are recorded and shown to the brand."
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button" className="btn-ok"
                      disabled={remarks.length < 10 || decide.isPending}
                      onClick={() => decide.mutate({ token: d.dispute_token, decision: 'ACCEPTED' })}
                    >
                      Accept appeal — withdraw notice
                    </button>
                    <button
                      type="button" className="btn-danger"
                      disabled={remarks.length < 10 || decide.isPending}
                      onClick={() => decide.mutate({ token: d.dispute_token, decision: 'REJECTED' })}
                    >
                      Reject — notice stands
                    </button>
                    <button
                      type="button" className="btn-ghost"
                      onClick={() => { setOpen(null); setRemarks(''); }}
                    >
                      Cancel
                    </button>
                  </div>
                  {decide.error && <ErrorBox error={decide.error} />}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </Page>
  );
}
