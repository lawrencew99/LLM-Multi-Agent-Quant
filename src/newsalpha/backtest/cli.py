"""Backtest CLI — run full pipeline from snapshots → backtrader → report.

Usage:
    uv run python -m newsalpha.backtest.cli --tickers AAPL,MSFT,NVDA --start 2023-01-01 --end 2023-12-31

If no snapshots exist, synthesizes mock signals so the pipeline is testable
end-to-end without prior production data.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from newsalpha.backtest.engine import run_multi_ticker_backtest
from newsalpha.backtest.metrics import compute_all_metrics
from newsalpha.backtest.replay import extract_signals_for_backtest
from newsalpha.backtest.reports import generate_html_report, write_markdown_report
from newsalpha.backtest.snapshots import DEFAULT_SNAPSHOT_DIR
from newsalpha.core.config import REPO_ROOT
from newsalpha.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


def synthesize_signals(
    tickers: list[str],
    *,
    start_date: str,
    end_date: str,
    n_per_ticker: int = 6,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Generate plausible mock signals for backtest dry-runs.

    Uses a deterministic RNG so backtests are reproducible. Signals reflect a
    biased-long strategy with realistic stop/take levels.
    """
    rng = random.Random(seed)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    business_days = pd.bdate_range(start, end)

    signals: list[dict[str, Any]] = []
    for ticker in tickers:
        for _ in range(n_per_ticker):
            day = business_days[rng.randint(0, len(business_days) - 1)]
            side = "long" if rng.random() > 0.25 else "short"
            entry_price = 100.0 + rng.uniform(-20, 50)
            atr = entry_price * 0.02
            if side == "long":
                stop = entry_price - 2 * atr
                tp = entry_price + 4 * atr
            else:
                stop = entry_price + 2 * atr
                tp = entry_price - 4 * atr

            signals.append({
                "ticker": ticker,
                "as_of": day.isoformat(),
                "side": side,
                "size_pct": rng.uniform(0.02, 0.05),
                "entry_price": entry_price,
                "stop_loss": stop,
                "take_profit": tp,
                "conviction": rng.uniform(0.6, 0.95),
                "trace_id": f"synth-{ticker}-{day.strftime('%Y%m%d')}",
            })

    signals.sort(key=lambda s: s["as_of"])
    return signals


def main() -> int:
    configure_logging()

    parser = argparse.ArgumentParser(description="NewsAlpha backtest runner")
    parser.add_argument("--tickers", default="AAPL,MSFT,NVDA,GOOGL,TSLA",
                        help="Comma-separated tickers")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--cash", type=float, default=100_000.0)
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR))
    parser.add_argument("--report-dir", default=str(REPO_ROOT / "data" / "reports"))
    parser.add_argument("--synth", action="store_true",
                        help="Skip reading snapshots; synthesize mock signals")
    parser.add_argument("--n-synth-per-ticker", type=int, default=8)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    if args.synth:
        log.info("using_synthesized_signals")
        signals = synthesize_signals(
            tickers,
            start_date=args.start,
            end_date=args.end,
            n_per_ticker=args.n_synth_per_ticker,
        )
    else:
        signals = extract_signals_for_backtest(args.snapshot_dir)
        if not signals:
            log.warning("no_snapshots_found_using_synth", path=args.snapshot_dir)
            signals = synthesize_signals(
                tickers,
                start_date=args.start,
                end_date=args.end,
                n_per_ticker=args.n_synth_per_ticker,
            )

    log.info("backtest_starting", n_tickers=len(tickers), n_signals=len(signals),
             start=args.start, end=args.end)

    results = run_multi_ticker_backtest(
        tickers,
        signals,
        start_date=args.start,
        end_date=args.end,
        initial_cash=args.cash,
    )

    combined_returns = results["combined_returns"]
    trade_log = results["all_trade_logs"]

    metrics = compute_all_metrics(combined_returns, trade_log)
    log.info("backtest_metrics", **{k: round(v, 4) if isinstance(v, float) else v
                                     for k, v in metrics.items()})

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")

    md_path = write_markdown_report(
        combined_returns,
        trade_log,
        output_path=report_dir / f"backtest_{ts}.md",
        title=f"NewsAlpha Backtest {args.start} → {args.end}",
    )

    metrics_path = report_dir / f"metrics_{ts}.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    log.info("report_written", markdown=str(md_path), metrics=str(metrics_path))

    print("\n" + "=" * 70)
    print(f"BACKTEST COMPLETE — {len(tickers)} tickers, {args.start} → {args.end}")
    print("=" * 70)
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k:<24} {v:>12.4f}")
        else:
            print(f"  {k:<24} {v:>12}")
    print("=" * 70)
    print(f"  Report: {md_path}")
    print(f"  Metrics JSON: {metrics_path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
