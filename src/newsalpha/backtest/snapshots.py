"""Decision snapshot persistence + replay primitives.

Design: every full graph run produces a self-contained JSON document with
*everything needed to re-derive downstream nodes deterministically*: each
agent's input payload, raw LLM text, parsed output, latency, cost. We store
to JSON-on-disk for W3 (zero-infra) and migrate to Postgres in W4.

The replay path (W4) reads a snapshot, replaces the LLMClient with a
record-replay shim keyed on `trace_id + agent_name`, and re-runs the graph —
allowing prompt-only A/B without re-spending tokens.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from newsalpha.core.config import REPO_ROOT
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "data" / "snapshots"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_snapshot(
    state: dict[str, Any],
    *,
    snapshot_dir: Path | None = None,
) -> Path:
    """Persist the final state of a graph run as a JSON snapshot.

    File name: `{trace_id}_{ticker}_{utc_iso}.json`. The trace_id is generated
    if absent so backtests-from-CSV still get a unique key.
    """
    out_dir = snapshot_dir or DEFAULT_SNAPSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_id = state.get("trace_id") or f"local_{_utcnow_iso().replace(':', '')}"
    ticker = state.get("ticker", "UNKNOWN")
    fname = f"{trace_id}_{ticker}_{_utcnow_iso().replace(':', '')}.json"
    path = out_dir / fname

    snapshot = {
        "schema_version": 1,
        "written_at": _utcnow_iso(),
        "trace_id": trace_id,
        "ticker": ticker,
        "as_of": state.get("as_of"),
        "state": state,
    }
    path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    log.info("snapshot_written", path=str(path), trace_id=trace_id, ticker=ticker)
    return path


def read_snapshot(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def list_snapshots(snapshot_dir: Path | None = None) -> list[Path]:
    out_dir = snapshot_dir or DEFAULT_SNAPSHOT_DIR
    if not out_dir.exists():
        return []
    return sorted(out_dir.glob("*.json"))
