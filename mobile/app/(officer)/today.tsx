import { Feather } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { api, useAuth } from '@/api';
import { pendingCount, subscribe, sync, type QueuedCapture } from '@/queue';
import { bandFor, radius, space } from '@/theme';
import {
  Body, Button, Callout, Card, Chip, Empty, ErrorBox, Eyebrow, Loading, StatusChip,
  Title, ago, moneyShort, usePalette,
} from '@/ui';

function Stat({ label, value, hint, tone }: {
  label: string; value: string | number; hint?: string; tone?: 'bad' | 'warn' | 'ok';
}) {
  const p = usePalette();
  const colour = tone === 'bad' ? p.bad : tone === 'warn' ? p.warn : tone === 'ok' ? p.ok : p.ink;
  return (
    <Card style={{ flex: 1, minWidth: 150, padding: space.md }}>
      <Eyebrow>{label}</Eyebrow>
      <Text
        style={{
          color: colour, fontSize: 24, fontWeight: '800', marginTop: 4,
          fontVariant: ['tabular-nums'],
        }}
      >
        {value}
      </Text>
      {hint && <Text style={{ color: p.inkMuted, fontSize: 11, marginTop: 3 }}>{hint}</Text>}
    </Card>
  );
}

export default function OfficerHome() {
  const p = usePalette();
  const { user, logout } = useAuth();
  const router = useRouter();
  const [queue, setQueue] = useState<QueuedCapture[]>([]);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => subscribe(setQueue), []);

  const dash = useQuery({
    queryKey: ['officer', 'dashboard'],
    queryFn: () => api.officerDashboard(),
  });
  const recent = useQuery({
    queryKey: ['sessions', 'recent'],
    queryFn: () => api.listSessions({ page_size: 8, mine: true }),
  });

  const pending = pendingCount(queue);

  async function runSync() {
    setSyncing(true);
    try {
      const res = await sync();
      await Promise.all([dash.refetch(), recent.refetch()]);
      Alert.alert(
        'Sync complete',
        `${res.uploaded} inspection${res.uploaded === 1 ? '' : 's'} uploaded` +
        (res.failed ? `, ${res.failed} still waiting.` : '.'),
      );
    } finally {
      setSyncing(false);
    }
  }

  if (dash.isLoading) return <Loading label="Loading your day…" />;
  if (dash.error) return <ErrorBox error={dash.error} onRetry={() => dash.refetch()} />;

  const d = dash.data!;
  const festival = d.upcoming_festivals?.[0];

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}
      refreshControl={
        <RefreshControl
          refreshing={dash.isFetching && !dash.isLoading}
          onRefresh={() => { void dash.refetch(); void recent.refetch(); }}
          tintColor={p.accent}
        />
      }
    >
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space.md }}>
        <View style={{ flex: 1 }}>
          <Eyebrow>{d.officer.officer_id ?? 'Officer'}</Eyebrow>
          <Title size={26} style={{ marginTop: 2 }}>{d.officer.name ?? user?.full_name ?? 'Officer'}</Title>
          <Body muted size={13}>{d.officer.jurisdiction ?? 'No jurisdiction assigned'}</Body>
        </View>
        <Pressable
          onPress={() => {
            Alert.alert('Sign out', 'End this session on the device?', [
              { text: 'Cancel', style: 'cancel' },
              {
                text: 'Sign out', style: 'destructive',
                onPress: () => { void logout().then(() => router.replace('/login')); },
              },
            ]);
          }}
          hitSlop={10}
          style={{ padding: space.sm }}
        >
          <Feather name="log-out" size={18} color={p.inkMuted} />
        </Pressable>
      </View>

      {pending > 0 && (
        <Callout tone="warn" title={`${pending} inspection${pending === 1 ? '' : 's'} on this device`}>
          <View style={{ gap: space.sm }}>
            <Text style={{ color: p.warn, fontSize: 12.5, lineHeight: 18 }}>
              Captured but not yet with the department. They stay on the phone until
              they upload, so nothing is lost if you go out of signal.
            </Text>

            {/* The reason a capture is stuck belongs next to the capture, not
                buried in a toast that has already gone. A server rejection and
                a lost connection need different actions from the officer. */}
            {queue.filter((c) => c.status !== 'uploaded').map((c) => (
              <View
                key={c.id}
                style={{
                  backgroundColor: p.surface, borderRadius: radius.md,
                  padding: space.sm, gap: 3,
                }}
              >
                <Text style={{ color: p.ink, fontSize: 12.5, fontWeight: '700' }}>
                  {c.session.product_name || c.session.barcode || 'Unnamed commodity'}
                </Text>
                <Text style={{ color: p.inkMuted, fontSize: 11 }}>
                  {c.surfaces.length} surface{c.surfaces.length === 1 ? '' : 's'} ·{' '}
                  {c.surfaces.filter((s) => s.uploaded).length} already sent ·{' '}
                  {ago(new Date(c.createdAt).toISOString())}
                </Text>
                {c.lastError && (
                  <Text style={{ color: c.status === 'failed' ? p.bad : p.warn, fontSize: 11, lineHeight: 15 }}>
                    {c.status === 'failed' ? 'Refused: ' : 'Last attempt: '}{c.lastError}
                  </Text>
                )}
              </View>
            ))}

            <Button
              label={syncing ? 'Uploading…' : 'Upload now'}
              tone="ghost"
              busy={syncing}
              onPress={runSync}
            />
          </View>
        </Callout>
      )}

      {festival && festival.days_until <= 30 && (
        <Callout
          tone="warn"
          title={`${festival.festival} in ${festival.days_until} day${festival.days_until === 1 ? '' : 's'} — risk up to ${festival.peak_multiplier}×`}
        >
          {`Watch: ${festival.elevated_categories.slice(0, 4).join(', ').replace(/-/g, ' ')}`}
        </Callout>
      )}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
        <Stat
          label="Inspections"
          value={d.inspections.total}
          hint={`${d.inspections.this_week} this week`}
        />
        <Stat
          label="Flagged"
          value={d.inspections.flagged}
          tone={d.inspections.flagged ? 'bad' : undefined}
          hint="Non-compliant findings"
        />
        <Stat
          label="Penalty exposure"
          value={moneyShort(d.inspections.penalty_exposure)}
          tone="warn"
          hint="Across your inspections"
        />
        <Stat
          label="Citizen leads"
          value={d.queues.citizen_leads_pending}
          hint="Ordered by reporter trust"
        />
      </View>

      <Link href="/(officer)/capture" asChild>
        <Pressable>
          <Card tone="accent" style={{ flexDirection: 'row', alignItems: 'center', gap: space.md }}>
            <View
              style={{
                width: 40, height: 40, borderRadius: radius.md,
                backgroundColor: p.accent, alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Feather name="camera" size={18} color={p.accentFg} />
            </View>
            <View style={{ flex: 1 }}>
              <Title size={17}>Start an inspection</Title>
              <Body muted size={12.5}>Photograph each panel that carries declarations</Body>
            </View>
            <Feather name="chevron-right" size={18} color={p.inkFaint} />
          </Card>
        </Pressable>
      </Link>

      <View style={{ gap: space.sm }}>
        <Title size={19}>Recent inspections</Title>
        {recent.isLoading ? (
          <Loading />
        ) : !recent.data?.items.length ? (
          <Empty
            title="No inspections yet"
            hint="Capture a pack and it will appear here once the pipeline has run."
          />
        ) : (
          recent.data.items.map((s) => {
            const band = bandFor(s.overall_score);
            return (
              <Link key={s.session_id} href={`/session/${s.session_id}` as never} asChild>
                <Pressable>
                  <Card style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md }}>
                    <View
                      style={{
                        width: 44, height: 44, borderRadius: radius.pill,
                        borderWidth: 3, borderColor: p.score[band],
                        alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      <Text
                        style={{
                          color: p.score[band], fontWeight: '800', fontSize: 14,
                          fontVariant: ['tabular-nums'],
                        }}
                      >
                        {s.overall_score == null ? '—' : Math.round(s.overall_score)}
                      </Text>
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text numberOfLines={1} style={{ color: p.ink, fontWeight: '700', fontSize: 14.5 }}>
                        {s.product_name ?? 'Unidentified commodity'}
                      </Text>
                      <Text numberOfLines={1} style={{ color: p.inkMuted, fontSize: 12, marginTop: 1 }}>
                        {s.store_name ?? 'No store'} · {ago(s.created_at)}
                      </Text>
                      <View style={{ flexDirection: 'row', gap: 5, marginTop: 6, flexWrap: 'wrap' }}>
                        <StatusChip status={s.status} />
                        {s.violation_count > 0 && (
                          <Chip tone="bad">
                            {`${s.violation_count} finding${s.violation_count === 1 ? '' : 's'}`}
                          </Chip>
                        )}
                      </View>
                    </View>
                    <Feather name="chevron-right" size={16} color={p.inkFaint} />
                  </Card>
                </Pressable>
              </Link>
            );
          })
        )}
      </View>
    </ScrollView>
  );
}
