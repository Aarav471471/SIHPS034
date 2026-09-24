"""Real-time WebSocket pool -- spec core/websocket_manager.py.

Carries live pipeline progress to whoever is watching a given inspection, so the
officer sees "unwarping surface 2 of 3" rather than a spinner.

Two subscription scopes:
  * per-session  -- the officer watching one inspection run
  * per-topic    -- dashboards subscribed to a broadcast stream (radar alerts,
                    peer-review queue changes)

Publishing is deliberately fire-and-forget: a dead socket must never be able to
stall or fail the inspection pipeline that is publishing to it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("metrix.ws")


@dataclass
class PipelineEvent:
    """One step in the six-stage pipeline, as seen by the client."""

    session_id: str
    stage: str          # CAPTURE | PREPROCESS | EXTRACT | VERIFY | VALIDATE | REVIEW
    status: str         # started | progress | completed | failed
    progress: int = 0   # 0-100
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_json(self) -> str:
        return json.dumps({"type": "pipeline", **asdict(self)}, default=str)


class ConnectionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, set[Any]] = defaultdict(set)
        self._topics: dict[str, set[Any]] = defaultdict(set)
        self._lock = asyncio.Lock()
        # Late subscribers would otherwise miss everything that already
        # happened; a short replay buffer lets them catch up on connect.
        self._replay: dict[str, list[str]] = defaultdict(list)
        self._replay_limit = 40

    # ------------------------------------------------------------ sessions --
    async def connect_session(self, websocket: Any, session_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._sessions[session_id].add(websocket)
            backlog = list(self._replay.get(session_id, []))
        for payload in backlog:
            try:
                await websocket.send_text(payload)
            except Exception:
                break
        logger.debug("WS attached to session %s (%d watchers)",
                     session_id, len(self._sessions[session_id]))

    async def disconnect_session(self, websocket: Any, session_id: str) -> None:
        async with self._lock:
            self._sessions[session_id].discard(websocket)
            if not self._sessions[session_id]:
                self._sessions.pop(session_id, None)

    # -------------------------------------------------------------- topics --
    async def connect_topic(self, websocket: Any, topic: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._topics[topic].add(websocket)

    async def disconnect_topic(self, websocket: Any, topic: str) -> None:
        async with self._lock:
            self._topics[topic].discard(websocket)
            if not self._topics[topic]:
                self._topics.pop(topic, None)

    # ------------------------------------------------------------ publish ---
    async def _fan_out(self, sockets: set[Any], payload: str) -> None:
        if not sockets:
            return
        dead = []
        for ws in list(sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)

    async def publish_event(self, event: PipelineEvent) -> None:
        payload = event.to_json()
        async with self._lock:
            buf = self._replay[event.session_id]
            buf.append(payload)
            if len(buf) > self._replay_limit:
                del buf[: len(buf) - self._replay_limit]
            targets = set(self._sessions.get(event.session_id, ()))
        await self._fan_out(targets, payload)

    async def publish_topic(self, topic: str, message: dict[str, Any]) -> None:
        payload = json.dumps(
            {
                "type": topic,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **message,
            },
            default=str,
        )
        async with self._lock:
            targets = set(self._topics.get(topic, ()))
        await self._fan_out(targets, payload)

    def clear_replay(self, session_id: str) -> None:
        self._replay.pop(session_id, None)

    # --------------------------------------------------------------- stats --
    def stats(self) -> dict[str, Any]:
        return {
            "session_channels": len(self._sessions),
            "session_watchers": sum(len(v) for v in self._sessions.values()),
            "topic_channels": len(self._topics),
            "topic_subscribers": sum(len(v) for v in self._topics.values()),
        }


manager = ConnectionManager()


def emit(
    session_id: str,
    stage: str,
    status: str,
    progress: int = 0,
    message: str = "",
    **detail: Any,
) -> None:
    """Publish from synchronous worker code.

    Pipeline tasks run in threads (or Celery processes) with no running event
    loop, so this schedules onto the API's loop when one is reachable and
    degrades to a log line when it is not -- a Celery worker on another host
    genuinely cannot reach these sockets, and that must not be an error.
    """
    event = PipelineEvent(
        session_id=session_id,
        stage=stage,
        status=status,
        progress=progress,
        message=message,
        detail=detail,
    )
    try:
        loop = _get_loop()
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.publish_event(event), loop)
            return
    except Exception as exc:  # pragma: no cover - best-effort transport
        logger.debug("WS emit skipped: %s", exc)
    logger.info("[%s] %s/%s %d%% %s", session_id, stage, status, progress, message)


_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at API startup so worker threads know where to publish."""
    global _loop
    _loop = loop


def _get_loop() -> asyncio.AbstractEventLoop | None:
    if _loop is not None:
        return _loop
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
