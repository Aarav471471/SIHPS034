import { Feather } from '@expo/vector-icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Image, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { api } from '@/api';
import { radius, space } from '@/theme';
import {
  Body, Button, Card, Chip, Empty, ErrorBox, Eyebrow, Loading, Title, ago, money,
  usePalette,
} from '@/ui';

export default function Leads() {
  const p = usePalette();
  const qc = useQueryClient();
  const [open, setOpen] = useState<number | null>(null);

  const q = useQuery({ queryKey: ['leads'], queryFn: () => api.leads('SUBMITTED') });

  const decide = useMutation({
    // The API keys a verdict on the report_ref, not the numeric id, and its
    // verdicts are VERIFIED / REJECTED / INVESTIGATING.
    mutationFn: (v: {
      ref: string; verdict: 'VERIFIED' | 'REJECTED'; note: string;
    }) => api.decideLead(v.ref, v.verdict, v.note),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['leads'] }); },
    onError: (e) => Alert.alert('Could not record that', e instanceof Error ? e.message : ''),
  });

  if (q.isLoading) return <Loading label="Loading the queue…" />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;

  const items = q.data ?? [];

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: space.xxl }}
      refreshControl={
        <RefreshControl refreshing={q.isFetching && !q.isLoading} onRefresh={() => q.refetch()} tintColor={p.accent} />
      }
    >
      <View>
        <Eyebrow>Public tip-offs</Eyebrow>
        <Title size={24} style={{ marginTop: 2 }}>Citizen leads</Title>
        <Body muted size={13}>
          Ordered by reporter trust, not arrival time. A confirmed report raises the
          reporter&apos;s standing; a false one costs them twice as much.
        </Body>
      </View>

      {!items.length ? (
        <Empty
          title="Nothing waiting"
          hint="Reports submitted by consumers land here, highest-trust reporters first."
        />
      ) : (
        items.map((lead) => {
          const expanded = open === lead.id;
          return (
            <Card key={lead.id} style={{ gap: space.sm }}>
              <Pressable onPress={() => setOpen(expanded ? null : lead.id)}>
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space.sm }}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Title size={17}>{lead.store_name ?? 'Unnamed premises'}</Title>
                    <Text style={{ color: p.inkMuted, fontSize: 12, marginTop: 2 }}>
                      {lead.barcode ?? 'Commodity not identified'} · {ago(lead.created_at)}
                    </Text>
                  </View>
                  <Feather
                    name={expanded ? 'chevron-up' : 'chevron-down'}
                    size={18} color={p.inkFaint}
                  />
                </View>

                <View style={{ flexDirection: 'row', gap: 5, marginTop: space.sm, flexWrap: 'wrap' }}>
                  {/* priority_score is what orders this queue, so it is shown
                      rather than a label derived from it. */}
                  <Chip tone={lead.priority_score >= 70 ? 'bad' : lead.priority_score >= 40 ? 'warn' : 'neutral'}>
                    {`priority ${Math.round(lead.priority_score)}`}
                  </Chip>
                  <Chip tone={lead.reporter_verified ? 'ok' : 'neutral'}>
                    {`trust ${Math.round(lead.reporter_trust_score ?? 0)}`}
                  </Chip>
                  {lead.violation_category && (
                    <Chip tone="info">{lead.violation_category.replace(/_/g, ' ')}</Chip>
                  )}
                </View>
              </Pressable>

              {expanded && (
                <View style={{ gap: space.md }}>
                  {lead.citizen_remarks ? (
                    <Text style={{ color: p.inkSoft, fontSize: 13.5, lineHeight: 20 }}>
                      {lead.citizen_remarks}
                    </Text>
                  ) : null}

                  <View style={{ flexDirection: 'row', gap: space.lg, flexWrap: 'wrap' }}>
                    {lead.charged_price != null && (
                      <View>
                        <Eyebrow>Price charged</Eyebrow>
                        <Text style={{ color: p.bad, fontWeight: '700', fontSize: 15 }}>
                          {money(lead.charged_price)}
                        </Text>
                      </View>
                    )}
                    {lead.claimed_mrp != null && (
                      <View>
                        <Eyebrow>MRP on the pack</Eyebrow>
                        <Text style={{ color: p.ink, fontWeight: '700', fontSize: 15 }}>
                          {money(lead.claimed_mrp)}
                        </Text>
                      </View>
                    )}
                  </View>

                  {/* Citizen evidence is shown plain -- no crop, no filter. What
                      the reporter photographed is what the officer judges. */}
                  {lead.image_url && (
                    <Image
                      source={{ uri: api.resolveUrl(lead.image_url) }}
                      style={{
                        width: '100%', aspectRatio: 4 / 3,
                        borderRadius: radius.md, backgroundColor: p.surfaceSunk,
                      }}
                      resizeMode="cover"
                    />
                  )}

                  <View style={{ flexDirection: 'row', gap: space.sm }}>
                    <Button
                      label="Accept"
                      tone="ok"
                      style={{ flex: 1 }}
                      busy={decide.isPending}
                      onPress={() =>
                        decide.mutate({
                          ref: lead.report_ref, verdict: 'VERIFIED',
                          note: 'Accepted for field verification',
                        })
                      }
                    />
                    <Button
                      label="Reject"
                      tone="ghost"
                      style={{ flex: 1 }}
                      busy={decide.isPending}
                      onPress={() =>
                        Alert.alert(
                          'Reject this lead?',
                          'Rejecting reduces the reporter’s trust score, which lowers where their future reports sit in this queue.',
                          [
                            { text: 'Cancel', style: 'cancel' },
                            {
                              text: 'Reject',
                              style: 'destructive',
                              onPress: () => decide.mutate({
                                ref: lead.report_ref, verdict: 'REJECTED',
                                note: 'Not substantiated on review',
                              }),
                            },
                          ],
                        )
                      }
                    />
                  </View>
                </View>
              )}
            </Card>
          );
        })
      )}
    </ScrollView>
  );
}
