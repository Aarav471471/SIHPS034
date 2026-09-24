import { Feather } from '@expo/vector-icons';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import * as Location from 'expo-location';
import { useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';

import { enqueue, uploadOne } from '@/queue';
import { radius, space } from '@/theme';
import {
  Body, Button, Callout, Card, Chip, Eyebrow, Title, usePalette,
} from '@/ui';

/**
 * Surfaces worth photographing.
 *
 * FRONT is required because the principal display panel is where Rule 7 puts
 * the declarations that matter. A SECOND surface is what converts "this
 * declaration is missing" from a guess into a finding: without it, an absent
 * MRP is merely unphotographed, and the rules engine says so rather than
 * issuing a notice on an incomplete capture.
 */
const SURFACES = ['FRONT', 'BACK', 'SIDE', 'TOP', 'BOTTOM'] as const;
type Surface = (typeof SURFACES)[number];

interface Shot { surface: Surface; uri: string }

export default function Capture() {
  const p = usePalette();
  const router = useRouter();
  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();

  const [cameraOn, setCameraOn] = useState(false);
  const [surface, setSurface] = useState<Surface>('FRONT');
  const [shots, setShots] = useState<Shot[]>([]);
  const [busy, setBusy] = useState(false);

  const [productName, setProductName] = useState('');
  const [brandName, setBrandName] = useState('');
  const [barcode, setBarcode] = useState('');
  const [storeName, setStoreName] = useState('');
  const [widthCm, setWidthCm] = useState('');
  const [heightCm, setHeightCm] = useState('');
  const [gps, setGps] = useState<Location.LocationObjectCoords | null>(null);
  const [gpsState, setGpsState] = useState<'idle' | 'locating' | 'ok' | 'denied'>('idle');

  const captured = new Set(shots.map((s) => s.surface));

  const locate = useCallback(async () => {
    setGpsState('locating');
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') { setGpsState('denied'); return; }
    try {
      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      setGps(pos.coords);
      setGpsState('ok');
    } catch {
      setGpsState('denied');
    }
  }, []);

  useEffect(() => { void locate(); }, [locate]);

  // Barcode is read live off the preview rather than typed. It is the single
  // most error-prone field to key by hand, and a wrong one attaches the
  // inspection to the wrong commodity.
  const onBarcode = useCallback((res: BarcodeScanningResult) => {
    setBarcode((current) => (current ? current : res.data));
  }, []);

  async function shoot() {
    if (!cameraRef.current || busy) return;
    setBusy(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        // The pipeline measures character heights in millimetres from these
        // pixels, so the image must not be downscaled or re-encoded on the way
        // out -- an upstream resize silently changes every measurement.
        skipProcessing: false,
      });
      if (!photo?.uri) return;
      setShots((prev) => [...prev.filter((s) => s.surface !== surface), { surface, uri: photo.uri }]);

      const next = SURFACES.find((s) => s !== surface && !captured.has(s));
      if (next) setSurface(next);
    } catch (err) {
      Alert.alert('Capture failed', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!shots.length) {
      Alert.alert('Nothing captured', 'Photograph at least the front panel.');
      return;
    }
    setBusy(true);
    try {
      const item = await enqueue(
        {
          product_name: productName.trim() || undefined,
          brand_name: brandName.trim() || undefined,
          barcode: barcode.trim() || undefined,
          store_name: storeName.trim() || undefined,
          package_width_cm: widthCm ? Number(widthCm) : undefined,
          package_height_cm: heightCm ? Number(heightCm) : undefined,
          latitude: gps?.latitude,
          longitude: gps?.longitude,
          captured_at: new Date().toISOString(),
        },
        shots.map((s) => ({ uri: s.uri, surface: s.surface })),
      );

      // Try immediately, but the capture is already safe on the device: a
      // failure here is a queued item, not a lost inspection.
      try {
        const sessionId = await uploadOne(item);
        reset();
        router.push(`/session/${sessionId}` as never);
      } catch (err) {
        reset();
        // Say which of the two it actually was. "Queued, retry when you have
        // signal" is right for a lost connection and actively misleading for a
        // server rejection, which will fail identically forever.
        const status = (err as { status?: number })?.status;
        const detail = err instanceof Error ? err.message : 'Unknown error';
        const rejected = typeof status === 'number' && status >= 400;

        Alert.alert(
          rejected ? 'The server refused this capture' : 'Saved on this device',
          rejected
            ? `${detail}\n\nIt is still on the phone under Today, but retrying will not help until this is fixed.`
            : `${detail}\n\nThe inspection is queued and nothing is lost. Send it from the Today tab once you are back in signal.`,
        );
      }
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setShots([]);
    setProductName(''); setBrandName(''); setBarcode('');
    setStoreName(''); setWidthCm(''); setHeightCm('');
    setSurface('FRONT');
    setCameraOn(false);
  }

  const field = {
    backgroundColor: p.surface,
    borderColor: p.line,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: 11,
    color: p.ink,
    fontSize: 15,
    marginTop: 6,
  };

  if (!permission) return <View style={{ flex: 1, backgroundColor: p.bg }} />;

  if (!permission.granted) {
    return (
      <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg }}>
        <Title size={22}>Camera access is required</Title>
        <Body>
          An inspection is a photograph of the printed panel. Without the camera
          there is nothing for the engine to read, and no evidence to seal.
        </Body>
        <Button label="Grant camera access" onPress={requestPermission} />
      </ScrollView>
    );
  }

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl * 2 }}
      keyboardShouldPersistTaps="handled"
    >
      {/* --------------------------------------------------- viewfinder -- */}
      <View
        style={{
          aspectRatio: 3 / 4, borderRadius: radius.lg, overflow: 'hidden',
          backgroundColor: '#000',
        }}
      >
        {cameraOn ? (
          <CameraView
            ref={cameraRef}
            style={{ flex: 1 }}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'qr'] }}
            onBarcodeScanned={onBarcode}
          >
            <View style={{ flex: 1, justifyContent: 'space-between' }}>
              <View style={{ padding: space.md, flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
                <View style={{ backgroundColor: p.scrim, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 }}>
                  <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>
                    {surface}
                  </Text>
                </View>
                {barcode ? (
                  <View style={{ backgroundColor: p.scrim, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 }}>
                    <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>
                      {barcode}
                    </Text>
                  </View>
                ) : null}
              </View>

              {/* A framing guide, not an accuracy claim. The engine measures
                  from the pixels; this only helps the officer fill the frame. */}
              <View style={{ alignItems: 'center' }}>
                <View
                  style={{
                    width: '78%', aspectRatio: 1.4,
                    borderWidth: 2, borderColor: 'rgba(255,255,255,0.75)',
                    borderRadius: radius.sm,
                  }}
                />
              </View>

              <View
                style={{
                  padding: space.lg, flexDirection: 'row',
                  alignItems: 'center', justifyContent: 'space-between',
                  backgroundColor: p.scrim,
                }}
              >
                <Pressable onPress={() => setCameraOn(false)} hitSlop={12}>
                  <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Close</Text>
                </Pressable>
                <Pressable
                  onPress={shoot}
                  disabled={busy}
                  accessibilityLabel={`Capture the ${surface} surface`}
                  style={{
                    width: 68, height: 68, borderRadius: 34,
                    borderWidth: 4, borderColor: '#fff',
                    backgroundColor: busy ? 'rgba(255,255,255,0.3)' : p.ok,
                  }}
                />
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>
                  {shots.length}/5
                </Text>
              </View>
            </View>
          </CameraView>
        ) : (
          <Pressable
            onPress={() => setCameraOn(true)}
            style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md }}
          >
            <Feather name="camera" size={32} color="rgba(255,255,255,0.85)" />
            <Text style={{ color: '#fff', fontWeight: '700' }}>Open the camera</Text>
            <Text style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>
              Fill the frame with one printed panel
            </Text>
          </Pressable>
        )}
      </View>

      {/* ---------------------------------------------- surface selector -- */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
        {SURFACES.map((s) => {
          const done = captured.has(s);
          const active = s === surface;
          return (
            <Pressable
              key={s}
              onPress={() => { setSurface(s); setCameraOn(true); }}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 5,
                paddingHorizontal: 12, paddingVertical: 7,
                borderRadius: radius.pill,
                borderWidth: StyleSheet.hairlineWidth * 2,
                borderColor: active ? p.accent : done ? p.ok : p.lineStrong,
                backgroundColor: active ? p.accent : done ? p.okSoft : p.surface,
              }}
            >
              {done && <Feather name="check" size={12} color={active ? p.accentFg : p.ok} />}
              <Text
                style={{
                  fontSize: 12, fontWeight: '700',
                  color: active ? p.accentFg : done ? p.ok : p.inkSoft,
                }}
              >
                {s}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {shots.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {shots.map((s) => (
            <View key={s.surface} style={{ borderRadius: radius.md, overflow: 'hidden' }}>
              <Image source={{ uri: s.uri }} style={{ width: 88, height: 110 }} />
              <View
                style={{
                  position: 'absolute', left: 0, right: 0, bottom: 0,
                  backgroundColor: p.scrim, paddingVertical: 3,
                }}
              >
                <Text style={{ color: '#fff', fontSize: 9.5, fontWeight: '700', textAlign: 'center' }}>
                  {s.surface}
                </Text>
              </View>
              <Pressable
                onPress={() => setShots((prev) => prev.filter((x) => x.surface !== s.surface))}
                hitSlop={8}
                style={{
                  position: 'absolute', right: 4, top: 4,
                  width: 20, height: 20, borderRadius: 10,
                  backgroundColor: p.scrim, alignItems: 'center', justifyContent: 'center',
                }}
              >
                <Feather name="x" size={12} color="#fff" />
              </Pressable>
            </View>
          ))}
        </ScrollView>
      )}

      {shots.length === 1 && (
        <Callout tone="info" title="One surface photographed">
          A second surface lets the engine prove a declaration is absent rather
          than merely unphotographed. With only the front, a missing MRP is
          reported as unproven.
        </Callout>
      )}

      {/* -------------------------------------------------- particulars -- */}
      <Card style={{ gap: space.md }}>
        <Title size={18}>Commodity</Title>

        <View>
          <Eyebrow>Product name</Eyebrow>
          <TextInput
            style={field} value={productName} onChangeText={setProductName}
            placeholder="Parle-G Original Glucose Biscuits"
            placeholderTextColor={p.inkFaint}
          />
        </View>
        <View>
          <Eyebrow>Brand / manufacturer</Eyebrow>
          <TextInput
            style={field} value={brandName} onChangeText={setBrandName}
            placeholder="Parle Products" placeholderTextColor={p.inkFaint}
          />
        </View>
        <View>
          <Eyebrow>Barcode</Eyebrow>
          <TextInput
            style={[field, { fontVariant: ['tabular-nums'] }]}
            value={barcode} onChangeText={setBarcode} keyboardType="number-pad"
            placeholder="Scanned from the pack" placeholderTextColor={p.inkFaint}
          />
        </View>

        <View style={{ flexDirection: 'row', gap: space.md }}>
          <View style={{ flex: 1 }}>
            <Eyebrow>Pack width (cm)</Eyebrow>
            <TextInput
              style={field} value={widthCm} onChangeText={setWidthCm}
              keyboardType="decimal-pad" placeholder="12.0" placeholderTextColor={p.inkFaint}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Eyebrow>Pack height (cm)</Eyebrow>
            <TextInput
              style={field} value={heightCm} onChangeText={setHeightCm}
              keyboardType="decimal-pad" placeholder="18.0" placeholderTextColor={p.inkFaint}
            />
          </View>
        </View>

        <Body muted size={12}>
          Pack dimensions set the minimum permitted character height under Rule 7(2).
          Without them the height check cannot run, and the engine says so rather
          than guessing.
        </Body>
      </Card>

      <Card style={{ gap: space.md }}>
        <Title size={18}>Location</Title>
        <View>
          <Eyebrow>Store / premises</Eyebrow>
          <TextInput
            style={field} value={storeName} onChangeText={setStoreName}
            placeholder="Sharma Supermart" placeholderTextColor={p.inkFaint}
          />
        </View>

        {gpsState === 'ok' && gps ? (
          <Chip tone="ok" icon={<Feather name="map-pin" size={11} color={p.ok} />}>
            {`GPS ${gps.latitude.toFixed(5)}, ${gps.longitude.toFixed(5)} (±${Math.round(gps.accuracy ?? 0)} m)`}
          </Chip>
        ) : gpsState === 'locating' ? (
          <Chip tone="info">Locating…</Chip>
        ) : (
          <View style={{ gap: space.sm }}>
            <Callout tone="warn" title="No location fix">
              A finding that cannot be tied to premises is much harder to act on.
            </Callout>
            <Button label="Try again" tone="ghost" onPress={locate} />
          </View>
        )}
      </Card>

      <Button
        label={shots.length ? `Submit ${shots.length} surface${shots.length === 1 ? '' : 's'}` : 'Photograph a panel first'}
        onPress={submit}
        disabled={!shots.length}
        busy={busy}
      />
    </ScrollView>
  );
}
