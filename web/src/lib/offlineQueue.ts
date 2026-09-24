/**
 * Offline-first capture queue -- spec "Offline-First PWA".
 *
 * An officer in a shop basement has no signal. The inspection must still
 * happen: photograph the pack, record the GPS fix and the time, and let the
 * upload happen later. Anything less means the officer either waits at the
 * door for a bar of signal or writes it on paper.
 *
 * Captures live in IndexedDB (not localStorage -- image blobs are megabytes)
 * and drain automatically when connectivity returns. The queue is deliberately
 * conservative about what it retries: a lost connection is retried forever, a
 * server rejection is not, because replaying a 4xx a thousand times just burns
 * the officer's battery.
 */
import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { SessionCreate } from '@shared/types';

export type QueueStatus = 'pending' | 'uploading' | 'uploaded' | 'failed';

export interface QueuedSurface {
  surfaceType: string;
  blob: Blob;
  filename: string;
}

export interface QueuedCapture {
  id: string;
  createdAt: number;
  status: QueueStatus;
  attempts: number;
  lastError?: string;
  /** Set once the session exists server-side, so a resumed upload is not duplicated. */
  sessionId?: string;
  session: SessionCreate;
  surfaces: QueuedSurface[];
  uploadedSurfaces: string[];
}

interface MetrixDB extends DBSchema {
  captures: {
    key: string;
    value: QueuedCapture;
    indexes: { 'by-status': QueueStatus; 'by-created': number };
  };
  /** Last-known scan results, so the consumer app works without signal. */
  scanCache: {
    key: string;
    value: { barcode: string; payload: unknown; cachedAt: number };
  };
}

const DB_NAME = 'metrix';
const DB_VERSION = 1;
// Beyond this many failed attempts a capture stops retrying on its own and
// waits for the officer to decide. Silent infinite retry hides real problems.
const MAX_ATTEMPTS = 8;

let dbPromise: Promise<IDBPDatabase<MetrixDB>> | null = null;

function getDB(): Promise<IDBPDatabase<MetrixDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MetrixDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        const captures = db.createObjectStore('captures', { keyPath: 'id' });
        captures.createIndex('by-status', 'status');
        captures.createIndex('by-created', 'createdAt');
        db.createObjectStore('scanCache', { keyPath: 'barcode' });
      },
    });
  }
  return dbPromise;
}

export function isSupported(): boolean {
  return typeof indexedDB !== 'undefined';
}

function newId(): string {
  return `cap_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

// ---------------------------------------------------------------- captures --
export async function enqueueCapture(
  session: SessionCreate,
  surfaces: QueuedSurface[],
): Promise<QueuedCapture> {
  const capture: QueuedCapture = {
    id: newId(),
    createdAt: Date.now(),
    status: 'pending',
    attempts: 0,
    // Stamp the capture time now. The upload may be hours later, and a finding
    // must be dated to when the officer was actually in the shop -- not to when
    // their phone next found signal.
    session: { ...session, captured_at: session.captured_at ?? new Date().toISOString() },
    surfaces,
    uploadedSurfaces: [],
  };
  const db = await getDB();
  await db.put('captures', capture);
  return capture;
}

export async function listCaptures(status?: QueueStatus): Promise<QueuedCapture[]> {
  const db = await getDB();
  const all = status
    ? await db.getAllFromIndex('captures', 'by-status', status)
    : await db.getAll('captures');
  return all.sort((a, b) => b.createdAt - a.createdAt);
}

export async function getCapture(id: string): Promise<QueuedCapture | undefined> {
  return (await getDB()).get('captures', id);
}

export async function updateCapture(
  id: string,
  patch: Partial<QueuedCapture>,
): Promise<void> {
  const db = await getDB();
  const existing = await db.get('captures', id);
  if (!existing) return;
  await db.put('captures', { ...existing, ...patch });
}

export async function removeCapture(id: string): Promise<void> {
  await (await getDB()).delete('captures', id);
}

export async function pendingCount(): Promise<number> {
  const db = await getDB();
  const pending = await db.getAllFromIndex('captures', 'by-status', 'pending');
  const failed = await db.getAllFromIndex('captures', 'by-status', 'failed');
  return pending.length + failed.length;
}

// ------------------------------------------------------------------ drain --
export interface SyncDeps {
  createSession: (payload: SessionCreate) => Promise<{ session_id: string }>;
  uploadSurface: (
    sessionId: string, blob: Blob, surfaceType: string, filename: string,
  ) => Promise<unknown>;
  processSession: (sessionId: string) => Promise<unknown>;
  isOfflineError: (err: unknown) => boolean;
}

export interface SyncResult {
  attempted: number;
  uploaded: number;
  failed: number;
  stillOffline: boolean;
  errors: Array<{ id: string; error: string }>;
}

/**
 * Push every queued capture to the server.
 *
 * Resumable at surface granularity: a capture interrupted after two of three
 * photographs uploaded continues from the third rather than starting over.
 * That matters on the connections this is designed for.
 */
export async function syncQueue(deps: SyncDeps): Promise<SyncResult> {
  const result: SyncResult = {
    attempted: 0, uploaded: 0, failed: 0, stillOffline: false, errors: [],
  };

  const queue = [
    ...(await listCaptures('pending')),
    ...(await listCaptures('failed')).filter((c) => c.attempts < MAX_ATTEMPTS),
  ].sort((a, b) => a.createdAt - b.createdAt);

  for (const capture of queue) {
    result.attempted += 1;
    await updateCapture(capture.id, { status: 'uploading' });

    try {
      let sessionId = capture.sessionId;
      if (!sessionId) {
        const created = await deps.createSession(capture.session);
        sessionId = created.session_id;
        await updateCapture(capture.id, { sessionId });
      }

      const done = new Set(capture.uploadedSurfaces);
      for (const surface of capture.surfaces) {
        const key = `${surface.surfaceType}:${surface.filename}`;
        if (done.has(key)) continue;
        await deps.uploadSurface(sessionId, surface.blob, surface.surfaceType, surface.filename);
        done.add(key);
        await updateCapture(capture.id, { uploadedSurfaces: [...done] });
      }

      await deps.processSession(sessionId);
      await updateCapture(capture.id, { status: 'uploaded', lastError: undefined });
      result.uploaded += 1;
    } catch (err) {
      const offline = deps.isOfflineError(err);
      const message = err instanceof Error ? err.message : String(err);

      await updateCapture(capture.id, {
        // A lost connection leaves the capture pending so it retries freely.
        // A server rejection marks it failed, because replaying a 4xx will
        // never succeed and pretending otherwise hides the real problem.
        status: offline ? 'pending' : 'failed',
        attempts: capture.attempts + 1,
        lastError: message,
      });

      if (offline) {
        result.stillOffline = true;
        break; // no point trying the rest of the queue with no connection
      }
      result.failed += 1;
      result.errors.push({ id: capture.id, error: message });
    }
  }

  return result;
}

/** Clear captures that uploaded successfully. */
export async function purgeUploaded(): Promise<number> {
  const uploaded = await listCaptures('uploaded');
  for (const c of uploaded) await removeCapture(c.id);
  return uploaded.length;
}

// ------------------------------------------------------------- scan cache --
export async function cacheScan(barcode: string, payload: unknown): Promise<void> {
  const db = await getDB();
  await db.put('scanCache', { barcode, payload, cachedAt: Date.now() });
}

export async function readCachedScan(
  barcode: string,
  maxAgeMs = 1000 * 60 * 60 * 24 * 7,
): Promise<unknown | null> {
  const db = await getDB();
  const hit = await db.get('scanCache', barcode);
  if (!hit) return null;
  // Stale price data is worse than none -- an out-of-date MRP could tell a
  // shopper they are being overcharged when the price legitimately changed.
  if (Date.now() - hit.cachedAt > maxAgeMs) return null;
  return hit.payload;
}

export async function estimateStorage(): Promise<{ usedMB: number; quotaMB: number } | null> {
  if (!navigator.storage?.estimate) return null;
  const { usage = 0, quota = 0 } = await navigator.storage.estimate();
  return { usedMB: usage / 1024 / 1024, quotaMB: quota / 1024 / 1024 };
}
