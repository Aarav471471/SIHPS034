/** Live six-stage pipeline progress over WebSocket. */
import { useEffect, useRef, useState } from 'react';
import type { PipelineEvent, PipelineStage } from '@shared/types';

import { api } from '@/store/auth';

export const STAGES: PipelineStage[] = [
  'CAPTURE', 'PREPROCESS', 'EXTRACT', 'VERIFY', 'VALIDATE', 'REVIEW',
];

export const STAGE_LABELS: Record<PipelineStage, string> = {
  CAPTURE: 'Capture',
  PREPROCESS: 'Preprocess',
  EXTRACT: 'AI extract',
  VERIFY: 'Verify',
  VALIDATE: 'Validate',
  REVIEW: 'Review',
};

export function usePipelineSocket(sessionId: string | undefined, active: boolean) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!sessionId || !active) return;

    let closed = false;
    let retry = 0;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(api.websocketUrl(`/api/ws/sessions/${sessionId}`));
      socketRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        retry = 0;
      };

      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data) as PipelineEvent;
          if (data.type === 'pipeline') setEvents((prev) => [...prev, data]);
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (closed) return;
        // Reconnect with backoff. A dropped socket must not silently stop the
        // progress display while the pipeline is still running server-side.
        retry += 1;
        if (retry <= 5) {
          timer = window.setTimeout(connect, Math.min(8000, 500 * 2 ** retry));
        }
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [sessionId, active]);

  const latest = events.at(-1);
  const progress = latest?.progress ?? 0;

  const stageStatus = STAGES.reduce<Record<string, 'done' | 'active' | 'pending' | 'failed'>>(
    (acc, stage) => {
      const forStage = events.filter((e) => e.stage === stage);
      const last = forStage.at(-1);
      acc[stage] = !last
        ? 'pending'
        : last.status === 'completed'
          ? 'done'
          : last.status === 'failed'
            ? 'failed'
            : 'active';
      return acc;
    },
    {},
  );

  return { events, latest, progress, connected, stageStatus };
}
