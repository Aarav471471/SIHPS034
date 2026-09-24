/**
 * Authentication and the shared API client instance.
 *
 * Tokens persist to localStorage so an officer who closes the app mid-shift
 * comes back signed in. The refresh token is long-lived by design (30 days),
 * because a field officer can be offline for days and being logged out on
 * reconnect would strand queued captures they can no longer upload.
 */
import { create } from 'zustand';
import { MetrixClient, type Tokens } from '@shared/client';
import type { UserProfile } from '@shared/types';

const STORAGE_KEY = 'metrix.auth';

function loadTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

function saveTokens(tokens: Tokens | null): void {
  try {
    if (tokens) localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private browsing, storage disabled -- the session simply won't persist */
  }
}

// In dev the Vite proxy forwards /api to the backend, so a relative base works
// and there is no CORS to configure. A build for a device on the LAN sets
// VITE_API_BASE_URL to the machine's address.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export const api = new MetrixClient({
  baseUrl: BASE_URL,
  onTokens: saveTokens,
  onUnauthorized: () => {
    useAuth.getState().clear();
  },
});

const stored = loadTokens();
if (stored) api.setTokens(stored);

interface AuthState {
  user: UserProfile | null;
  status: 'unknown' | 'authenticated' | 'anonymous';
  error: string | null;
  busy: boolean;

  restore: () => Promise<void>;
  login: (username: string, password: string) => Promise<UserProfile>;
  register: (payload: {
    username: string; email: string; password: string;
    full_name?: string; role?: 'consumer' | 'brand'; brand_name?: string;
  }) => Promise<UserProfile>;
  logout: () => void;
  clear: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  status: 'unknown',
  error: null,
  busy: false,

  /** Validate a persisted token on boot rather than trusting it blindly. */
  restore: async () => {
    if (!api.isAuthenticated) {
      set({ status: 'anonymous', user: null });
      return;
    }
    try {
      const user = await api.me();
      set({ user, status: 'authenticated', error: null });
    } catch {
      api.logout();
      set({ user: null, status: 'anonymous' });
    }
  },

  login: async (username, password) => {
    set({ busy: true, error: null });
    try {
      const res = await api.login(username, password);
      set({ user: res.user, status: 'authenticated', busy: false });
      return res.user;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Sign-in failed';
      set({ error: message, busy: false, status: 'anonymous' });
      throw err;
    }
  },

  register: async (payload) => {
    set({ busy: true, error: null });
    try {
      const res = await api.register(payload);
      set({ user: res.user, status: 'authenticated', busy: false });
      return res.user;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Registration failed';
      set({ error: message, busy: false });
      throw err;
    }
  },

  logout: () => {
    api.logout();
    set({ user: null, status: 'anonymous', error: null });
  },

  clear: () => set({ user: null, status: 'anonymous' }),
}));

/** Where each role lands after signing in. */
export function homeFor(role: string | undefined): string {
  switch (role) {
    case 'officer':
    case 'senior_officer':
      return '/officer';
    case 'brand':
      return '/brand';
    case 'admin':
      return '/policy';
    case 'consumer':
    default:
      return '/scan';
  }
}
