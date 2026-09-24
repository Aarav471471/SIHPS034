/**
 * API access and session state for the mobile app.
 *
 * The transport is the same `MetrixClient` the web PWA uses, imported straight
 * from packages/shared. Sharing it is the point: an endpoint added once is
 * available on both surfaces, and the token-refresh collapsing that took real
 * effort to get right is not reimplemented here with subtly different bugs.
 *
 * What differs is persistence. The browser keeps tokens in localStorage; a
 * phone should not, because the device may be shared or seized. Tokens go into
 * expo-secure-store, which is backed by the Android Keystore.
 */
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { MetrixClient, type Tokens } from '@shared/client';
import type { UserProfile } from '@shared/types';

const TOKEN_KEY = 'metrix.tokens';

/**
 * Where the API lives.
 *
 * Derived from the Metro host by default rather than configured. The phone has
 * just downloaded its JavaScript bundle from the development machine, so that
 * machine's address is known-good and known-reachable -- guessing it, or asking
 * the operator to type it into an environment variable, is how you end up
 * pointed at `10.0.2.2` (the emulator's host alias) on a physical device and
 * staring at a connection error that says nothing about the real cause.
 *
 * Precedence:
 *   1. EXPO_PUBLIC_API_URL, when someone deliberately set it (and for release
 *      builds, where there is no Metro host to read).
 *   2. The Metro host, with the API's port substituted.
 *   3. The emulator alias, which is only ever right inside an emulator.
 */
const API_PORT = 8000;

function hostFromExpo(): string | null {
  // hostUri looks like "172.20.185.197:8081" in dev and is absent in a
  // standalone build.
  const hostUri =
    Constants.expoConfig?.hostUri
    ?? (Constants.expoGoConfig as { debuggerHost?: string } | undefined)?.debuggerHost
    ?? null;
  if (!hostUri) return null;
  const host = hostUri.split('/')[0].split(':')[0].trim();
  return host || null;
}

function resolveApiBase(): string {
  const explicit = process.env.EXPO_PUBLIC_API_URL?.trim();
  if (explicit) return explicit.replace(/\/$/, '');

  const host = hostFromExpo();
  if (host) return `http://${host}:${API_PORT}`;

  return `http://10.0.2.2:${API_PORT}`;
}

export const API_BASE = resolveApiBase();

/** Shown on the login screen so a connection failure names its own cause. */
export const API_BASE_SOURCE =
  process.env.EXPO_PUBLIC_API_URL?.trim()
    ? 'EXPO_PUBLIC_API_URL'
    : hostFromExpo()
      ? 'auto-detected from the Expo dev server'
      : 'emulator fallback';

let cachedTokens: Tokens | null = null;

/**
 * Token storage, with a web fallback.
 *
 * expo-secure-store has no web implementation -- its `.web.js` is an empty
 * object -- so on `expo start --web` every read and write throws and the
 * session cannot survive a reload. That makes the browser useless for
 * developing or demonstrating anything behind a login.
 *
 * On native the Android Keystore is used and is the right place for a
 * credential on a device that may be shared or seized. On web there is no
 * equivalent, so localStorage is the honest substitute: no worse than the PWA
 * console already does, and confined to a context that is never the field
 * device.
 */
const isWeb = Platform.OS === 'web';

async function writeToken(value: string | null): Promise<void> {
  if (isWeb) {
    if (value === null) globalThis.localStorage?.removeItem(TOKEN_KEY);
    else globalThis.localStorage?.setItem(TOKEN_KEY, value);
    return;
  }
  if (value === null) await SecureStore.deleteItemAsync(TOKEN_KEY);
  else await SecureStore.setItemAsync(TOKEN_KEY, value);
}

async function readToken(): Promise<string | null> {
  if (isWeb) return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null;
  return SecureStore.getItemAsync(TOKEN_KEY);
}

async function persist(tokens: Tokens | null): Promise<void> {
  cachedTokens = tokens;
  try {
    await writeToken(tokens ? JSON.stringify(tokens) : null);
  } catch {
    // A keystore failure must not take the app down mid-inspection; the
    // session simply will not survive a restart.
  }
}

let onUnauthorizedHook: (() => void) | null = null;

export const api = new MetrixClient({
  baseUrl: API_BASE,
  onTokens: (t) => { void persist(t); },
  onUnauthorized: () => { onUnauthorizedHook?.(); },
});

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorizedHook = fn;
}

export async function restoreSession(): Promise<Tokens | null> {
  if (cachedTokens) return cachedTokens;
  try {
    const raw = await readToken();
    if (!raw) return null;
    const tokens = JSON.parse(raw) as Tokens;
    api.setTokens(tokens);
    cachedTokens = tokens;
    return tokens;
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ session --
export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

interface AuthState {
  status: AuthStatus;
  user: UserProfile | null;
  error: string | null;
  busy: boolean;
}

const listeners = new Set<(s: AuthState) => void>();
let state: AuthState = { status: 'loading', user: null, error: null, busy: false };

function emit(next: Partial<AuthState>): void {
  state = { ...state, ...next };
  listeners.forEach((l) => l(state));
}

/**
 * A tiny store rather than Context.
 *
 * The auth state is read by the router guard, the API error handler and several
 * screens. A module-level store keeps all three reading the same value without
 * threading a provider through a file-based route tree.
 */
export function useAuth() {
  const [local, setLocal] = useState<AuthState>(state);

  useEffect(() => {
    listeners.add(setLocal);
    return () => { listeners.delete(setLocal); };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    emit({ busy: true, error: null });
    try {
      await api.login(username, password);
      // login() returns the token pair; the profile is a separate call, and the
      // router needs the role to decide which portal to open.
      const profile = await api.me();
      emit({ status: 'authenticated', user: profile, busy: false, error: null });
      return profile;
    } catch (err) {
      const message =
        err instanceof Error && (err as { status?: number }).status === 0
          ? [
            `Cannot reach the backend at ${API_BASE}`,
            `(${API_BASE_SOURCE}).`,
            '',
            `Start it with --host 0.0.0.0 so it accepts connections from this`,
            `phone, and allow port ${API_PORT} through the firewall on that machine.`,
          ].join(' ')
          : err instanceof Error ? err.message : 'Sign in failed';
      emit({ busy: false, error: message });
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    api.setTokens(null);
    await persist(null);
    emit({ status: 'anonymous', user: null, error: null });
  }, []);

  return useMemo(
    () => ({ ...local, login, logout }),
    [local, login, logout],
  );
}

/** Called once at startup, before the router decides where to send the user. */
export async function bootstrapAuth(): Promise<void> {
  const tokens = await restoreSession();
  if (!tokens) {
    emit({ status: 'anonymous', user: null });
    return;
  }
  try {
    const me = await api.me();
    emit({ status: 'authenticated', user: me });
  } catch {
    // A stored token that no longer works is the same as no token; the refresh
    // path inside the client has already had its chance by this point.
    await persist(null);
    api.setTokens(null);
    emit({ status: 'anonymous', user: null });
  }
}

setUnauthorizedHandler(() => {
  void persist(null);
  emit({ status: 'anonymous', user: null });
});

/**
 * Landing screen for a role.
 *
 * A concrete screen, never a bare route group. A group in parentheses is not a
 * path of its own: `/(consumer)` matches nothing at all, and `/(officer)` used
 * to collide with the root redirect for `/`. Either one lands the user on
 * expo-router's "Unmatched route" screen, which looks like the app is broken.
 */
export function homeFor(role?: string | null): string {
  switch (role) {
    case 'officer':
    case 'senior_officer':
    case 'admin':
      return '/(officer)/today';
    default:
      return '/(consumer)/scan';
  }
}

export function isOfficer(role?: string | null): boolean {
  return role === 'officer' || role === 'senior_officer' || role === 'admin';
}
