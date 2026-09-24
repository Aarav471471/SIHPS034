import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';

import { Page } from '@/components/motion';
import {
  Empty, ErrorBox, Loading, PageHeader, Section, StatusChip, ago,
} from '@/components/ui';
import { api } from '@/store/auth';

export default function Trust() {
  const trust = useQuery({ queryKey: ['trust'], queryFn: () => api.trustProfile() });
  const reports = useQuery({ queryKey: ['my-reports'], queryFn: () => api.myReports() });
  const board = useQuery({ queryKey: ['leaderboard'], queryFn: () => api.leaderboard() });

  if (trust.isLoading) return <Loading rows={3} />;
  if (trust.error) return <ErrorBox error={trust.error} retry={() => trust.refetch()} />;

  const t = trust.data!;
  const verified = t.trust_score > 80;

  return (
    <Page className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        eyebrow={<span className="eyebrow">Citizen standing</span>}
        title="Your reporting record"
        subtitle="Trust decides where your reports sit in an officer's queue. It is earned by being right, and it is the reason a verified reporter is acted on first."
      />

      <div className={clsx('surface p-6 text-center',
        verified ? 'border-ok/30 bg-ok-soft' : '',
      )}>
        <div className={clsx(
          'text-5xl font-black tabular-nums',
          verified ? 'text-ok' : 'text-accent',
        )}>
          {Math.round(t.trust_score)}
        </div>
        <p className="mt-1 text-sm font-bold">{t.badge.replace(/_/g, ' ')}</p>
        <p className="mt-1 text-xs text-ink-muted">
          Ranked {t.rank} of {t.total_reporters} reporters
        </p>

        {/* Progress toward the next badge, so the score is a goal rather than
            a number that just happens to you. */}
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface/70">
          <div
            className={clsx('h-full rounded-full', verified ? 'bg-ok' : 'bg-accent')}
            style={{ width: `${Math.min(100, t.trust_score)}%` }}
          />
        </div>

        {t.next_badge && t.reports_to_next_badge ? (
          <p className="mt-2 text-xs font-medium text-ink-soft">
            {t.reports_to_next_badge} more confirmed report
            {t.reports_to_next_badge === 1 ? '' : 's'} to become a{' '}
            {t.next_badge.replace(/_/g, ' ').toLowerCase()}
          </p>
        ) : (
          <p className="mt-2 text-xs font-medium text-ok">
            Your reports go to the top of the officer queue.
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          ['Submitted', t.reports_submitted, 'default'],
          ['Confirmed', t.reports_confirmed, 'good'],
          ['Not substantiated', t.reports_rejected, t.reports_rejected ? 'bad' : 'default'],
        ].map(([label, value, tone]) => (
          <div key={String(label)} className="surface p-4 text-center">
            <div className={clsx(
              'text-2xl font-bold tabular-nums',
              tone === 'good' && 'text-ok',
              tone === 'bad' && 'text-bad',
            )}>
              {value as number}
            </div>
            <div className="mt-1 text-xs text-ink-muted">{label}</div>
          </div>
        ))}
      </div>

      {t.accuracy_rate != null && (
        <div className="surface p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Accuracy</span>
            <span className="text-lg font-bold tabular-nums">{t.accuracy_rate}%</span>
          </div>
          <p className="mt-1 text-xs text-ink-muted">
            Share of your decided reports that officers confirmed.
          </p>
        </div>
      )}

      <div className="surface bg-surface-sunk p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          How it works
        </p>
        <p className="mt-1 text-sm leading-relaxed text-ink-soft">{t.how_it_works}</p>
      </div>

      <Section title="Your reports">
        {reports.isLoading ? (
          <Loading rows={2} />
        ) : !reports.data?.length ? (
          <Empty title="No reports yet" hint="Anything you file will appear here with its outcome." />
        ) : (
          <div className="space-y-2">
            {reports.data.map((r) => (
              <div key={r.report_ref} className="surface p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{r.store_name}</span>
                  <StatusChip status={r.status} />
                  <StatusChip status={r.violation_category} />
                  <span className="ml-auto font-mono text-xs text-ink-muted">
                    {r.report_ref}
                  </span>
                </div>
                {r.citizen_remarks && (
                  <p className="mt-1 text-sm italic text-ink-soft">“{r.citizen_remarks}”</p>
                )}
                {r.officer_notes && (
                  <p className="mt-2 rounded-lg bg-surface-sunk px-3 py-2 text-sm">
                    <span className="font-semibold">Officer: </span>{r.officer_notes}
                  </p>
                )}
                <p className="mt-1 text-xs text-ink-muted">Filed {ago(r.created_at)}</p>
              </div>
            ))}
          </div>
        )}
      </Section>

      {board.data && board.data.leaderboard.length > 0 && (
        <Section title="Top reporters">
          <div className="surface divide-y divide-line">
            {board.data.leaderboard.slice(0, 10).map((row) => (
              <div key={row.rank} className="flex items-center gap-3 p-3">
                <span className="w-6 text-center text-sm font-bold text-ink-muted">
                  {row.rank}
                </span>
                <span className="flex-1 font-medium">{row.display_name}</span>
                {row.verified && (
                  <span className="chip bg-ok-soft text-ok">Verified</span>
                )}
                <span className="text-sm font-bold tabular-nums">
                  {Math.round(row.trust_score)}
                </span>
              </div>
            ))}
          </div>
          <p className="text-xs text-ink-muted">{board.data.note}</p>
        </Section>
      )}
    </Page>
  );
}
