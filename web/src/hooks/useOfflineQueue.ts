/** React binding for the IndexedDB capture queue. */
import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@shared/client';

import {
  listCaptures, pendingCount, purgeUploaded, syncQueue,
  type QueuedCapture, type SyncResult,
} from '@/lib/offlineQueue';
import { api } from '@/store/auth';

export function useOfflineQueue() {
  const [pending, setPending] = useState(0);
  const [captures, setCaptures] = useState<QueuedCapture[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [lastResult, setLastResult] = useState<SyncResult | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPending(await pendingCount());
      setCaptures(await listCaptures());
    } catch {
      /* IndexedDB unavailable (private browsing) -- degrade to online-only */
    }
  }, []);

  const sync = useCallback(async () => {
    if (syncing || !navigator.onLine) return null;
    setSyncing(true);
    try {
      const result = await syncQueue({
        createSession: (payload) => api.createSession(payload),
        uploadSurface: (sessionId, blob, surfaceType, filename) =>
          api.uploadSurface(sessionId, blob, surfaceType, filename),
        processSession: (sessionId) => api.processSession(sessionId),
        isOfflineError: (err) => err instanceof ApiError && err.isOffline,
      });
      setLastResult(result);
      await refresh();
      return result;
    } finally {
      setSyncing(false);
    }
  }, [refresh, syncing]);

  useEffect(() => {
    void refresh();
    // Drain automatically the moment connectivity returns -- an officer should
    // never have to remember to press a sync button.
    const onOnline = () => { void sync(); };
    window.addEventListener('online', onOnline);
    const timer = window.setInterval(() => { void refresh(); }, 15_000);
    return () => {
      window.removeEventListener('online', onOnline);
      window.clearInterval(timer);
    };
  }, [refresh, sync]);

  const purge = useCallback(async () => {
    await purgeUploaded();
    await refresh();
  }, [refresh]);

  return { pending, captures, syncing, lastResult, sync, refresh, purge };
}
