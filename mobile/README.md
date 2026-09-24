# MetriX — Android app

Expo React Native. Shares `packages/shared` with the web console, so the API
client, the token-refresh handling and every response type are one
implementation rather than two.

## Running it on a phone

The backend and the phone must be on the same network, and the app must be told
the machine's LAN address — a phone cannot reach the laptop's `localhost`.

1. Start the backend, bound to all interfaces rather than loopback:

```bash
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. Start Expo with the LAN address of that machine:

```bash
cd mobile && EXPO_PUBLIC_API_URL=http://172.20.185.197:8000 npx expo start
```

3. Install **Expo Go** on the phone and scan the QR code.

The login screen prints the address it will call, so if sign-in fails with a
connection error you can see immediately whether the address is wrong.

Find the address again with `ipconfig` (Windows) or `ifconfig` (macOS/Linux) —
it changes when the machine joins a different network.

## Building an installable APK

There is no Android SDK on the development machine, so `expo run:android` and
Gradle are not available locally. EAS builds it in the cloud instead:

```bash
npx eas-cli build --platform android --profile preview
```

That produces a downloadable `.apk`. It needs a free Expo account, and the
`EXPO_PUBLIC_API_URL` baked into the `preview` profile in `eas.json` must point
at a host the phone can actually reach — a LAN address only works while the
phone is on that network.

To verify a change bundles without a device:

```bash
npx expo export --platform android
```

## What is here

| Screen | Route | Notes |
|---|---|---|
| Sign in | `app/login.tsx` | Seeded demo accounts, one tap to fill |
| Officer — Today | `app/(officer)/index.tsx` | Queue counts, festival risk, recent inspections, offline queue |
| Officer — Inspect | `app/(officer)/capture.tsx` | Multi-surface camera, live barcode read, GPS, queues offline |
| Officer — Route | `app/(officer)/route.tsx` | Risk-ranked patrol, Leaflet map |
| Officer — Leads | `app/(officer)/leads.tsx` | Citizen reports ordered by reporter trust |
| Inspection | `app/session/[id].tsx` | Verdict, clause-by-clause findings, sealed evidence |
| Consumer — Scan | `app/(consumer)/scan.tsx` | Barcode scan, overcharge check |
| Consumer — Report | `app/(consumer)/report.tsx` | GPS-tagged, photographed citizen report |
| Consumer — Alerts | `app/(consumer)/alerts.tsx` | Recalls, expiry, trust standing |

`src/queue.ts` is the offline capture queue: photographs stay on the device
until they upload, resumable per surface so a retry does not re-send what
already landed.

## Deliberate choices

**Leaflet in a WebView, not `react-native-maps`.** On Android the latter uses
Google Maps, which renders a grey rectangle without a billed API key. Leaflet
over OpenStreetMap needs no key, works in Expo Go without a native rebuild, and
is the same tile source the web console uses.

**Tokens in `expo-secure-store`, not AsyncStorage.** An enforcement device may
be shared or seized; the Android Keystore is the right place for a credential.

**`legacy-peer-deps=true` in `.npmrc`.** Expo SDK 57 pins `react@19.2.3` while a
transitive `react-dom@19.2.8` asks for `react@^19.2.8`. npm refuses the tree
outright; Expo's own installer tolerates it. Pinning the policy in `.npmrc`
keeps later installs from half-pruning the dependency tree, which is how
`expo-asset` and `react-native-worklets` went missing during setup.

## Known limits

- **Push notifications are not wired.** Expo Go dropped remote push on Android
  in SDK 53, so it needs a development build to test. Alerts are polled and
  shown in-app instead, which is honest about what actually works today.
- **`usesCleartextTraffic` is enabled** so the app can talk to a plain-HTTP
  backend on a LAN. That must come out before anything ships beyond a demo.
- The consumer scan is a catalogue lookup, so it only recognises barcodes that
  exist in the database. A real pack off a shop shelf will report "not in the
  compliance catalogue yet" until it has been inspected or seeded.
