"""FastAPI app — REST endpoints + WebSocket event stream.

Endpoints:
  GET  /health           — liveness probe
  GET  /snapshots        — list recent decision snapshots
  GET  /snapshots/{id}   — fetch one snapshot
  GET  /memory/episodes  — recent reflection episodes
  POST /decisions/replay — run replay_decision against a snapshot with override
  POST /run              — trigger one decision graph run for a ticker (async)
  WS   /ws/events        — broadcast new decisions + position updates

Designed for the W5 Streamlit dashboard to consume.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from newsalpha.backtest.replay import replay_decision
from newsalpha.backtest.snapshots import DEFAULT_SNAPSHOT_DIR, list_snapshots, read_snapshot
from newsalpha.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


def _build_app() -> Any:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(title="NewsAlpha API", version="0.5.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class ReplayRequest(BaseModel):
        snapshot_id: str
        override_risk_config: dict[str, Any] | None = None

    class RunRequest(BaseModel):
        ticker: str

    class EventBus:
        def __init__(self) -> None:
            self._clients: set[WebSocket] = set()
            self._lock = asyncio.Lock()

        async def connect(self, ws: WebSocket) -> None:
            await ws.accept()
            async with self._lock:
                self._clients.add(ws)

        async def disconnect(self, ws: WebSocket) -> None:
            async with self._lock:
                self._clients.discard(ws)

        async def broadcast(self, event: dict[str, Any]) -> None:
            payload = json.dumps(event, default=str)
            dead: list[WebSocket] = []
            async with self._lock:
                for c in self._clients:
                    try:
                        await c.send_text(payload)
                    except Exception:  # noqa: BLE001
                        dead.append(c)
                for d in dead:
                    self._clients.discard(d)

    bus = EventBus()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.5.0",
            "ts": datetime.now(tz=UTC).isoformat(),
        }

    @app.get("/snapshots")
    def list_recent_snapshots(limit: int = 20) -> list[dict[str, Any]]:
        paths = list_snapshots()[-limit:]
        out = []
        for p in paths:
            try:
                snap = read_snapshot(p)
                state = snap.get("state", {})
                out.append({
                    "snapshot_id": p.stem,
                    "trace_id": snap.get("trace_id"),
                    "ticker": snap.get("ticker"),
                    "as_of": snap.get("as_of"),
                    "accepted": state.get("risk_decision", {}).get("accepted", False),
                    "conviction": (state.get("judge_verdict") or {}).get("conviction"),
                    "bias": (state.get("judge_verdict") or {}).get("directional_bias"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return out

    @app.get("/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str) -> dict[str, Any]:
        for p in list_snapshots():
            if p.stem == snapshot_id:
                return read_snapshot(p)
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_id}")

    @app.get("/memory/episodes")
    def list_episodes(limit: int = 20) -> list[dict[str, Any]]:
        from newsalpha.memory.episodes import InMemoryEpisodeStore, get_default_store

        store = get_default_store()
        if isinstance(store, InMemoryEpisodeStore):
            items = store._items[-limit:]
            return [p for _, _, p in items]
        return []

    @app.post("/decisions/replay")
    def replay(req: ReplayRequest) -> dict[str, Any]:
        for p in list_snapshots():
            if p.stem == req.snapshot_id:
                return replay_decision(p, override_risk_config=req.override_risk_config)
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {req.snapshot_id}")

    @app.post("/run")
    async def run_graph(req: RunRequest) -> dict[str, Any]:
        from newsalpha.demo import run as run_demo

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_demo, req.ticker)

        await bus.broadcast({
            "type": "decision_complete",
            "ticker": req.ticker,
            "trace_id": result.get("trace_id"),
            "ts": datetime.now(tz=UTC).isoformat(),
        })

        return {"trace_id": result.get("trace_id"), "ticker": req.ticker, "ok": True}

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        await bus.connect(ws)
        try:
            await ws.send_text(json.dumps({"type": "hello", "version": "0.5.0"}))
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            await bus.disconnect(ws)

    return app


def create_app() -> Any:
    """ASGI app factory — used by uvicorn entrypoint."""
    configure_logging()
    return _build_app()


def main() -> int:
    import uvicorn

    uvicorn.run(
        "newsalpha.api.app:create_app",
        host="127.0.0.1",
        port=8000,
        factory=True,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
