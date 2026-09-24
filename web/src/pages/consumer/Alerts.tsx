import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Link } from 'react-router-dom';

import { Page } from '@/components/motion';
import { Empty, ErrorBox, Loading, PageHeader, ago } from '@/components/ui';
import { api } from '@/store/auth';

const TONE: Record<string, string> = {
  CRITICAL: 'border-l-bad bg-bad-soft',
  WARNING: 'border-l-warn bg-warn-soft',
  // `bg-white` here was invisible in dark mode -- the surface token is the
  // same colour in light and correct in both.
  INFO: 'border-l-line-strong bg-surface',
};

const TYPE_LABEL: Record<string, string> = {
  PRODUCT_RECALL: 'Recall',
  EXPIRED_BATCH_WARNING: 'Expiry',
  PRICE_SURGE: 'Overcharging',
  COMPLIANCE_UPDATE: 'Compliance',
};

export default function Alerts() {
  const qc = useQueryClient();
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: () => api.alerts() });

  const markRead = useMutation({
    mutationFn: (id: number) => api.markAlertRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });

  if (alerts.isLoading) return <Loading rows={4} />;
  if (alerts.error) return <ErrorBox error={alerts.error} retry={() => alerts.refetch()} />;

  const items = alerts.data ?? [];
  const unread = items.filter((a) => !a.is_read).length;

  return (
    <Page className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Your watchlist</span>}
        title="Alerts"
        subtitle={`Recalls, expiry warnings and overcharging notices for commodities you have scanned.${unread > 0 ? ` ${unread} unread.` : ''}`}
      />

      {!items.length ? (
        <Empty
          title="No alerts"
          hint="Scan a product and we will tell you if it is later recalled, nears expiry, or starts being sold above MRP nearby."
          action={<Link to="/scan" className="btn-primary">Scan a product</Link>}
        />
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <article
              key={a.id}
              className={clsx('surface border-l-4 p-4',
                TONE[a.severity ?? 'INFO'] ?? TONE.INFO,
                a.is_read && 'opacity-60',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="display text-lg font-semibold">{a.title}</h2>
                    <span className="chip bg-surface/70 text-[10px] text-ink-soft">
                      {TYPE_LABEL[a.alert_type] ?? a.alert_type}
                    </span>
                    {!a.is_read && <span className="size-2 rounded-full bg-accent" />}
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-ink-soft">{a.message}</p>
                  <p className="mt-1 text-xs text-ink-muted">{ago(a.created_at)}</p>
                </div>
                {!a.is_read && (
                  <button
                    type="button"
                    onClick={() => markRead.mutate(a.id)}
                    className="shrink-0 text-xs font-semibold text-accent"
                  >
                    Mark read
                  </button>
                )}
              </div>

              {a.barcode && (
                <Link
                  to={`/catalogue/${a.barcode}`}
                  className="mt-2 inline-block text-sm font-semibold text-accent"
                >
                  View this product →
                </Link>
              )}
            </article>
          ))}
        </div>
      )}
    </Page>
  );
}
