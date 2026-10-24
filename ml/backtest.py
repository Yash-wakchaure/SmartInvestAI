"""Backtest the model's held-out test-period signals with Indian trading costs.

Input is `test_predictions.csv`, written by pipeline.py from the model that never
saw the test period. A direction model is only useful if it makes money AFTER
costs, so this script charges brokerage, STT, exchange fees, stamp duty, GST and
slippage, and compares against equal-weight buy-and-hold of the same stocks.

    python ml/backtest.py --predictions ml/artifacts/test_predictions.csv

Honesty rules baked in:
  * the headline threshold is fixed in advance (from metrics.json / --threshold);
    the threshold sweep is informational - picking the best row on the test
    period would be overfitting to the test set;
  * the default strategy is long-only, because short selling delivery shares is
    not possible in the Indian cash market;
  * cost rates below are approximations. Check your broker's charge calculator
    and pass --brokerage-bps / --slippage-bps to match your real costs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Approximate per-side charges in basis points (1 bp = 0.01%) of traded value.
# GST (18%) is applied on brokerage + exchange charges. Rates change - verify them.
EXCHANGE_BPS = 0.30   # NSE transaction charges, ~0.003% each side
SEBI_BPS = 0.01
GST_RATE = 0.18
DELIVERY_STT_BPS = 10.0       # 0.1% on BOTH buy and sell for delivery
DELIVERY_STAMP_BUY_BPS = 1.5  # 0.015% on buy
INTRADAY_STT_SELL_BPS = 2.5   # 0.025% on sell only
INTRADAY_STAMP_BUY_BPS = 0.3  # 0.003% on buy


def side_cost_bps(segment: str, side: str, brokerage_bps: float, slippage_bps: float) -> float:
    """Cost of one buy or one sell, in basis points of traded value."""
    if segment not in {"delivery", "intraday"}:
        raise ValueError("segment must be 'delivery' or 'intraday'")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    if segment == "delivery":
        stt = DELIVERY_STT_BPS
        stamp = DELIVERY_STAMP_BUY_BPS if side == "buy" else 0.0
    else:
        stt = INTRADAY_STT_SELL_BPS if side == "sell" else 0.0
        stamp = INTRADAY_STAMP_BUY_BPS if side == "buy" else 0.0
    gst = GST_RATE * (brokerage_bps + EXCHANGE_BPS + SEBI_BPS)
    return stt + stamp + brokerage_bps + EXCHANGE_BPS + SEBI_BPS + gst + slippage_bps


def performance(daily: pd.Series) -> dict[str, float]:
    daily = daily.dropna()
    if daily.empty:
        return {}
    equity = (1.0 + daily).cumprod()
    years = max(len(daily) / TRADING_DAYS, 1e-9)
    std = daily.std(ddof=1)
    drawdown = equity / equity.cummax() - 1.0
    return {
        "days": int(len(daily)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "cagr": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "annual_volatility": float(std * np.sqrt(TRADING_DAYS)),
        "sharpe": float(daily.mean() / std * np.sqrt(TRADING_DAYS)) if std > 0 else float("nan"),
        "max_drawdown": float(drawdown.min()),
    }


def run_backtest(
    preds: pd.DataFrame,
    threshold: float,
    execution: str = "close",
    segment: str | None = None,
    allow_short: bool = False,
    brokerage_bps: float | None = None,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Equal-weight portfolio: each ticker-day gets 1/N of capital, idle capital earns 0.

    execution='close': enter at today's close, exit at tomorrow's close (matches the
                       model target; positions held on consecutive signals pay costs once).
    execution='open' : enter at tomorrow's open, exit at tomorrow's close (intraday).
    """
    if execution not in {"close", "open"}:
        raise ValueError("execution must be 'close' or 'open'")
    segment = segment or ("delivery" if execution == "close" else "intraday")
    if allow_short and segment == "delivery":
        raise ValueError("Short selling is only possible intraday in the Indian cash market; use --execution open")
    if brokerage_bps is None:
        brokerage_bps = 0.0 if segment == "delivery" else 2.0  # delivery often free at discount brokers

    df = preds.sort_values(["ticker", "date"]).copy()
    ret_col = "fwd_ret_cc" if execution == "close" else "fwd_ret_oc"
    df["pos"] = 0
    df.loc[df["prob_up"] >= threshold, "pos"] = 1
    if allow_short:
        df.loc[df["prob_up"] <= 1.0 - threshold, "pos"] = -1

    buy = side_cost_bps(segment, "buy", brokerage_bps, slippage_bps) / 1e4
    sell = side_cost_bps(segment, "sell", brokerage_bps, slippage_bps) / 1e4

    df["gross"] = df["pos"] * df[ret_col]
    if execution == "close":
        prev = df.groupby("ticker")["pos"].shift(1).fillna(0)
        delta = df["pos"] - prev
        df["cost"] = np.where(delta > 0, delta * buy, -delta * sell)
        entries = int((delta > 0).sum() + (delta < 0).sum() * allow_short)
    else:  # entry and exit on the same day, every active day
        df["cost"] = df["pos"].abs() * (buy + sell)
        entries = int((df["pos"] != 0).sum())
    df["net"] = df["gross"] - df["cost"]

    per_day = df.groupby("date").agg(
        gross=("gross", "sum"), net=("net", "sum"), bench=(ret_col, "mean"), n=("ticker", "size")
    )
    daily = pd.DataFrame(
        {
            "gross": per_day["gross"] / per_day["n"],
            "net": per_day["net"] / per_day["n"],
            "buy_and_hold": per_day["bench"],
        }
    )
    active = df[df["pos"] != 0]
    stats = {
        "threshold": threshold,
        "execution": execution,
        "segment": segment,
        "allow_short": allow_short,
        "brokerage_bps_per_side": brokerage_bps,
        "slippage_bps_per_side": slippage_bps,
        "round_trip_cost_bps": (buy + sell) * 1e4,
        "trades": entries,
        "exposure": float((df["pos"] != 0).mean()),
        "hit_rate_active_days": float((active["net"] > 0).mean()) if len(active) else float("nan"),
        "avg_net_return_per_active_day_bps": float(active["net"].mean() * 1e4) if len(active) else float("nan"),
        "strategy_gross": performance(daily["gross"]),
        "strategy_net": performance(daily["net"]),
        "buy_and_hold": performance(daily["buy_and_hold"]),
    }
    return {"stats": stats, "daily": daily}


def _fmt(perf: dict[str, float]) -> str:
    if not perf:
        return "n/a"
    return (f"return {perf['total_return']:+8.1%}  CAGR {perf['cagr']:+7.1%}  vol {perf['annual_volatility']:6.1%}  "
            f"Sharpe {perf['sharpe']:5.2f}  maxDD {perf['max_drawdown']:7.1%}")


def print_report(stats: dict[str, Any]) -> None:
    print(f"\nthreshold {stats['threshold']:.2f} | {stats['execution']} execution | {stats['segment']} costs "
          f"(round trip ≈ {stats['round_trip_cost_bps']:.1f} bps) | short={stats['allow_short']}")
    hit, avg = stats["hit_rate_active_days"], stats["avg_net_return_per_active_day_bps"]
    hit_txt = "n/a" if np.isnan(hit) else f"{hit:.1%}"
    avg_txt = "n/a" if np.isnan(avg) else f"{avg:+.1f} bps"
    print(f"  trades {stats['trades']:,}  exposure {stats['exposure']:.1%}  "
          f"hit rate {hit_txt}  avg net/active day {avg_txt}")
    if stats["trades"] == 0:
        print("  (no trades: the model never reached this threshold - that is a normal outcome for next-day direction)")
    print(f"  strategy (gross)   {_fmt(stats['strategy_gross'])}")
    print(f"  strategy (net)     {_fmt(stats['strategy_net'])}")
    print(f"  buy & hold (EW)    {_fmt(stats['buy_and_hold'])}")


def default_threshold(predictions_path: Path) -> float:
    metrics = predictions_path.parent / "metrics.json"
    if metrics.is_file():
        try:
            return float(json.loads(metrics.read_text())["thresholds"]["buy"])
        except (KeyError, ValueError, json.JSONDecodeError):
            pass
    return 0.55


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--predictions", default="ml/artifacts/test_predictions.csv")
    p.add_argument("--threshold", type=float, help="P(up) needed to go long (default: value saved by pipeline.py)")
    p.add_argument("--execution", choices=["close", "open"], default="close")
    p.add_argument("--segment", choices=["delivery", "intraday"], help="cost model (default follows --execution)")
    p.add_argument("--allow-short", action="store_true", help="intraday only: short when P(up) <= 1 - threshold")
    p.add_argument("--brokerage-bps", type=float, help="brokerage per side in bps (default 0 delivery / 2 intraday)")
    p.add_argument("--slippage-bps", type=float, default=5.0, help="slippage per side in bps (default 5)")
    p.add_argument("--no-sweep", action="store_true", help="skip the threshold sweep table")
    p.add_argument("--out-dir", help="where to write backtest_report.json / equity.csv / equity.png")
    args = p.parse_args(argv)

    path = Path(args.predictions)
    preds = pd.read_csv(path, parse_dates=["date"])
    threshold = args.threshold if args.threshold is not None else default_threshold(path)
    kwargs = dict(
        execution=args.execution,
        segment=args.segment,
        allow_short=args.allow_short,
        brokerage_bps=args.brokerage_bps,
        slippage_bps=args.slippage_bps,
    )
    result = run_backtest(preds, threshold, **kwargs)
    print(f"test period {preds['date'].min().date()} -> {preds['date'].max().date()}, "
          f"{preds['ticker'].nunique()} tickers, {len(preds):,} rows")
    print_report(result["stats"])

    sweep = []
    if not args.no_sweep:
        print("\nthreshold sweep (informational only - do NOT pick the best row and call it your result):")
        print("  thr   trades  exposure   net return   net Sharpe   gross Sharpe")
        for t in (0.50, 0.52, 0.55, 0.60):
            r = run_backtest(preds, t, **kwargs)["stats"]
            sweep.append(r)
            print(f"  {t:.2f} {r['trades']:>7,}   {r['exposure']:7.1%}   {r['strategy_net'].get('total_return', float('nan')):+10.1%}"
                  f"   {r['strategy_net'].get('sharpe', float('nan')):10.2f}   {r['strategy_gross'].get('sharpe', float('nan')):12.2f}")

    out_dir = Path(args.out_dir) if args.out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backtest_report.json").write_text(json.dumps({"headline": result["stats"], "sweep": sweep}, indent=2, default=str))
    equity = (1.0 + result["daily"]).cumprod()
    equity.to_csv(out_dir / "equity.csv")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(equity.index, equity["net"], label="strategy (net of costs)")
        ax.plot(equity.index, equity["gross"], label="strategy (gross)", alpha=0.5)
        ax.plot(equity.index, equity["buy_and_hold"], label="buy & hold (equal weight)")
        ax.set_title("Test-period equity curves (start = 1.0)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "equity.png", dpi=130)
        plt.close(fig)
    except ImportError:
        pass
    print(f"\nwrote {out_dir / 'backtest_report.json'}, equity.csv" + (", equity.png" if (out_dir / 'equity.png').exists() else ""))
    print("Reminder: a backtest on one test period is evidence, not proof. Costs here are approximations.")


if __name__ == "__main__":
    main(sys.argv[1:])
