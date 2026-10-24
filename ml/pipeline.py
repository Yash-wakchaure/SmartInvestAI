"""Training pipeline for next-trading-day direction prediction.

What it does, in order:
  1. loads OHLCV data and builds scale-free, causal features (common.py);
  2. splits by GLOBAL calendar date (train / validation / test) with an embargo;
  3. trains several models and picks one on VALIDATION ROC-AUC;
  4. calibrates its probabilities on validation (Platt scaling);
  5. scores the untouched TEST period once, against a majority-class baseline;
  6. reports walk-forward stability, per-ticker results and strong-signal metrics;
  7. saves the model artifact, metrics.json and test_predictions.csv (for backtest.py).

Run from the SmartInvestAI directory:
    python ml/pipeline.py --input path/to/data.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.stats import binomtest
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:  # works as `python ml/pipeline.py` and as `python -m ml.pipeline`
    from .common import (
        DEFAULT_BUY_THRESHOLD,
        DEFAULT_SELL_THRESHOLD,
        FEATURE_COLUMNS,
        MIN_HISTORY_ROWS,
        WARMUP_ROWS,
        build_dataset,
        build_market_proxy,
        fit_calibrator,
        predict_proba_up,
        split_by_date,
    )
except ImportError:  # pragma: no cover
    from common import (  # type: ignore
        DEFAULT_BUY_THRESHOLD,
        DEFAULT_SELL_THRESHOLD,
        FEATURE_COLUMNS,
        MIN_HISTORY_ROWS,
        WARMUP_ROWS,
        build_dataset,
        build_market_proxy,
        fit_calibrator,
        predict_proba_up,
        split_by_date,
    )

try:
    from xgboost import XGBClassifier
except ImportError:
    XGBClassifier = None

BASE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]
STRONG_THRESHOLDS = (0.52, 0.55, 0.60, 0.65)
TARGET_DEFINITION = "1 if same-ticker next close is greater than current close, otherwise 0"


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def _check_not_lfs_pointer(path: Path) -> None:
    with open(path, "rb") as handle:
        head = handle.read(200)
    if head.startswith(b"version https://git-lfs"):
        raise SystemExit(
            f"{path} is a Git LFS pointer, not the real CSV. Run `git lfs pull` "
            "(or download the file directly) and try again."
        )


def load_market_data(
    input_path: str | Path,
    sample_tickers: int | None = None,
    min_rows: int = 300,
    seed: int = 42,
) -> pd.DataFrame:
    path = Path(input_path)
    _check_not_lfs_pointer(path)
    wanted = set(BASE_COLUMNS)
    data = pd.read_csv(path, usecols=lambda c: c.strip().lower() in wanted)
    data.columns = [c.strip().lower() for c in data.columns]
    missing = wanted.difference(data.columns)
    if missing:
        raise SystemExit(f"CSV is missing required columns: {sorted(missing)}")

    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["ticker"] = data["ticker"].astype(str).str.upper().str.strip()
    numeric = [c for c in BASE_COLUMNS if c not in {"date", "ticker"}]
    data[numeric] = data[numeric].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=BASE_COLUMNS)
    data = data[(data[["open", "high", "low", "close"]] > 0).all(axis=1) & (data["volume"] >= 0)]
    data = data.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])

    counts = data.groupby("ticker")["date"].transform("size")
    data = data[counts >= min_rows]
    if sample_tickers:
        tickers = sorted(data["ticker"].unique())
        rng = np.random.default_rng(seed)
        keep = set(rng.choice(tickers, size=min(sample_tickers, len(tickers)), replace=False))
        data = data[data["ticker"].isin(keep)]
    if data.empty:
        raise SystemExit("No usable rows after cleaning; check the CSV columns and min-rows")
    return data.reset_index(drop=True)


def load_market_close(args: argparse.Namespace, data: pd.DataFrame) -> tuple[pd.Series, str]:
    """Return (index close series, description of where it came from)."""
    if args.market_source == "csv":
        if not args.index_csv:
            raise SystemExit("--market-source csv needs --index-csv (columns: date, close)")
        idx = pd.read_csv(args.index_csv)
        idx.columns = [c.strip().lower() for c in idx.columns]
        idx["date"] = pd.to_datetime(idx["date"]).dt.tz_localize(None).dt.normalize()
        series = idx.drop_duplicates("date").set_index("date")["close"].astype(float).sort_index()
        return series, f"csv:{args.index_csv}"
    if args.market_source == "yfinance":
        import yfinance as yf  # imported lazily so training works without it

        start, end = data["date"].min(), data["date"].max() + pd.Timedelta(days=5)
        hist = yf.Ticker(args.index_ticker).history(start=start, end=end, auto_adjust=True)
        if hist.empty:
            raise SystemExit(f"yfinance returned no data for {args.index_ticker}")
        idx = hist["Close"].copy()
        idx.index = pd.to_datetime(idx.index).tz_localize(None).normalize()
        return idx, f"yfinance:{args.index_ticker}"
    return build_market_proxy(data), "proxy:equal-weight-of-training-universe"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def build_models(fast: bool = False) -> dict[str, Any]:
    trees = 40 if fast else 300
    models: dict[str, Any] = {
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=0.1, max_iter=2000),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=trees,
            max_depth=6,
            min_samples_leaf=100,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_depth=3,
            learning_rate=0.05,
            max_iter=60 if fast else 200,
            min_samples_leaf=100,
            l2_regularization=1.0,
            random_state=42,
        ),
    }
    if XGBClassifier is not None:
        models["xgboost"] = XGBClassifier(
            n_estimators=60 if fast else 300,
            max_depth=3,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=50,
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            random_state=42,
            n_jobs=-1,
        )
    return models


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _auc(y: np.ndarray, p: np.ndarray) -> float:
    return float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else float("nan")


def strong_signal_table(y: np.ndarray, p: np.ndarray, thresholds=STRONG_THRESHOLDS) -> list[dict[str, float]]:
    """Accuracy only on rows where the model is at least `t` sure of either direction."""
    rows = []
    confidence = np.maximum(p, 1 - p)
    for t in thresholds:
        mask = confidence >= t
        n = int(mask.sum())
        if n == 0:
            rows.append({"threshold": t, "n": 0, "coverage": 0.0, "accuracy": float("nan"), "baseline": float("nan")})
            continue
        pred = (p[mask] >= 0.5).astype(int)
        rows.append(
            {
                "threshold": t,
                "n": n,
                "coverage": n / len(y),
                "accuracy": float((pred == y[mask]).mean()),
                "baseline": float(max(y[mask].mean(), 1 - y[mask].mean())),
            }
        )
    return rows


def evaluate(y_true: pd.Series, prob: np.ndarray, baseline_class: int) -> dict[str, Any]:
    y = np.asarray(y_true).astype(int)
    pred = (prob >= 0.5).astype(int)
    baseline_acc = float((y == baseline_class).mean())
    correct = int((pred == y).sum())
    # NOTE: rows of the same day are correlated (stocks move together), so this
    # p-value is optimistic. Treat it as a sanity check, not as proof of skill.
    p_value = float(binomtest(correct, len(y), baseline_acc, alternative="greater").pvalue)
    return {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "baseline_accuracy": baseline_acc,
        "baseline_class": baseline_class,
        "edge_over_baseline": float(accuracy_score(y, pred) - baseline_acc),
        "p_value_vs_baseline": p_value,
        "roc_auc": _auc(y, prob),
        "brier": float(brier_score_loss(y, prob)),
        "log_loss": float(log_loss(y, np.clip(prob, 1e-6, 1 - 1e-6), labels=[0, 1])),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
        "strong_signals": strong_signal_table(y, prob),
    }


def per_ticker_summary(frame: pd.DataFrame, prob: np.ndarray, baseline_class: int) -> dict[str, Any]:
    df = pd.DataFrame(
        {
            "ticker": frame["ticker"].to_numpy(),
            "y": frame["target"].to_numpy().astype(int),
            "pred": (prob >= 0.5).astype(int),
        }
    )
    df["hit"] = (df["pred"] == df["y"]).astype(float)
    df["base_hit"] = (df["y"] == baseline_class).astype(float)
    grouped = df.groupby("ticker").agg(n=("y", "size"), accuracy=("hit", "mean"), baseline=("base_hit", "mean"))
    grouped = grouped[grouped["n"] >= 30]
    if grouped.empty:
        return {"tickers_evaluated": 0}
    grouped["edge"] = grouped["accuracy"] - grouped["baseline"]
    return {
        "tickers_evaluated": int(len(grouped)),
        "median_accuracy": float(grouped["accuracy"].median()),
        "median_edge_over_baseline": float(grouped["edge"].median()),
        "share_beating_baseline": float((grouped["edge"] > 0).mean()),
        "best_5": grouped.sort_values("edge", ascending=False).head(5)["edge"].round(4).to_dict(),
        "worst_5": grouped.sort_values("edge").head(5)["edge"].round(4).to_dict(),
    }


def walk_forward(dev: pd.DataFrame, model_name: str, fast: bool, n_splits: int = 5, embargo: int = 1) -> dict[str, Any]:
    """Expanding-window evaluation on the development period (train+validation only)."""
    dates = np.sort(dev["date"].unique())
    chunks = np.array_split(dates, n_splits + 1)
    folds = []
    for k in range(1, n_splits + 1):
        train_dates = np.concatenate(chunks[:k])
        test_dates = chunks[k]
        train_dates = train_dates[: max(len(train_dates) - embargo, 1)]
        tr = dev[dev["date"].isin(train_dates)]
        te = dev[dev["date"].isin(test_dates)]
        if tr["target"].nunique() < 2 or len(te) == 0:
            continue
        model = clone(build_models(fast)[model_name])
        model.fit(tr[FEATURE_COLUMNS], tr["target"])
        prob = model.predict_proba(te[FEATURE_COLUMNS])[:, 1]
        y = te["target"].to_numpy()
        base_class = int(tr["target"].mean() >= 0.5)
        folds.append(
            {
                "fold": k,
                "test_from": str(pd.Timestamp(test_dates[0]).date()),
                "test_to": str(pd.Timestamp(test_dates[-1]).date()),
                "n": int(len(te)),
                "accuracy": float(((prob >= 0.5).astype(int) == y).mean()),
                "baseline_accuracy": float((y == base_class).mean()),
                "roc_auc": _auc(y, prob),
            }
        )
    if not folds:
        return {"folds": []}
    acc = np.array([f["accuracy"] for f in folds])
    base = np.array([f["baseline_accuracy"] for f in folds])
    auc = np.array([f["roc_auc"] for f in folds])
    return {
        "folds": folds,
        "mean_accuracy": float(acc.mean()),
        "std_accuracy": float(acc.std()),
        "mean_baseline_accuracy": float(base.mean()),
        "mean_roc_auc": float(np.nanmean(auc)),
        "folds_beating_baseline": int((acc > base).sum()),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def train_and_evaluate(
    dataset: pd.DataFrame,
    model_path: str | Path,
    *,
    market_source: str,
    split_kwargs: dict[str, Any] | None = None,
    buy_threshold: float = DEFAULT_BUY_THRESHOLD,
    refit_all: bool = False,
    fast: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    log = print if verbose else (lambda *a, **k: None)
    train, val, test, split_info = split_by_date(dataset, **(split_kwargs or {}))
    baseline_class = int(train["target"].mean() >= 0.5)
    log(f"rows: train={len(train):,}  validation={len(val):,}  test={len(test):,}  tickers={dataset['ticker'].nunique()}")
    log(f"train {split_info['train_range']}  val {split_info['val_range']}  test {split_info['test_range']}")
    log(f"baseline (always predict {'UP' if baseline_class else 'DOWN'}): "
        f"test accuracy {float((test['target'] == baseline_class).mean()):.4f}")

    # 1) fit every candidate on train, compare on validation
    validation_results: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for name, model in build_models(fast).items():
        model.fit(train[FEATURE_COLUMNS], train["target"])
        fitted[name] = model
        prob = model.predict_proba(val[FEATURE_COLUMNS])[:, 1]
        validation_results[name] = evaluate(val["target"], prob, baseline_class)
        v = validation_results[name]
        log(f"  {name:<24} val acc={v['accuracy']:.4f} (baseline {v['baseline_accuracy']:.4f})  auc={v['roc_auc']:.4f}  brier={v['brier']:.4f}")

    selected = max(validation_results, key=lambda n: (validation_results[n]["roc_auc"], -validation_results[n]["log_loss"]))
    model = fitted[selected]
    log(f"selected on validation ROC-AUC: {selected}")

    # 2) calibrate on validation, then score the untouched test period ONCE
    val_raw = model.predict_proba(val[FEATURE_COLUMNS])[:, 1]
    calibrator = fit_calibrator(val_raw, val["target"].to_numpy())
    artifact: dict[str, Any] = {
        "model": model,
        "calibrator": calibrator,
        "model_name": selected,
        "feature_columns": list(FEATURE_COLUMNS),
        "target_definition": TARGET_DEFINITION,
        "interval": "next trading day",
        "thresholds": {"buy": buy_threshold, "sell": 1 - buy_threshold},
        "market_source": market_source,
        "warmup_rows": WARMUP_ROWS,
        "min_history_rows": MIN_HISTORY_ROWS,
        "split": split_info,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "refit_on_all_data": False,
    }
    test_raw = model.predict_proba(test[FEATURE_COLUMNS])[:, 1]
    test_prob = predict_proba_up(artifact, test)
    test_results = evaluate(test["target"], test_prob, baseline_class)
    test_results["roc_auc_uncalibrated"] = _auc(test["target"].to_numpy(), test_raw)
    test_results["brier_uncalibrated"] = float(brier_score_loss(test["target"], test_raw))
    test_results["per_ticker"] = per_ticker_summary(test, test_prob, baseline_class)

    # 3) stability over time (development period only, never touches the test set)
    dev = pd.concat([train, val], ignore_index=True)
    wf = walk_forward(dev, selected, fast)

    # 4) predictions file for backtest.py (from the honest, not refit, model)
    predictions = test[["date", "ticker", "close", "target", "fwd_ret_cc", "fwd_ret_oc"]].copy()
    predictions["prob_up"] = test_prob

    if refit_all:
        final = clone(model)
        everything = pd.concat([dev, test], ignore_index=True)
        final.fit(everything[FEATURE_COLUMNS], everything["target"])
        artifact["model"] = final
        artifact["refit_on_all_data"] = True
        log("refit selected model on ALL rows (calibrator kept from validation fit)")

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)

    report = {
        "selected_model": selected,
        "baseline_class": baseline_class,
        "split": split_info,
        "market_source": market_source,
        "thresholds": artifact["thresholds"],
        "validation": validation_results,
        "test": test_results,
        "walk_forward": wf,
    }
    out_dir = model_path.parent
    (out_dir / "metrics.json").write_text(json.dumps(_clean_json(report), indent=2, default=_json_default))
    predictions.to_csv(out_dir / "test_predictions.csv", index=False)

    log("\n=== TEST (held out, calibrated) ===")
    log(f"accuracy {test_results['accuracy']:.4f} vs baseline {test_results['baseline_accuracy']:.4f}  "
        f"(edge {test_results['edge_over_baseline']:+.4f}, p={test_results['p_value_vs_baseline']:.3f})")
    log(f"roc_auc {test_results['roc_auc']:.4f}  brier {test_results['brier']:.4f}  log_loss {test_results['log_loss']:.4f}")
    log("strong signals (model at least t sure):")
    for row in test_results["strong_signals"]:
        log(f"  t>={row['threshold']:.2f}  n={row['n']:>7,}  coverage={row['coverage']:.1%}  "
            f"accuracy={row['accuracy']:.4f}  baseline={row['baseline']:.4f}")
    pt = test_results["per_ticker"]
    if pt.get("tickers_evaluated"):
        log(f"per ticker: median edge {pt['median_edge_over_baseline']:+.4f}, "
            f"{pt['share_beating_baseline']:.0%} of {pt['tickers_evaluated']} tickers beat baseline")
    if wf.get("folds"):
        log(f"walk-forward ({len(wf['folds'])} folds): accuracy {wf['mean_accuracy']:.4f} ± {wf['std_accuracy']:.4f} "
            f"vs baseline {wf['mean_baseline_accuracy']:.4f}; beat baseline in {wf['folds_beating_baseline']}/{len(wf['folds'])} folds")
    if test_results["accuracy"] > 0.60:
        log("WARNING: next-day accuracy above 60% is very unusual - check for data leakage before trusting it.")
    log(f"\nsaved model:       {model_path}")
    log(f"saved metrics:     {out_dir / 'metrics.json'}")
    log(f"saved predictions: {out_dir / 'test_predictions.csv'}  (use with ml/backtest.py)")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="OHLCV CSV with columns date,ticker,open,high,low,close,volume")
    p.add_argument("--model-output", default="ml/artifacts/next_day_direction.joblib")
    p.add_argument("--train-end", help="first date of the validation period, e.g. 2022-01-01 (default: 70%% of dates)")
    p.add_argument("--val-end", help="first date of the test period, e.g. 2023-07-01 (default: 85%% of dates)")
    p.add_argument("--embargo", type=int, default=1, help="trading days dropped before each cutoff (default 1)")
    p.add_argument("--market-source", choices=["proxy", "csv", "yfinance"], default="proxy",
                   help="where market-context features come from (default: equal-weight index of the CSV's tickers)")
    p.add_argument("--index-csv", help="CSV with date,close of a market index (for --market-source csv)")
    p.add_argument("--index-ticker", default="^NSEI", help="Yahoo ticker for --market-source yfinance")
    p.add_argument("--buy-threshold", type=float, default=DEFAULT_BUY_THRESHOLD,
                   help="P(up) at or above this is BUY; at or below 1-this is SELL")
    p.add_argument("--sample-tickers", type=int, help="use a random subset of tickers (faster experiments)")
    p.add_argument("--min-rows", type=int, default=300, help="drop tickers with fewer rows")
    p.add_argument("--refit-all", action="store_true", help="after evaluation, refit the chosen model on all rows")
    p.add_argument("--fast", action="store_true", help="smaller models (smoke tests)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if XGBClassifier is None:
        print("note: xgboost not installed, skipping it (pip install xgboost to include it)")
    raw = load_market_data(args.input, sample_tickers=args.sample_tickers, min_rows=args.min_rows)
    print(f"loaded {len(raw):,} rows, {raw['ticker'].nunique()} tickers, {raw['date'].min().date()} -> {raw['date'].max().date()}")
    market_close, market_source = load_market_close(args, raw)
    dataset = build_dataset(raw, market_close)
    print(f"market context: {market_source}")
    train_and_evaluate(
        dataset,
        args.model_output,
        market_source=market_source,
        split_kwargs={"train_end": args.train_end, "val_end": args.val_end, "embargo": args.embargo},
        buy_threshold=args.buy_threshold,
        refit_all=args.refit_all,
        fast=args.fast,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
