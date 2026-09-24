import { useQuery } from '@tanstack/react-query';
import { useLocalSearchParams } from 'expo-router';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api';
import { radius, space } from '@/theme';
import {
  Body, Callout, Card, Chip, ErrorBox, Eyebrow, Loading, StatusChip, Title, Verdict,
  money, usePalette, when,
} from '@/ui';

const SEVERITY_TONE = { CRITICAL: 'bad', MAJOR: 'warn', MINOR: 'warn' } as const;

export default function SessionDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const p = usePalette();

  const q = useQuery({
    queryKey: ['session', id],
    queryFn: () => api.getSession(id!),
    enabled: Boolean(id),
    // Poll while the pipeline runs. There is no WebSocket here: a phone that
    // sleeps drops the socket anyway, and a two-second poll over a handful of
    // seconds is cheaper than reconnect logic that has to survive backgrounding.
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === 'PENDING' || s === 'PROCESSING' ? 2000 : false;
    },
  });

  if (q.isLoading) return <Loading label="Loading the inspection…" />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;

  const s = q.data!;
  const running = s.status === 'PENDING' || s.status === 'PROCESSING';
  const fails = s.violations.filter((v) => v.status === 'FAIL');
  const warns = s.violations.filter((v) => v.status === 'WARNING');
  const verified = s.fields.filter((f) => f.ocr_agreement === true).length;

  // A pack the pipeline could not read is not a compliant pack. The same
  // fail-closed rule the console uses, for the same reason.
  const unassessable = !running && s.fields.length === 0;

  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}>
      <Verdict
        score={s.overall_score}
        state={running ? 'pending' : unassessable ? 'unassessable' : 'scored'}
        title={s.product_name ?? 'Unidentified commodity'}
        subtitle={`${s.brand_name ?? 'Brand not declared'} · ${s.store_name ?? 'No store recorded'}`}
        note={
          running
            ? 'The pipeline is still running. Nothing here is final until the validate stage completes.'
            : unassessable
              ? 'No declarations were read from this capture, so no clause could be tested. The score is withheld rather than defaulted.'
              : `${s.fields.length} declaration${s.fields.length === 1 ? '' : 's'} extracted, ${verified} confirmed by a second OCR pass over the same pixels.`
        }
      />

      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
        <StatusChip status={s.status} />
        {s.compliance_status && <StatusChip status={s.compliance_status} />}
        {s.jurisdiction_status === 'OUT_OF_BOUNDS' && <Chip tone="warn">Outside jurisdiction</Chip>}
        {s.is_locked && <Chip tone="neutral">Evidence locked</Chip>}
      </View>

      <Card>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.lg }}>
          {[
            ['Inspected', when(s.created_at)],
            ['Officer', s.officer_name ?? '—'],
            ['Confidence', s.confidence_score != null ? s.confidence_score.toFixed(2) : '—'],
            ['Penalty exposure', money(s.estimated_penalty)],
          ].map(([k, v]) => (
            <View key={k} style={{ minWidth: 120 }}>
              <Eyebrow>{k}</Eyebrow>
              <Text
                style={{
                  color: k === 'Penalty exposure' && s.estimated_penalty ? p.warn : p.ink,
                  fontWeight: '700', fontSize: 14, marginTop: 3,
                  fontVariant: ['tabular-nums'],
                }}
              >
                {v}
              </Text>
            </View>
          ))}
        </View>
      </Card>

      {/* --------------------------------------------------- findings ---- */}
      <View style={{ gap: space.sm }}>
        <Title size={19}>
          Findings ({fails.length} failed, {warns.length} advisory)
        </Title>
        <Body muted size={12.5}>Each finding cites its clause and the pixels that evidence it.</Body>

        {!s.violations.length ? (
          running ? (
            <Callout tone="info" title="Still checking">
              The validate stage has not run yet. Findings appear as soon as the
              rules engine has been applied.
            </Callout>
          ) : unassessable ? (
            <Callout tone="warn" title="Not assessable — nothing was extracted">
              No declarations could be read from the captured surfaces, so no clause
              could be tested. This is not a finding of compliance. Re-capture with
              the panel filling the frame, in even light, with the text in focus.
            </Callout>
          ) : (
            <Callout tone="ok" title="No contravention detected">
              {`All ${s.fields.length} extracted declaration${s.fields.length === 1 ? '' : 's'} passed every applicable clause.`}
            </Callout>
          )
        ) : (
          s.violations.map((v, i) => (
            <Card
              key={`${v.rule_id}-${i}`}
              style={{
                borderLeftWidth: 3,
                borderLeftColor: v.severity === 'CRITICAL' ? p.bad : p.warn,
                gap: space.sm,
              }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' }}>
                <Text style={{ color: p.ink, fontWeight: '700', fontSize: 15, flex: 1 }}>
                  {v.rule_name ?? v.rule_id}
                </Text>
                <Chip tone={SEVERITY_TONE[v.severity as keyof typeof SEVERITY_TONE] ?? 'warn'}>
                  {v.severity}
                </Chip>
              </View>

              {v.legal_clause && (
                <Text style={{ color: p.accent, fontSize: 11.5, fontWeight: '700' }}>
                  {v.legal_clause}
                </Text>
              )}
              <Text style={{ color: p.inkSoft, fontSize: 13.5, lineHeight: 20 }}>
                {v.evidence_text}
              </Text>

              {(v.calculated_value || v.expected_value) && (
                <View
                  style={{
                    flexDirection: 'row', gap: space.lg,
                    backgroundColor: p.surfaceSunk, borderRadius: radius.md, padding: space.md,
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Eyebrow>Observed</Eyebrow>
                    <Text style={{ color: p.ink, fontWeight: '700', marginTop: 2 }}>
                      {v.calculated_value ?? '—'}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Eyebrow>Required</Eyebrow>
                    <Text style={{ color: p.ok, fontWeight: '700', marginTop: 2 }}>
                      {v.expected_value ?? '—'}
                    </Text>
                  </View>
                </View>
              )}
            </Card>
          ))
        )}
      </View>

      {/* ---------------------------------------------------- evidence --- */}
      {s.images.length > 0 && (
        <View style={{ gap: space.sm }}>
          <Title size={19}>Evidence</Title>
          <Body muted size={12.5}>Sealed at capture with SHA-256.</Body>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
            {s.images.map((img) => (
              <View
                key={img.id}
                style={{
                  width: 150, borderRadius: radius.md, overflow: 'hidden',
                  borderWidth: StyleSheet.hairlineWidth * 2, borderColor: p.line,
                  backgroundColor: p.surface,
                }}
              >
                {/* Evidence is never decorated: no filter, no crop, no zoom that
                    changes what the officer sees. */}
                <Image
                  source={{ uri: api.resolveUrl(img.url) }}
                  style={{ width: 150, height: 190, backgroundColor: p.surfaceSunk }}
                  resizeMode="cover"
                />
                <View style={{ padding: space.sm }}>
                  <Text style={{ color: p.ink, fontSize: 11, fontWeight: '700' }}>
                    {img.surface_type}
                  </Text>
                  <Text numberOfLines={1} style={{ color: p.inkFaint, fontSize: 9.5, marginTop: 2 }}>
                    {img.sha256_hash?.slice(0, 24)}…
                  </Text>
                </View>
              </View>
            ))}
          </ScrollView>
        </View>
      )}
    </ScrollView>
  );
}
