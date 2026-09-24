import { Feather } from '@expo/vector-icons';
import { useMutation } from '@tanstack/react-query';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import * as Location from 'expo-location';
import { useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';

import { api } from '@/api';
import { radius, space } from '@/theme';
import {
  Body, Button, Callout, Card, Chip, ErrorBox, Eyebrow, Title, Verdict, money,
  usePalette, when,
} from '@/ui';
import type { ScanResponse } from '@shared/types';

export default function Scan() {
  const p = usePalette();
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanning, setScanning] = useState(false);
  const [barcode, setBarcode] = useState('');
  const [price, setPrice] = useState('');
  const [store, setStore] = useState('');
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
  const [result, setResult] = useState<ScanResponse | null>(null);
  // A live camera fires the same barcode many times a second; without this the
  // lookup would be sent on every frame.
  const lastScan = useRef<string>('');

  useEffect(() => {
    void (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      try {
        const pos = await Location.getCurrentPositionAsync({});
        setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      } catch { /* a scan without a position is still useful */ }
    })();
  }, []);

  const lookup = useMutation({
    mutationFn: (code: string) => api.scan({
      barcode: code,
      mrp: price ? Number(price) : undefined,
      lat: gps?.lat,
      lng: gps?.lng,
      store_name: store || undefined,
    }),
    onSuccess: (res) => { setResult(res); setScanning(false); },
  });

  const onBarcode = useCallback((res: BarcodeScanningResult) => {
    if (res.data === lastScan.current) return;
    lastScan.current = res.data;
    setBarcode(res.data);
    lookup.mutate(res.data);
  }, [lookup]);

  if (!permission) return <View style={{ flex: 1, backgroundColor: p.bg }} />;

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}
      keyboardShouldPersistTaps="handled"
    >
      <View>
        <Eyebrow>Consumer check</Eyebrow>
        <Title size={26} style={{ marginTop: 2 }}>Scan before you buy</Title>
        <Body muted size={13}>
          Check the declared price and the compliance record of a packaged
          commodity before it reaches your basket.
        </Body>
      </View>

      {scanning ? (
        <View
          style={{
            aspectRatio: 3 / 4, borderRadius: radius.lg, overflow: 'hidden',
            backgroundColor: '#000',
          }}
        >
          {permission.granted ? (
            <CameraView
              style={{ flex: 1 }}
              facing="back"
              barcodeScannerSettings={{
                barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128'],
              }}
              onBarcodeScanned={onBarcode}
            >
              <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                <View
                  style={{
                    width: '76%', height: 110,
                    borderWidth: 2, borderColor: 'rgba(255,255,255,0.85)',
                    borderRadius: radius.sm,
                  }}
                />
                <Text style={{ color: '#fff', marginTop: space.lg, fontSize: 13 }}>
                  Hold the barcode inside the frame
                </Text>
              </View>
              <Pressable
                onPress={() => setScanning(false)}
                style={{
                  position: 'absolute', top: space.md, right: space.md,
                  backgroundColor: p.scrim, borderRadius: radius.pill,
                  paddingHorizontal: 12, paddingVertical: 6,
                }}
              >
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 12 }}>Close</Text>
              </Pressable>
            </CameraView>
          ) : (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg, gap: space.md }}>
              <Text style={{ color: '#fff', textAlign: 'center' }}>
                Camera access is needed to read a barcode.
              </Text>
              <Button label="Grant access" onPress={requestPermission} />
            </View>
          )}
        </View>
      ) : (
        <Button
          label="Scan a barcode"
          onPress={() => {
            lastScan.current = '';
            if (!permission.granted) { void requestPermission(); }
            setScanning(true);
          }}
          icon={<Feather name="maximize" size={16} color={p.accentFg} />}
        />
      )}

      <Card style={{ gap: space.md }}>
        <View>
          <Eyebrow>Barcode</Eyebrow>
          <TextInput
            value={barcode}
            onChangeText={setBarcode}
            keyboardType="number-pad"
            placeholder="8901234567890"
            placeholderTextColor={p.inkFaint}
            style={{
              backgroundColor: p.surfaceSunk, borderRadius: radius.md,
              paddingHorizontal: space.md, paddingVertical: 11, marginTop: 6,
              color: p.ink, fontSize: 15, fontVariant: ['tabular-nums'],
              borderWidth: StyleSheet.hairlineWidth * 2, borderColor: p.line,
            }}
          />
        </View>

        <View style={{ flexDirection: 'row', gap: space.md }}>
          <View style={{ flex: 1 }}>
            <Eyebrow>Price asked (₹)</Eyebrow>
            <TextInput
              value={price} onChangeText={setPrice} keyboardType="decimal-pad"
              placeholder="45.00" placeholderTextColor={p.inkFaint}
              style={{
                backgroundColor: p.surfaceSunk, borderRadius: radius.md,
                paddingHorizontal: space.md, paddingVertical: 11, marginTop: 6,
                color: p.ink, fontSize: 15, fontVariant: ['tabular-nums'],
                borderWidth: StyleSheet.hairlineWidth * 2, borderColor: p.line,
              }}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Eyebrow>Shop</Eyebrow>
            <TextInput
              value={store} onChangeText={setStore}
              placeholder="Optional" placeholderTextColor={p.inkFaint}
              style={{
                backgroundColor: p.surfaceSunk, borderRadius: radius.md,
                paddingHorizontal: space.md, paddingVertical: 11, marginTop: 6,
                color: p.ink, fontSize: 15,
                borderWidth: StyleSheet.hairlineWidth * 2, borderColor: p.line,
              }}
            />
          </View>
        </View>

        <Button
          label={lookup.isPending ? 'Checking…' : 'Check this pack'}
          busy={lookup.isPending}
          disabled={!barcode.trim()}
          onPress={() => lookup.mutate(barcode.trim())}
        />
        <Body muted size={11.5}>
          Telling us the price you were asked is what makes overcharge detection
          work — it is compared against the price other shoppers reported.
        </Body>
      </Card>

      {lookup.error && <ErrorBox error={lookup.error} onRetry={() => lookup.mutate(barcode)} />}

      {result && (
        <View style={{ gap: space.lg }}>
          {/* The overcharge warning leads, because it is the one thing that
              changes what the shopper does in the next ten seconds. */}
          {result.is_price_gouged && result.anomaly_warning && (
            <Card style={{ backgroundColor: p.bad, borderColor: p.bad, gap: space.sm }}>
              <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>
                PRICE CHECK
              </Text>
              <Title size={22} style={{ color: '#fff' }}>You are being overcharged</Title>
              {result.overcharge_amount != null && (
                <Text style={{ color: '#fff', fontSize: 34, fontWeight: '800', fontVariant: ['tabular-nums'] }}>
                  +{money(result.overcharge_amount)}
                </Text>
              )}
              <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 13, lineHeight: 19 }}>
                {result.anomaly_warning}
              </Text>
              <Button
                label="Report this shop"
                tone="ghost"
                onPress={() => router.push('/(consumer)/report')}
              />
            </Card>
          )}

          {!result.found ? (
            /* Not an error. The catalogue is built from field inspections, so a
               pack nobody has inspected yet is simply absent -- and saying that
               plainly, with what the scan still achieved, is more use than an
               apology that reads like a failure. */
            <Card style={{ gap: space.md }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
                <Feather name="search" size={18} color={p.inkMuted} />
                <Title size={19} style={{ flex: 1 }}>No record for this pack yet</Title>
              </View>

              <Body size={13}>
                The catalogue is built from inspections officers have actually
                carried out. This barcode has not been inspected yet, so there is
                no verified MRP to check the shelf price against.
              </Body>

              <View
                style={{
                  backgroundColor: p.okSoft, borderRadius: radius.md, padding: space.md,
                  gap: 3,
                }}
              >
                <Text style={{ color: p.ok, fontWeight: '700', fontSize: 12.5 }}>
                  Your scan still counted
                </Text>
                <Text style={{ color: p.ok, fontSize: 12, lineHeight: 17 }}>
                  {result.message}
                </Text>
              </View>

              <Text style={{ color: p.inkFaint, fontSize: 11.5, fontVariant: ['tabular-nums'] }}>
                Barcode {result.barcode ?? barcode}
              </Text>

              <Button
                label="Report a problem with this pack"
                tone="ghost"
                icon={<Feather name="flag" size={15} color={p.inkSoft} />}
                onPress={() => router.push('/(consumer)/report')}
              />
            </Card>
          ) : (
            <>
              <Verdict
                score={result.compliance_score}
                state={result.compliance_score == null ? 'unassessable' : 'scored'}
                title={result.product_name ?? 'Unidentified commodity'}
                subtitle={`${result.brand_name ?? ''}${result.category ? ` · ${result.category}` : ''}`}
                note={
                  result.total_inspections
                    ? `Based on ${result.total_inspections} inspection${result.total_inspections === 1 ? '' : 's'} on record, most recently ${when(result.last_inspected)}.`
                    : 'No inspection on record yet — this reflects the declared label only.'
                }
              />

              <Card>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.lg }}>
                  {[
                    ['Verified MRP', money(result.official_mrp)],
                    ['Net quantity', result.net_quantity ?? '—'],
                    ['Unit price', result.unit_price ?? '—'],
                    ['Origin', result.country_of_origin ?? '—'],
                  ].map(([k, v]) => (
                    <View key={k} style={{ minWidth: 130 }}>
                      <Eyebrow>{k}</Eyebrow>
                      <Text
                        style={{
                          color: p.ink, fontWeight: '700', fontSize: 15, marginTop: 3,
                          fontVariant: ['tabular-nums'],
                        }}
                      >
                        {v}
                      </Text>
                    </View>
                  ))}
                </View>
              </Card>

              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                <Chip tone={result.past_violations ? 'bad' : 'ok'}>
                  {`${result.past_violations} past violation${result.past_violations === 1 ? '' : 's'}`}
                </Chip>
                <Chip tone={result.fssai_verified ? 'ok' : 'neutral'}>
                  {result.fssai_number ? `FSSAI ${result.fssai_number}` : 'FSSAI not declared'}
                </Chip>
                {result.crowd_sample_count > 0 && (
                  <Chip tone="info">
                    {`Typically ${money(result.crowd_modal_mrp)} · ${result.crowd_sample_count} scans`}
                  </Chip>
                )}
              </View>

              {!result.is_price_gouged && result.scanned_mrp != null && (
                <Callout tone="ok" title="Price matches">
                  The price on this pack matches its declared MRP.
                </Callout>
              )}
            </>
          )}
        </View>
      )}
    </ScrollView>
  );
}
