"""Shared feature engineering, date splits and probability helpers.

This module is imported by pipeline.py (training), api.py (serving), predict.py
and backtest.py. Training and serving call the *same* functions, so a feature
cannot be computed one way in the notebook and another way in the API.

Rules every feature here follows:
  * causal - the value at date t only uses rows dated <= t;
  * scale-free - ratios and returns, never raw prices, so the model cannot
    identify a stock from its price level.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

OHLCV = ["open", "high", "low", "close", "volume"]

STOCK_FEATURES = [
    # momentum / returns
    "ret_1", "ret_3", "ret_5", "ret_10",
    # day-trader candle features
    "gap_pct", "range_pct", "body_pct", "close_pos",
    # volatility
    "atr_pct", "vol_20",
    # volume
    "rel_volume", "volume_chg",
    # oscillators / trend
    "rsi_14", "macd_pct", "macd_hist_pct",
    "pct_b", "bb_width",
    "close_vs_sma5", "close_vs_sma20", "close_vs_ema12",
    # position inside recent range
    "dist_high_20", "dist_low_20",
]
MARKET_FEATURES = ["mkt_ret_1", "mkt_ret_5", "mkt_vol_20", "rel_strength_5"]
FEATURE_COLUMNS = STOCK_FEATURES + MARKET_FEATURES

WARMUP_ROWS = 60          # first rows of each ticker are dropped in training (EMA seeding)
MIN_HISTORY_ROWS = 120    # minimum rows the API needs to compute reliable features
DEFAULT_BUY_THRESHOLD = 0.55
DEFAULT_SELL_THRESHOLD = 0.45

IST = ZoneInfo("Asia/Kolkata")
NSE_CLOSE = time(15, 30)


# --------------------------------------------------------------------------- #
# Indicators and features
# --------------------------------------------------------------------------- #
def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def compute_indicators(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Single-ticker indicators. Index must be a sorted DatetimeIndex.

    Returns the STOCK_FEATURES plus raw columns used for display/risk levels
    (close, atr, macd, macd_signal, bb_upper, bb_lower).
    """
    d = ohlcv[OHLCV].astype(float)
    open_, high, low, close, volume = (d[c] for c in OHLCV)
    prev_close = close.shift(1)

    out = pd.DataFrame(index=d.index)
    out["close"] = close

    for n in (1, 3, 5, 10):
        out[f"ret_{n}"] = close / close.shift(n) - 1.0

    out["gap_pct"] = open_ / prev_close - 1.0
    day_range = (high - low).replace(0, np.nan)
    out["range_pct"] = (high - low) / close
    out["body_pct"] = (close - open_) / open_
    out["close_pos"] = ((close - low) / day_range).fillna(0.5)

    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    out["atr"] = _wilder(true_range, 14)
    out["atr_pct"] = out["atr"] / close
    out["vol_20"] = out["ret_1"].rolling(20, min_periods=20).std()

    vol_ma20 = volume.rolling(20, min_periods=20).mean()
    out["rel_volume"] = np.log((volume + 1.0) / (vol_ma20 + 1.0)).clip(-3, 3)
    out["volume_chg"] = np.log((volume + 1.0) / (volume.shift(1) + 1.0)).clip(-3, 3)

    # RSI(14), Wilder smoothing. No losses -> 100, no movement -> 50.
    delta = close.diff()
    avg_gain = _wilder(delta.clip(lower=0), 14)
    avg_loss = _wilder((-delta).clip(lower=0), 14)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    out["rsi_14"] = rsi

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    out["macd_pct"] = out["macd"] / close
    out["macd_hist_pct"] = (out["macd"] - out["macd_signal"]) / close

    sma5 = close.rolling(5, min_periods=5).mean()
    sma20 = close.rolling(20, min_periods=20).mean()
    bb_std = close.rolling(20, min_periods=20).std()
    out["bb_upper"] = sma20 + 2 * bb_std
    out["bb_lower"] = sma20 - 2 * bb_std
    band_width = (out["bb_upper"] - out["bb_lower"]).replace(0, np.nan)
    out["pct_b"] = ((close - out["bb_lower"]) / band_width).fillna(0.5).clip(-1, 2)
    out["bb_width"] = band_width / sma20

    out["close_vs_sma5"] = close / sma5 - 1.0
    out["close_vs_sma20"] = close / sma20 - 1.0
    out["close_vs_ema12"] = close / ema12 - 1.0
    out["dist_high_20"] = close / high.rolling(20, min_periods=20).max() - 1.0
    out["dist_low_20"] = close / low.rolling(20, min_periods=20).min() - 1.0

    return out.replace([np.inf, -np.inf], np.nan)


def compute_market_features(market_close: pd.Series) -> pd.DataFrame:
    """Market-context features from an index (or index proxy) close series."""
    m = market_close.astype(float).sort_index()
    m = m[~m.index.duplicated(keep="last")]
    ret_1 = m / m.shift(1) - 1.0
    return pd.DataFrame(
        {
            "mkt_ret_1": ret_1,
            "mkt_ret_5": m / m.shift(5) - 1.0,
            "mkt_vol_20": ret_1.rolling(20, min_periods=20).std(),
        },
        index=m.index,
    )


def compute_feature_frame(ohlcv: pd.DataFrame, market_close: pd.Series) -> pd.DataFrame:
    """All FEATURE_COLUMNS (plus display columns) for one ticker, one row per date.

    Used by BOTH training and the API.
    """
    ind = compute_indicators(ohlcv)
    mkt = compute_market_features(market_close).reindex(ind.index).ffill(limit=2)
    frame = ind.join(mkt)
    frame["rel_strength_5"] = frame["ret_5"] - frame["mkt_ret_5"]
    return frame


def build_market_proxy(data: pd.DataFrame, min_names: int = 3) -> pd.Series:
    """Equal-weighted index built from the training universe itself.

    Uses only same-date returns of the tickers, so it is causal. Used when no
    real index series is supplied.
    """
    prev = data.groupby("ticker")["close"].shift(1)
    ret = (data["close"] / prev - 1.0).clip(-0.5, 0.5)
    grouped = ret.groupby(data["date"])
    mean_ret = grouped.mean().where(grouped.count() >= min(min_names, data["ticker"].nunique()))
    mean_ret = mean_ret.sort_index().fillna(0.0)
    return 100.0 * (1.0 + mean_ret).cumprod()


def build_dataset(
    data: pd.DataFrame,
    market_close: pd.Series,
    *,
    max_return: float = 0.5,
    warmup_rows: int = WARMUP_ROWS,
) -> pd.DataFrame:
    """Long table: date, ticker, FEATURE_COLUMNS, target and forward returns.

    target(t)=1 if close(t+1) > close(t). The last row of every ticker has no
    next close and is dropped. Rows next to absurd moves (likely unadjusted
    splits / bad ticks) are dropped as well.
    """
    parts = []
    for ticker, group in data.groupby("ticker", sort=False):
        g = group.sort_values("date").drop_duplicates("date").set_index("date")
        if len(g) <= warmup_rows + 5:
            continue
        frame = compute_feature_frame(g, market_close)
        out = frame[FEATURE_COLUMNS].copy()
        nxt_close = g["close"].shift(-1)
        out["fwd_ret_cc"] = nxt_close / g["close"] - 1.0           # close(t) -> close(t+1)
        out["fwd_ret_oc"] = nxt_close / g["open"].shift(-1) - 1.0  # open(t+1) -> close(t+1)
        out["target"] = (out["fwd_ret_cc"] > 0).astype("float").where(out["fwd_ret_cc"].notna())
        out["close"] = g["close"]
        out["ticker"] = ticker
        out = out.iloc[warmup_rows:]
        parts.append(out.reset_index())
    if not parts:
        raise ValueError("No ticker has enough history to build features")

    dataset = pd.concat(parts, ignore_index=True)
    dataset = dataset.replace([np.inf, -np.inf], np.nan)
    bad = (dataset["ret_1"].abs() > max_return) | (dataset["fwd_ret_cc"].abs() > max_return)
    dataset = dataset.loc[~bad].dropna(subset=FEATURE_COLUMNS + ["target", "fwd_ret_cc", "fwd_ret_oc"])
    dataset["target"] = dataset["target"].astype(int)
    return dataset.sort_values(["date", "ticker"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def split_by_date(
    data: pd.DataFrame,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    train_end: str | None = None,
    val_end: str | None = None,
    embargo: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Split on GLOBAL calendar dates so every ticker shares the same periods.

    train: date < train_end, validation: train_end <= date < val_end, test: date >= val_end.
    The last `embargo` trading days before each cutoff are dropped, because
    their target uses a close that lies on the other side of the cutoff.
    """
    dates = np.sort(data["date"].unique())
    if train_end is None:
        train_cut = pd.Timestamp(dates[int(len(dates) * train_frac)])
    else:
        train_cut = pd.Timestamp(train_end)
    if val_end is None:
        val_cut = pd.Timestamp(dates[int(len(dates) * (train_frac + val_frac))])
    else:
        val_cut = pd.Timestamp(val_end)
    if not train_cut < val_cut:
        raise ValueError("train_end must be earlier than val_end")

    def embargo_dates(cut: pd.Timestamp) -> np.ndarray:
        pos = int(np.searchsorted(dates, np.datetime64(cut)))
        return dates[max(pos - embargo, 0):pos] if embargo > 0 else dates[:0]

    d = data["date"]
    train = data[(d < train_cut) & ~d.isin(embargo_dates(train_cut))]
    val = data[(d >= train_cut) & (d < val_cut) & ~d.isin(embargo_dates(val_cut))]
    test = data[d >= val_cut]
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError("One of the train/validation/test splits is empty; adjust the split dates")

    info = {
        "train_end": str(train_cut.date()),
        "val_end": str(val_cut.date()),
        "train_range": [str(train["date"].min().date()), str(train["date"].max().date())],
        "val_range": [str(val["date"].min().date()), str(val["date"].max().date())],
        "test_range": [str(test["date"].min().date()), str(test["date"].max().date())],
        "embargo_days": embargo,
    }
    return (
        train.reset_index(drop=True),
        val.reset_index(drop=True),
        test.reset_index(drop=True),
        info,
    )


# --------------------------------------------------------------------------- #
# Probability calibration (Platt scaling, stored as a plain sklearn object so
# the joblib artifact never depends on this module being importable)
# --------------------------------------------------------------------------- #
def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def fit_calibrator(raw_prob: np.ndarray, y: np.ndarray) -> LogisticRegression:
    calibrator = LogisticRegression(C=1e3, max_iter=1000)
    calibrator.fit(_logit(raw_prob), np.asarray(y).astype(int))
    return calibrator


def predict_proba_up(artifact: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    """Calibrated P(next close > close) for rows of `frame`."""
    raw = artifact["model"].predict_proba(frame[artifact["feature_columns"]])[:, 1]
    calibrator = artifact.get("calibrator")
    if calibrator is None:
        return raw
    return calibrator.predict_proba(_logit(raw))[:, 1]


def decision_label(prob_up: float, buy: float = DEFAULT_BUY_THRESHOLD, sell: float = DEFAULT_SELL_THRESHOLD) -> str:
    """The single place that turns a probability into BUY / SELL / HOLD."""
    if prob_up >= buy:
        return "BUY"
    if prob_up <= sell:
        return "SELL"
    return "HOLD"


# --------------------------------------------------------------------------- #
# Live-data helpers (used by the API)
# --------------------------------------------------------------------------- #
def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case columns, drop timezone, normalise index to dates, sort, de-duplicate."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    out.columns = [str(c).lower() for c in out.columns]
    idx = pd.to_datetime(out.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    out.index.name = "date"
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["open", "high", "low", "close"])


def drop_incomplete_bar(df: pd.DataFrame, now: datetime | None = None, buffer_minutes: int = 30) -> pd.DataFrame:
    """Remove today's still-forming daily bar.

    Models are trained on complete daily bars, so a bar fetched during market
    hours (before 15:30 IST + buffer) must not be fed to them.
    """
    if df.empty:
        return df
    now = (now or datetime.now(IST)).astimezone(IST)
    cutoff = (datetime.combine(now.date(), NSE_CLOSE) + timedelta(minutes=buffer_minutes)).time()
    last_date = pd.Timestamp(df.index[-1]).date()
    if last_date == now.date() and now.time() < cutoff:
        return df.iloc[:-1]
    return df
