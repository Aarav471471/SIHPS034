import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { api } from '@/api';
import { space } from '@/theme';
import {
  Body, Card, Chip, Empty, ErrorBox, Eyebrow, Loading, Title, ago,
  usePalette,
} from '@/ui';

const TONE = {
  CRITICAL: 'bad', WARNING: 'warn', INFO: 'info',
} as const;

export default function Alerts() {
  const p = usePalette();
  const qc = useQueryClient();

  const q = useQuery({ queryKey: ['alerts'], queryFn: () => api.alerts() });
  const trust = useQuery({ queryKey: ['trust'], queryFn: () => api.trustProfile() });

  const markRead = useMutation({
    mutationFn: (id: number) => api.markAlertRead(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['alerts'] }); },
  });

  if (q.isLoading) return <Loading label="Loading your alerts…" />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;

  const items = q.data ?? [];
  const unread = items.filter((a) => !a.is_read).length;

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}
      refreshControl={
        <RefreshControl
          refreshing={q.isFetching && !q.isLoading}
          onRefresh={() => { void q.refetch(); void trust.refetch(); }}
          tintColor={p.accent}
        />
      }
    >
      <View>
        <Eyebrow>Your watchlist</Eyebrow>
        <Title size={26} style={{ marginTop: 2 }}>Alerts</Title>
        <Body muted size={13}>
          Recalls, expiry warnings and overcharging notices for commodities you
          have scanned.{unread ? ` ${unread} unread.` : ''}
        </Body>
      </View>

      {/* Trust is the mechanism that makes citizen reporting worth an officer's
          attention, so the consumer is shown where they stand rather than left
          to guess why their reports are or are not acted on. */}
      {trust.data && (
        <Card tone="accent" style={{ gap: space.sm }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md }}>
            <Text
              style={{
                color: p.accent, fontSize: 34, fontWeight: '800',
                fontVariant: ['tabular-nums'],
              }}
            >
              {Math.round(trust.data.trust_score ?? 0)}
            </Text>
            <View style={{ flex: 1 }}>
              <Title size={16}>{trust.data.badge ?? 'Reporter'}</Title>
              <Body muted size={12}>
                {trust.data.reports_confirmed ?? 0} of {trust.data.reports_submitted ?? 0} reports confirmed
              </Body>
            </View>
          </View>
        </Card>
      )}

      {!items.length ? (
        <Empty
          title="Nothing to flag"
          hint="Scan a product and you will be told here if it is recalled, expiring, or being sold over its declared MRP."
        />
      ) : (
        items.map((a) => (
          <Pressable
            key={a.id}
            onPress={() => { if (!a.is_read) markRead.mutate(a.id); }}
          >
            <Card
              style={{
                borderLeftWidth: 3,
                borderLeftColor:
                  a.severity === 'CRITICAL' ? p.bad : a.severity === 'WARNING' ? p.warn : p.lineStrong,
                opacity: a.is_read ? 0.65 : 1,
                gap: space.sm,
              }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space.sm }}>
                <Title size={16} style={{ flex: 1 }}>{a.title}</Title>
                {!a.is_read && (
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: p.accent, marginTop: 6 }} />
                )}
              </View>
              <Text style={{ color: p.inkSoft, fontSize: 13, lineHeight: 19 }}>{a.message}</Text>
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                <Chip tone={TONE[a.severity as keyof typeof TONE] ?? 'info'}>{a.severity}</Chip>
                {a.alert_type && <Chip tone="neutral">{a.alert_type.replace(/_/g, ' ')}</Chip>}
                <Chip tone="neutral">{ago(a.created_at)}</Chip>
              </View>
            </Card>
          </Pressable>
        ))
      )}
    </ScrollView>
  );
}
