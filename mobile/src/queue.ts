/**
 * Offline capture queue.
 *
 * An officer inspects in shops, basements and markets where the signal is
 * unreliable, and losing an inspection because the upload failed is the worst
 * outcome the app can produce -- the pack has already been put back on the
 * shelf by then. So capture never touches the network: photographs are written
 * to the device by the camera, their paths and the session metadata go into
 * AsyncStorage, and upload is a separate step that can fail and be retried.
 *
 * Resumability is at SURFACE granularity, not session granularity. A five-photo
 * inspection that dies after the third upload must not re-send the first three
 * on retry, both because the connection that failed is by definition a bad one
 * and because the server would reject the duplicates.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { api } from '@/api';
import { fileForUpload } from '@/upload';
import type { SessionCreate } from '@shared/types';

const KEY = 'metrix.queue.v1';

export type QueueStatus = 'pending' | 'uploading' | 'uploaded' | 'failed';

export interface QueuedSurface {
  /** Local file URI produced by the camera. */
  uri: string;
  surface: string;
  /** Set once this surface has been accepted by the server. */
  uploaded?: boolean;
}

export interface QueuedCapture {
  id: string;
  createdAt: number;
  session: SessionCreate;
  surfaces: QueuedSurface[];
  status: QueueStatus;
  /** Server session id, once created. Kept so a retry resumes rather than restarts. */
  sessionId?: string;
  lastError?: string;
  attempts: number;
}

type Listener = (items: QueuedCapture[]) => void;
const listeners = new Set<Listener>();
let cache: QueuedCapture[] | null = null;

async function readAll(): Promise<QueuedCapture[]> {
  if (cache) return cache;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    cache = raw ? (JSON.parse(raw) as QueuedCapture[]) : [];
  } catch {
    cache = [];
  }
  return cache;
}

async function writeAll(items: QueuedCapture[]): Promise<void> {
  cache = items;
  listeners.forEach((l) => l(items));
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    // Storage full or unavailable. The in-memory copy still serves this
    // session, which is better than throwing away a capture the officer just
    // made; it will be lost on restart and that is the honest outcome.
  }
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  void readAll().then(fn);
  return () => { listeners.delete(fn); };
}

export async function list(): Promise<QueuedCapture[]> {
  return readAll();
}

export async function enqueue(
  session: SessionCreate,
  surfaces: QueuedSurface[],
): Promise<QueuedCapture> {
  const items = await readAll();
  const item: QueuedCapture = {
    id: `cap_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    createdAt: Date.now(),
    session,
    surfaces,
    status: 'pending',
    attempts: 0,
  };
  await writeAll([item, ...items]);
  return item;
}

export async function remove(id: string): Promise<void> {
  const items = await readAll();
  await writeAll(items.filter((i) => i.id !== id));
}

async function update(id: string, patch: Partial<QueuedCapture>): Promise<void> {
  const items = await readAll();
  await writeAll(items.map((i) => (i.id === id ? { ...i, ...patch } : i)));
}

/**
 * Push one queued capture to the server.
 *
 * Returns the server session id on success. Throws on failure, leaving the
 * item in the queue with whatever progress it made recorded, so the next
 * attempt resumes.
 */
export async function uploadOne(item: QueuedCapture): Promise<string> {
  await update(item.id, { status: 'uploading', lastError: undefined });

  try {
    // Create the session once. A retry after a partial upload must reuse the
    // id, or the officer ends up with two half-populated inspections of the
    // same pack and no way to tell which is authoritative.
    let sessionId = item.sessionId;
    if (!sessionId) {
      const created = await api.createSession(item.session);
      sessionId = created.session_id;
      await update(item.id, { sessionId });
    }

    const surfaces = [...item.surfaces];
    for (let i = 0; i < surfaces.length; i += 1) {
      const s = surfaces[i];
      if (s.uploaded) continue;

      // A real Blob, not a { uri } descriptor: Expo's fetch builds the
      // multipart body in JS and rejects the descriptor outright. See
      // src/upload.ts for why.
      const filename = `${s.surface.toLowerCase()}.jpg`;
      const file = fileForUpload(s.uri);

      await api.uploadSurface(sessionId, file, s.surface, filename);

      surfaces[i] = { ...s, uploaded: true };
      await update(item.id, { surfaces: [...surfaces] });
    }

    await api.processSession(sessionId);
    await update(item.id, { status: 'uploaded', surfaces });
    return sessionId;
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Upload failed';
    const offline = (err as { status?: number })?.status === 0;
    await update(item.id, {
      // An offline failure is not a rejection: it stays pending so the next
      // sync retries it. A 4xx means the server refused this capture and
      // retrying will refuse it again, so it stops and shows the reason.
      status: offline ? 'pending' : 'failed',
      lastError: message,
      attempts: item.attempts + 1,
    });
    throw err;
  }
}

/** Drain everything that is still waiting. Stops at the first offline error. */
export async function sync(): Promise<{ uploaded: number; failed: number }> {
  const items = await readAll();
  let uploaded = 0;
  let failed = 0;

  for (const item of items) {
    if (item.status === 'uploaded') continue;
    try {
      await uploadOne(item);
      uploaded += 1;
    } catch (err) {
      failed += 1;
      // No point hammering a dead connection with the rest of the queue.
      if ((err as { status?: number })?.status === 0) break;
    }
  }
  return { uploaded, failed };
}

export function pendingCount(items: QueuedCapture[]): number {
  return items.filter((i) => i.status !== 'uploaded').length;
}
