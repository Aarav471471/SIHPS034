import { Feather } from '@expo/vector-icons';
import { useMutation } from '@tanstack/react-query';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Location from 'expo-location';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';

import { api } from '@/api';
import { fileForUpload } from '@/upload';
import { radius, space } from '@/theme';
import {
  Body, Button, Callout, Card, Chip, ErrorBox, Eyebrow, Title, usePalette,
} from '@/ui';

// These are the ReportCategory values the API validates against. Inventing
// friendlier keys here just produces a 422 the reporter cannot act on.
const TYPES = [
  { key: 'OVERCHARGING', label: 'Charged over MRP' },
  { key: 'MISSING_MRP', label: 'No MRP printed' },
  { key: 'MISSING_EXPIRY', label: 'No expiry date' },
  { key: 'EXPIRED_STOCK', label: 'Expired stock' },
  { key: 'MISSING_NET_QTY', label: 'No net quantity' },
  { key: 'OTHER', label: 'Something else' },
] as const;

export default function ReportForm() {
  const p = usePalette();
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();

  const [cameraOn, setCameraOn] = useState(false);
  const [photo, setPhoto] = useState<string | null>(null);
  const [type, setType] = useState<string>('OVERCHARGING');
  const [store, setStore] = useState('');
  const [barcode, setBarcode] = useState('');
  const [claimedMrp, setClaimedMrp] = useState('');
  const [pricePaid, setPricePaid] = useState('');
  const [description, setDescription] = useState('');
  const [gps, setGps] = useState<Location.LocationObjectCoords | null>(null);
  const [gpsState, setGpsState] = useState<'idle' | 'locating' | 'ok' | 'denied'>('idle');
  const [done, setDone] = useState<string | null>(null);

  const locate = useCallback(async () => {
    setGpsState('locating');
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') { setGpsState('denied'); return; }
    try {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setGps(pos.coords);
      setGpsState('ok');
    } catch { setGpsState('denied'); }
  }, []);

  useEffect(() => { void locate(); }, [locate]);

  const submit = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      // store_name and violation_category are required by the endpoint; the
      // rest are optional. The names are the endpoint's, not friendlier
      // synonyms -- a mismatch here is a 422 the reporter cannot act on.
      form.append('store_name', store.trim());
      form.append('violation_category', type);
      if (barcode.trim()) form.append('barcode', barcode.trim());
      if (pricePaid) form.append('charged_price', pricePaid);
      if (claimedMrp) form.append('claimed_mrp', claimedMrp);
      if (description.trim()) form.append('remarks', description.trim());
      if (gps) {
        form.append('latitude', String(gps.latitude));
        form.append('longitude', String(gps.longitude));
      }
      if (photo) {
        // Same constraint as the officer capture path: Expo's fetch needs the
        // bytes, not a uri descriptor.
        form.append('image', fileForUpload(photo), 'report.jpg');
      }
      return api.submitReport(form);
    },
    onSuccess: (res) => {
      setDone(res.queue_guidance ?? `Report ${res.report_id} received.`);
      setPhoto(null); setStore(''); setBarcode(''); setPricePaid('');
      setClaimedMrp(''); setDescription('');
    },
  });

  async function shoot() {
    const shot = await cameraRef.current?.takePictureAsync({ quality: 0.8 });
    if (shot?.uri) { setPhoto(shot.uri); setCameraOn(false); }
  }

  const field = {
    backgroundColor: p.surfaceSunk,
    borderColor: p.line,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: 11,
    color: p.ink,
    fontSize: 15,
    marginTop: 6,
  };

  if (done) {
    return (
      <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg }}>
        <Callout tone="ok" title="Report submitted">{done}</Callout>
        <Body>
          It joins the enforcement queue ordered by reporter trust. If an officer
          confirms it, your trust score rises and your future reports are seen
          sooner.
        </Body>
        <Button label="Submit another" tone="ghost" onPress={() => setDone(null)} />
      </ScrollView>
    );
  }

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}
      keyboardShouldPersistTaps="handled"
    >
      <View>
        <Eyebrow>Citizen report</Eyebrow>
        <Title size={26} style={{ marginTop: 2 }}>Report a violation</Title>
        <Body muted size={13}>
          This goes into a Legal Metrology enforcement queue. A photograph and a
          location fix make it far more actionable.
        </Body>
      </View>

      {cameraOn && permission?.granted ? (
        <View style={{ aspectRatio: 3 / 4, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#000' }}>
          <CameraView ref={cameraRef} style={{ flex: 1 }} facing="back">
            <View style={{ flex: 1, justifyContent: 'flex-end', alignItems: 'center', paddingBottom: space.xl }}>
              <Pressable
                onPress={shoot}
                style={{
                  width: 64, height: 64, borderRadius: 32,
                  borderWidth: 4, borderColor: '#fff', backgroundColor: p.ok,
                }}
              />
            </View>
            <Pressable
              onPress={() => setCameraOn(false)}
              style={{
                position: 'absolute', top: space.md, right: space.md,
                backgroundColor: p.scrim, borderRadius: radius.pill,
                paddingHorizontal: 12, paddingVertical: 6,
              }}
            >
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 12 }}>Close</Text>
            </Pressable>
          </CameraView>
        </View>
      ) : photo ? (
        <View>
          <Image
            source={{ uri: photo }}
            style={{ width: '100%', aspectRatio: 4 / 3, borderRadius: radius.lg }}
          />
          <Pressable
            onPress={() => setPhoto(null)}
            style={{
              position: 'absolute', right: space.sm, top: space.sm,
              backgroundColor: p.scrim, borderRadius: radius.pill,
              paddingHorizontal: 10, paddingVertical: 5,
            }}
          >
            <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>Remove</Text>
          </Pressable>
        </View>
      ) : (
        <Button
          label="Photograph the pack or the bill"
          tone="ghost"
          icon={<Feather name="camera" size={16} color={p.inkSoft} />}
          onPress={() => {
            if (!permission?.granted) { void requestPermission(); }
            setCameraOn(true);
          }}
        />
      )}

      <Card style={{ gap: space.md }}>
        <View>
          <Eyebrow>What happened</Eyebrow>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {TYPES.map((t) => (
              <Pressable
                key={t.key}
                onPress={() => setType(t.key)}
                style={{
                  paddingHorizontal: 12, paddingVertical: 7,
                  borderRadius: radius.pill,
                  backgroundColor: type === t.key ? p.accent : p.surfaceSunk,
                }}
              >
                <Text
                  style={{
                    fontSize: 12, fontWeight: '700',
                    color: type === t.key ? p.accentFg : p.inkMuted,
                  }}
                >
                  {t.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View>
          <Eyebrow>Shop</Eyebrow>
          <TextInput
            style={field} value={store} onChangeText={setStore}
            placeholder="Sharma Supermart (required)" placeholderTextColor={p.inkFaint}
          />
        </View>
        <View>
          <Eyebrow>Barcode (optional)</Eyebrow>
          <TextInput
            style={[field, { fontVariant: ['tabular-nums'] }]}
            value={barcode} onChangeText={setBarcode} keyboardType="number-pad"
            placeholder="8901234567890" placeholderTextColor={p.inkFaint}
          />
        </View>

        <View style={{ flexDirection: 'row', gap: space.md }}>
          <View style={{ flex: 1 }}>
            <Eyebrow>MRP on pack (₹)</Eyebrow>
            <TextInput
              style={[field, { fontVariant: ['tabular-nums'] }]}
              value={claimedMrp} onChangeText={setClaimedMrp} keyboardType="decimal-pad"
              placeholder="35.00" placeholderTextColor={p.inkFaint}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Eyebrow>Price charged (₹)</Eyebrow>
            <TextInput
              style={[field, { fontVariant: ['tabular-nums'] }]}
              value={pricePaid} onChangeText={setPricePaid} keyboardType="decimal-pad"
              placeholder="45.00" placeholderTextColor={p.inkFaint}
            />
          </View>
        </View>
        <View>
          <Eyebrow>What you saw</Eyebrow>
          <TextInput
            style={[field, { minHeight: 90, textAlignVertical: 'top' }]}
            value={description} onChangeText={setDescription}
            multiline
            placeholder="The MRP printed on the pack was ₹35 but the shop charged ₹45."
            placeholderTextColor={p.inkFaint}
          />
        </View>

        {gpsState === 'ok' && gps ? (
          <Chip tone="ok" icon={<Feather name="map-pin" size={11} color={p.ok} />}>
            {`Location recorded (±${Math.round(gps.accuracy ?? 0)} m)`}
          </Chip>
        ) : gpsState === 'locating' ? (
          <Chip tone="info">Getting your location…</Chip>
        ) : (
          <Callout tone="warn" title="No location">
            Without a position an officer cannot tell which premises this concerns.
          </Callout>
        )}
      </Card>

      {submit.error && <ErrorBox error={submit.error} />}

      <Button
        label={submit.isPending ? 'Submitting…' : 'Submit report'}
        busy={submit.isPending}
        disabled={!store.trim()}
        onPress={() => submit.mutate()}
      />
      <Body muted size={11.5}>
        A confirmed report raises your trust score. A false one costs twice as
        much, which is what keeps this queue worth an officer&apos;s time.
      </Body>
    </ScrollView>
  );
}
