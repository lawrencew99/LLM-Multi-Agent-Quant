"""Decision snapshot persistence + roundtrip tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from newsalpha.backtest import snapshots


def test_write_and_read_snapshot_roundtrip(tmp_path: Path) -> None:
    state: dict[str, Any] = {
        "trace_id": "abc123",
        "ticker": "AAPL",
        "as_of": "2026-05-26T00:00:00Z",
        "judge_verdict": {"directional_bias": "long", "conviction": 0.7},
        "final_orders": [{"ticker": "AAPL", "side": "long", "size_pct": 0.03}],
        "cost_usd": 0.012,
    }

    path = snapshots.write_snapshot(state, snapshot_dir=tmp_path)
    assert path.exists()

    loaded = snapshots.read_snapshot(path)
    assert loaded["schema_version"] == 1
    assert loaded["trace_id"] == "abc123"
    assert loaded["ticker"] == "AAPL"
    assert loaded["state"]["final_orders"][0]["size_pct"] == 0.03


def test_list_snapshots_returns_sorted(tmp_path: Path) -> None:
    snapshots.write_snapshot({"trace_id": "t1", "ticker": "A"}, snapshot_dir=tmp_path)
    snapshots.write_snapshot({"trace_id": "t2", "ticker": "B"}, snapshot_dir=tmp_path)
    snapshots.write_snapshot({"trace_id": "t3", "ticker": "C"}, snapshot_dir=tmp_path)

    found = snapshots.list_snapshots(snapshot_dir=tmp_path)
    assert len(found) == 3
    assert found == sorted(found)


def test_list_snapshots_empty_dir(tmp_path: Path) -> None:
    assert snapshots.list_snapshots(snapshot_dir=tmp_path / "missing") == []


def test_write_snapshot_generates_trace_id_when_absent(tmp_path: Path) -> None:
    state = {"ticker": "AAPL"}  # no trace_id
    path = snapshots.write_snapshot(state, snapshot_dir=tmp_path)
    loaded = snapshots.read_snapshot(path)
    assert loaded["trace_id"].startswith("local_")
