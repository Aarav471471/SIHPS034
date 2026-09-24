import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Page } from '@/components/motion';
import {
  Empty, ErrorBox, Loading, PageHeader, ScoreRing, ago, money,
} from '@/components/ui';
import { api } from '@/store/auth';

const TRIGGER_COPY: Record<string, string> = {
  LOW_CONFIDENCE: 'Pipeline confidence fell in the escalation band',
  CONTESTED_UNIT_PRICE: 'Unit price does not follow from the pack',
  HIGH_PENALTY: 'Penalty exposure above the senior-review threshold',
  MANUAL: 'Referred by the inspecting officer',
};

export default function PeerReviews() {
  const q = useQuery({ queryKey: ['peer-reviews'], queryFn: () => api.pendingPeerReviews() });

  if (q.isLoading) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;

  const items = q.data ?? [];

  return (
    <Page className="space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Senior officer</span>}
        title="Peer review queue"
        subtitle="Cases the pipeline declined to issue on its own — borderline confidence, a contested unit price, or a high penalty. Read the cited crops before approving a notice."
      />

      {!items.length ? (
        <Empty
          title="Nothing awaiting review"
          hint="Cases arrive here automatically when confidence is borderline, the unit-price arithmetic is contested, or the penalty exceeds the threshold."
        />
      ) : (
        <div className="space-y-3">
          {items.map((r) => (
            <Link
              key={r.id}
              to={`/officer/sessions/${r.session_ref}`}
              className="surface flex items-start gap-4 p-4 transition hover:border-accent"
            >
              <ScoreRing score={r.overall_score} size={56} />
              <div className="min-w-0 flex-1">
                <h2 className="truncate font-bold">
                  {r.product_name ?? 'Unidentified commodity'}
                </h2>
                <p className="truncate text-sm text-ink-muted">
                  {r.brand_name ?? '—'} · {r.store_name ?? 'No store'} · filed {ago(r.created_at)}
                </p>

                <div className="mt-2 rounded-lg bg-violet-500/10 px-3 py-2">
                  <p className="text-xs font-bold text-violet-700 dark:text-violet-300">
                    {TRIGGER_COPY[r.trigger_reason ?? ''] ?? r.trigger_reason}
                  </p>
                  {r.trigger_detail && (
                    <p className="mt-0.5 text-xs text-violet-600 dark:text-violet-400">{r.trigger_detail}</p>
                  )}
                </div>

                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {r.triggering_confidence != null && (
                    <span className="chip bg-surface-sunk text-ink-soft tabular-nums">
                      confidence {r.triggering_confidence.toFixed(2)}
                    </span>
                  )}
                  {r.violation_count > 0 && (
                    <span className="chip bg-bad-soft text-bad">
                      {r.violation_count} finding{r.violation_count === 1 ? '' : 's'}
                    </span>
                  )}
                  {r.estimated_penalty != null && (
                    <span className="chip bg-warn-soft text-warn">
                      {money(r.estimated_penalty)}
                    </span>
                  )}
                  {r.requested_by_name && (
                    <span className="chip bg-surface-sunk text-ink-muted">
                      from {r.requested_by_name}
                    </span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </Page>
  );
}
