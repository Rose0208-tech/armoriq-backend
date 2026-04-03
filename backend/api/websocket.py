"""WebSocket endpoint for live enforcement event streaming."""
from __future__ import annotations
import asyncio, json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()

# Simple in-process pub/sub registry
_subscribers: dict[str, list[WebSocket]] = {}


async def broadcast_event(session_id: str, event: dict):
    """Called by audit_logger after every decision to push to UI."""
    sockets = _subscribers.get(session_id, []) + _subscribers.get("*", [])
    dead = []
    for ws in sockets:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        for key in _subscribers:
            if ws in _subscribers[key]:
                _subscribers[key].remove(ws)


@ws_router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket, session: str = "*"):
    await websocket.accept()
    _subscribers.setdefault(session, []).append(websocket)
    try:
        while True:
            # Keep connection alive; client just listens
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        if session in _subscribers:
            _subscribers[session] = [
                ws for ws in _subscribers[session] if ws != websocket
            ]