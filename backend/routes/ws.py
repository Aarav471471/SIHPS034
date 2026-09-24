"""WebSocket endpoints -- spec routes/ws.py.

Live pipeline progress for the officer console, plus broadcast topics the
dashboards subscribe to.

Authentication is by query-string token rather than an Authorization header,
because the browser WebSocket API cannot set custom headers. The token is the
same short-lived JWT used elsewhere.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from core.security import decode_token
from core.websocket_manager import manager

logger = logging.getLogger("metrix.ws")
router = APIRouter(prefix="/ws", tags=["WebSocket"])

BROADCAST_TOPICS = {
    "radar_alerts",       # price-gouging detections
    "peer_review_queue",  # senior officer queue changes
    "citizen_reports",    # incoming citizen leads
    "system",
}


def _authorised(token: str | None) -> dict | None:
    return decode_token(token, expected_type="access") if token else None


@router.websocket("/sessions/{session_id}")
async def session_progress(
    websocket: WebSocket,
    session_id: str,
    token: str | None = Query(default=None),
) -> None:
    """Stream six-stage pipeline progress for one inspection."""
    if _authorised(token) is None:
        # 1008 = policy violation. Closing before accept avoids a half-open
        # socket that looks connected to the client but receives nothing.
        await websocket.close(code=1008, reason="Valid access token required")
        return

    await manager.connect_session(websocket, session_id)
    try:
        while True:
            # The client sends nothing meaningful; this receive keeps the
            # connection open and surfaces the disconnect promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Session socket %s closed: %s", session_id, exc)
    finally:
        await manager.disconnect_session(websocket, session_id)


@router.websocket("/topics/{topic}")
async def topic_stream(
    websocket: WebSocket,
    topic: str,
    token: str | None = Query(default=None),
) -> None:
    """Subscribe a dashboard to a broadcast topic."""
    if _authorised(token) is None:
        await websocket.close(code=1008, reason="Valid access token required")
        return
    if topic not in BROADCAST_TOPICS:
        await websocket.close(code=1003, reason=f"Unknown topic '{topic}'")
        return

    await manager.connect_topic(websocket, topic)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Topic socket %s closed: %s", topic, exc)
    finally:
        await manager.disconnect_topic(websocket, topic)


@router.get("/stats", tags=["System"])
async def websocket_stats() -> dict:
    return {"topics": sorted(BROADCAST_TOPICS), **manager.stats()}
