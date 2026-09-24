/**
 * Theme.
 *
 * Three states, not two: 'system' is the default and follows the OS, because a
 * user who has set their device to dark at night expects apps to follow without
 * being asked. An explicit choice overrides it and persists.
 */
import { create } from 'zustand';

export type ThemeChoice = 'light' | 'dark' | 'system';

const KEY = 'metrix.theme';

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

function resolve(choice: ThemeChoice): 'light' | 'dark' {
  return choice === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : choice;
}

function paint(resolved: 'light' | 'dark'): void {
  document.documentElement.classList.toggle('dark', resolved === 'dark');
  // Keep the browser chrome (address bar, status bar) in step with the app.
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', resolved === 'dark' ? '#0b1220' : '#0f3d6e');
}

function load(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
  } catch {
    return 'system';
  }
}

interface ThemeState {
  choice: ThemeChoice;
  resolved: 'light' | 'dark';
  set: (c: ThemeChoice) => void;
  cycle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  choice: 'system',
  resolved: 'light',

  set: (choice) => {
    try {
      localStorage.setItem(KEY, choice);
    } catch {
      /* storage disabled -- the choice simply will not persist */
    }
    const resolved = resolve(choice);
    paint(resolved);
    set({ choice, resolved });
  },

  cycle: () => {
    const order: ThemeChoice[] = ['light', 'dark', 'system'];
    const next = order[(order.indexOf(get().choice) + 1) % order.length];
    get().set(next);
  },
}));

/** Applied once at boot, before React paints, to avoid a flash of the wrong theme. */
export function initTheme(): void {
  const choice = load();
  const resolved = resolve(choice);
  paint(resolved);
  useTheme.setState({ choice, resolved });

  // Track the OS while the user is on 'system'.
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (useTheme.getState().choice !== 'system') return;
    const next = resolve('system');
    paint(next);
    useTheme.setState({ resolved: next });
  });
}
