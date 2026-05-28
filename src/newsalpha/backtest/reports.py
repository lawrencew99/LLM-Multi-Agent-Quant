"""Quantstats HTML report generation.

Wraps quantstats to produce a tear-sheet-style HTML report from a backtest
result. Falls back to a markdown summary if quantstats is unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from newsalpha.backtest.metrics import compute_all_metrics
from newsalpha.utils.logging import get_logger

log = get_logger(__name__)


def generate_html_report(
    returns: pd.Series,
    trade_log: list[dict[str, Any]],
    *,
    output_path: str | Path,
    benchmark_returns: pd.Series | None = None,
    title: str = "NewsAlpha Backtest Report",
) -> Path:
    """Generate a quantstats HTML tear sheet.

    If quantstats fails (it has matplotlib dependencies that can be flaky),
    fall back to a markdown summary at the same path with `.md` extension.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        import quantstats as qs

        qs.extend_pandas()

        if benchmark_returns is not None and not benchmark_returns.empty:
            qs.reports.html(
                returns,
                benchmark=benchmark_returns,
                output=str(output),
                title=title,
            )
        else:
            qs.reports.html(
                returns,
                output=str(output),
                title=title,
            )
        log.info("html_report_generated", path=str(output))
        return output
    except Exception as exc:  # noqa: BLE001
        log.warning("quantstats_failed_fallback_md", error=str(exc))
        md_path = output.with_suffix(".md")
        write_markdown_report(returns, trade_log, output_path=md_path,
                              benchmark_returns=benchmark_returns, title=title)
        return md_path


def write_markdown_report(
    returns: pd.Series,
    trade_log: list[dict[str, Any]],
    *,
    output_path: str | Path,
    benchmark_returns: pd.Series | None = None,
    title: str = "NewsAlpha Backtest Report",
) -> Path:
    """Pure-Python markdown report (no plotting deps)."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    metrics = compute_all_metrics(returns, trade_log, benchmark_returns)

    lines = [
        f"# {title}",
        "",
        f"**Period**: {returns.index.min() if not returns.empty else 'N/A'} → "
        f"{returns.index.max() if not returns.empty else 'N/A'}",
        f"**Trading days**: {len(returns)}",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total return | {metrics.get('total_return_pct', 0):.2f}% |",
        f"| CAGR | {metrics.get('cagr', 0) * 100:.2f}% |",
        f"| Sharpe ratio | {metrics.get('sharpe_ratio', 0):.2f} |",
        f"| Sortino ratio | {metrics.get('sortino_ratio', 0):.2f} |",
        f"| Max drawdown | {metrics.get('max_drawdown', 0) * 100:.2f}% |",
        f"| Win rate | {metrics.get('win_rate', 0) * 100:.2f}% |",
        f"| Profit factor | {metrics.get('profit_factor', 0):.2f} |",
        f"| Total trades | {metrics.get('total_trades', 0)} |",
    ]

    if "alpha_vs_benchmark" in metrics:
        lines.extend([
            f"| Alpha vs benchmark | {metrics['alpha_vs_benchmark'] * 100:.2f}% |",
            f"| Benchmark return | {metrics['benchmark_return_pct']:.2f}% |",
        ])

    lines.extend(["", "## Trade Log", ""])

    if trade_log:
        lines.append("| Ticker | Side | Entry | Exit | PnL % | Reason | Conviction |")
        lines.append("|---|---|---|---|---|---|---|")
        for t in trade_log[:50]:
            lines.append(
                f"| {t.get('ticker', '')} "
                f"| {t.get('side', '')} "
                f"| {t.get('entry_date', '')[:10]} "
                f"| {t.get('exit_date', '')[:10]} "
                f"| {t.get('pnl_pct', 0) * 100:.2f}% "
                f"| {t.get('exit_reason', '')} "
                f"| {t.get('conviction', 0):.2f} |"
            )
        if len(trade_log) > 50:
            lines.append(f"\n*... and {len(trade_log) - 50} more trades*")
    else:
        lines.append("*No trades executed.*")

    output.write_text("\n".join(lines), encoding="utf-8")
    log.info("markdown_report_generated", path=str(output))
    return output
