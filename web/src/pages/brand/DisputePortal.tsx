import { useMutation, useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { ErrorBox, Loading, SeverityChip, money, when } from '@/components/ui';
import { api } from '@/store/auth';

/**
 * Token-addressed appeal portal -- spec 3.G.
 *
 * Deliberately outside the authenticated shell. A brand receives this link with
 * the notice and must be able to see exactly what is alleged, and the pixels it
 * rests on, without first negotiating an account. Due process should not have an
 * onboarding funnel.
 */
export default function DisputePortal() {
  const { token } = useParams<{ token: string }>();
  const [grounds, setGrounds] = useState('');

  const dispute = useQuery({
    queryKey: ['dispute', token],
    queryFn: () => api.viewDispute(token!),
    enabled: Boolean(token),
  });

  const submit = useMutation({
    mutationFn: () => api.submitDispute(token!, grounds),
    onSuccess: () => dispute.refetch(),
  });

  if (dispute.isLoading) {
    return <div className="mx-auto max-w-3xl p-6"><Loading rows={4} /></div>;
  }
  if (dispute.error) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorBox error={dispute.error} />
      </div>
    );
  }

  const d = dispute.data!;
  const canFile = !d.is_expired && d.appellate_status === 'UNDER_REVIEW' && !d.grounds_of_appeal;

  return (
    <div className="min-h-dvh bg-surface-sunk">
      <header className="border-b border-line bg-[hsl(222_54%_11%)] px-6 py-7 text-white">
        <div className="mx-auto max-w-3xl">
          <p className="eyebrow text-white/50">
            Department of Legal Metrology · Ministry of Consumer Affairs
          </p>
          <h1 className="display mt-2 text-display-sm font-semibold">
            Notice appeal portal
          </h1>
          <p className="mt-2 text-sm text-white/70">
            Reference <span className="font-mono">{d.session_ref}</span> ·{' '}
            {d.product_name ?? 'Commodity'}
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-5 p-6">
        <div className={clsx('surface p-4',
          d.is_expired ? 'border-bad/30 bg-bad-soft'
            : d.appellate_status === 'ACCEPTED' ? 'border-ok/30 bg-ok-soft'
            : d.appellate_status === 'REJECTED' ? 'border-bad/30 bg-bad-soft'
            : 'border-warn/30 bg-warn-soft',
        )}>
          <p className="text-sm font-bold">
            {d.is_expired
              ? `The ${d.window_days}-day appeal window closed on ${when(d.token_expires_at)}.`
              : d.appellate_status === 'ACCEPTED'
                ? 'Appeal accepted — the notice has been withdrawn.'
                : d.appellate_status === 'REJECTED'
                  ? 'Appeal rejected — the notice stands.'
                  : d.grounds_of_appeal
                    ? 'Your appeal has been filed and is awaiting an appellate officer.'
                    : `You have until ${when(d.token_expires_at)} to respond.`}
          </p>
          {d.appellate_remarks && (
            <p className="mt-2 text-sm">{d.appellate_remarks}</p>
          )}
        </div>

        <section className="surface p-5">
          <h2 className="display text-xl font-semibold">Particulars</h2>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <dt className="text-ink-muted">Commodity</dt>
            <dd className="font-semibold">{d.product_name ?? '—'}</dd>
            <dt className="text-ink-muted">Premises</dt>
            <dd className="font-semibold">{d.store_name ?? '—'}</dd>
            <dt className="text-ink-muted">Inspected</dt>
            <dd className="font-semibold">{when(d.inspected_at)}</dd>
            <dt className="text-ink-muted">Compliance score</dt>
            <dd className="font-semibold">{d.overall_score ?? '—'}/100</dd>
            <dt className="text-ink-muted">Penalty exposure</dt>
            <dd className="font-semibold text-warn">{money(d.estimated_penalty)}</dd>
          </dl>
        </section>

        {/* The pixel crops are the point of this page. A brand cannot mount a
            real defence against a finding it has not been shown. */}
        <section className="space-y-3">
          <h2 className="font-bold">
            Findings cited against you ({d.cited_violations.length})
          </h2>
          {d.cited_violations.map((v, i) => (
            <article key={`${v.rule_id}-${i}`} className="surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="display text-lg font-semibold">{v.rule_name ?? v.rule_id}</h3>
                <SeverityChip severity={v.severity} />
              </div>
              {v.legal_clause && (
                <p className="mt-1 text-xs font-medium text-accent">{v.legal_clause}</p>
              )}
              <p className="mt-2 text-sm text-ink-soft">{v.evidence_text}</p>

              {(v.calculated_value || v.expected_value) && (
                <dl className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-surface-sunk p-3 text-sm">
                  <div>
                    <dt className="text-xs text-ink-muted">Observed</dt>
                    <dd className="font-semibold">{v.calculated_value ?? '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-ink-muted">Required</dt>
                    <dd className="font-semibold text-ok">{v.expected_value ?? '—'}</dd>
                  </div>
                </dl>
              )}

              {v.evidence_crop_url && (
                <figure className="mt-3">
                  <img
                    src={api.resolveUrl(v.evidence_crop_url)}
                    alt={`Evidence for ${v.rule_name}`}
                    className="max-h-40 rounded-lg border border-line-strong"
                  />
                  <figcaption className="mt-1 text-xs text-ink-muted">
                    The exact pixels cited, from the officer's original photograph
                  </figcaption>
                </figure>
              )}
            </article>
          ))}
        </section>

        {d.evidence_images.length > 0 && (
          <section>
            <h2 className="font-bold">Evidence photographs</h2>
            <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {d.evidence_images.map((img) => (
                <figure key={img.sha256} className="surface overflow-hidden">
                  {img.url && (
                    <img
                      src={api.resolveUrl(img.url)} alt={img.surface}
                      className="aspect-square w-full object-cover" loading="lazy"
                    />
                  )}
                  <figcaption className="p-2 text-[10px]">
                    <span className="block font-bold">{img.surface}</span>
                    <span className="block break-all font-mono text-ink-muted">
                      {img.sha256.slice(0, 16)}…
                    </span>
                  </figcaption>
                </figure>
              ))}
            </div>
            <p className="mt-2 text-xs text-ink-muted">
              Each photograph was sealed with a SHA-256 digest at capture. You can
              verify these hashes independently.
            </p>
          </section>
        )}

        {d.grounds_of_appeal && (
          <section className="surface p-5">
            <h2 className="font-bold">Your grounds of appeal</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-ink-soft">
              {d.grounds_of_appeal}
            </p>
            {d.counter_evidence_urls && d.counter_evidence_urls.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm">
                {d.counter_evidence_urls.map((u) => (
                  <li key={String(u)} className="text-accent">{String(u)}</li>
                ))}
              </ul>
            )}
          </section>
        )}

        {canFile && (
          <form
            className="surface space-y-3 p-5"
            onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}
          >
            <h2 className="font-bold">File an appeal</h2>
            <p className="text-sm text-ink-muted">
              State your grounds. Attach batch records, an accredited laboratory
              declaration, or an approved packaging variance notice by reference.
            </p>
            <textarea
              className="input" rows={6} value={grounds} required minLength={20}
              onChange={(e) => setGrounds(e.target.value)}
              placeholder="Packaging variation approved under the Legal Metrology (Packaged Commodities) Amendment Rules 2024. Batch records and laboratory declaration attached."
            />
            {submit.error && <ErrorBox error={submit.error} />}
            <button
              type="submit" className="btn-primary w-full"
              disabled={submit.isPending || grounds.length < 20}
            >
              {submit.isPending ? 'Filing…' : 'Submit appeal'}
            </button>
          </form>
        )}

        <p className="pb-8 text-center text-xs text-ink-muted">
          An appellate officer reviews your submission alongside the original
          inspection evidence before any further action is taken.
        </p>
      </main>
    </div>
  );
}
