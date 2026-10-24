"""FastAPI service for next-trading-day direction predictions on Indian markets.

Start from the SmartInvestAI directory:
    uvicorn ml.api:app --host 0.0.0.0 --port 8000

Training and serving share ml/common.py, so features are computed identically.
Predictions use only COMPLETE daily bars (today's unfinished bar is dropped while
the market is open) and ~1 year of history so EMAs/MACD are properly warmed up.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:  # works as `uvicorn ml.api:app` and as `python ml/api.py`
    from .common import (
        DEFAULT_BUY_THRESHOLD,
        DEFAULT_SELL_THRESHOLD,
        MIN_HISTORY_ROWS,
        compute_indicators,
        compute_feature_frame,
        decision_label,
        drop_incomplete_bar,
        normalize_ohlcv,
        predict_proba_up,
    )
except ImportError:  # pragma: no cover
    from common import (  # type: ignore
        DEFAULT_BUY_THRESHOLD,
        DEFAULT_SELL_THRESHOLD,
        MIN_HISTORY_ROWS,
        compute_indicators,
        compute_feature_frame,
        decision_label,
        drop_incomplete_bar,
        normalize_ohlcv,
        predict_proba_up,
    )

logger = logging.getLogger("smartinvest.api")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "next_day_direction.joblib"
INDEX_TICKER = os.getenv("INDEX_TICKER", "^NSEI")
CACHE_TTL_SECONDS = int(os.getenv("DATA_CACHE_SECONDS", "300"))
MAX_SYMBOLS = 25
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9&.^=\-]{1,30}$")
DISCLAIMER = (
    "Model probability that the next close is above the last close. It is not a guarantee, "
    "not the probability of making a profit, and not financial advice."
)

REQUIRED_ARTIFACT_KEYS = {"model", "model_name", "feature_columns", "target_definition", "thresholds"}
LEGACY_FEATURE_COLUMNS = [
    "open", "high", "low", "close", "volume", "price_change", "volume_change",
    "sma_5", "ema_12", "rsi_14", "macd", "macd_signal", "bb_middle", "bb_upper", "bb_lower",
]


def get_model_path() -> Path:
    return Path(os.getenv("MODEL_PATH", str(DEFAULT_MODEL_PATH)))


class PredictionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    features: dict[str, float]


class PredictionResponse(BaseModel):
    symbol: str
    prediction: str
    confidence: float
    probability_up: float
    signal: str
    model: str


model_artifact: dict[str, Any] | None = None


def load_model_artifact() -> dict[str, Any]:
    path = get_model_path()
    if not path.is_file():
        raise RuntimeError(f"Model artifact not found: {path}. Train one with `python ml/pipeline.py --input <csv>`.")
    artifact = joblib.load(path)
    missing = REQUIRED_ARTIFACT_KEYS.difference({"thresholds"}).difference(artifact)
    if missing:
        raise RuntimeError(
            f"Model artifact is missing {sorted(missing)}; it was trained with an older pipeline. Retrain it."
        )
    if "thresholds" not in artifact:
        if artifact["feature_columns"] != LEGACY_FEATURE_COLUMNS:
            raise RuntimeError("Model artifact is missing thresholds and does not match the supported legacy feature schema.")
        artifact["thresholds"] = {
            "buy": DEFAULT_BUY_THRESHOLD,
            "sell": DEFAULT_SELL_THRESHOLD,
        }
    return artifact


@asynccontextmanager
async def lifespan(_: FastAPI):
    global model_artifact
    try:
        model_artifact = load_model_artifact()
        logger.info("Loaded model %s from %s", model_artifact["model_name"], get_model_path())
    except Exception:
        logger.exception("Could not load the model artifact; API will answer 503 on prediction routes")
        model_artifact = None
    yield


app = FastAPI(title="SmartInvest AI ML API", version="2.0.0", lifespan=lifespan)

_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Market data access (cached)
# --------------------------------------------------------------------------- #
class DataError(Exception):
    def __init__(self, message: str, status_code: int = 404):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


_cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
_cache_lock = threading.Lock()


def format_ticker(symbol: str) -> str:
    raw = symbol.strip().upper()
    if not SYMBOL_PATTERN.match(raw):
        raise DataError(f"Invalid symbol: {symbol!r}", 422)
    if raw.endswith((".NS", ".BO")) or raw.startswith("^") or "=" in raw:
        return raw
    return f"{raw}.NS"


def display_symbol(ticker: str) -> str:
    return ticker.replace(".NS", "").replace(".BO", "")


def fetch_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Daily OHLCV for a Yahoo ticker, normalised and cached for a few minutes."""
    key = (ticker, period)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1].copy()
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    except Exception as exc:
        logger.warning("Market data request failed for %s: %s", ticker, exc)
        raise DataError("Market data provider is unavailable, try again shortly", 502) from exc
    if hist is None or hist.empty:
        raise DataError(f"No market data found for {display_symbol(ticker)}", 404)
    frame = normalize_ohlcv(hist)
    with _cache_lock:
        _cache[key] = (now, frame)
    return frame.copy()


def compute_legacy_feature_frame(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Build the feature schema used by the bundled pre-v2 model."""
    close = ohlcv["close"]
    volume = ohlcv["volume"]
    features = ohlcv[["open", "high", "low", "close", "volume"]].copy()
    features["price_change"] = close.pct_change()
    features["volume_change"] = volume.pct_change()
    features["sma_5"] = close.rolling(window=5).mean()
    features["ema_12"] = close.ewm(span=12, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    features["rsi_14"] = (100 - (100 / (1 + rs))).fillna(50.0)

    ema_26 = close.ewm(span=26, adjust=False).mean()
    features["macd"] = features["ema_12"] - ema_26
    features["macd_signal"] = features["macd"].ewm(span=9, adjust=False).mean()
    features["bb_middle"] = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    features["bb_upper"] = features["bb_middle"] + 2 * bb_std
    features["bb_lower"] = features["bb_middle"] - 2 * bb_std
    return features.replace([float("inf"), float("-inf")], float("nan"))


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def require_model() -> dict[str, Any]:
    if model_artifact is None:
        raise HTTPException(status_code=503, detail="Prediction model is not loaded")
    return model_artifact


def volatility_risk(atr_pct: float) -> str:
    """Risk label from realised volatility (ATR as % of price), not from model confidence."""
    if atr_pct < 0.015:
        return "low"
    if atr_pct < 0.03:
        return "medium"
    return "high"


def score_symbol(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    artifact = require_model()
    ticker = format_ticker(symbol)
    raw = fetch_history(ticker)
    bars = drop_incomplete_bar(raw, now)
    min_rows = int(artifact.get("min_history_rows", MIN_HISTORY_ROWS))
    if len(bars) < min_rows:
        raise DataError(f"Not enough price history for {display_symbol(ticker)} ({len(bars)} days, need {min_rows})", 422)
    as_of = bars.index[-1]
    cols = artifact["feature_columns"]
    if cols == LEGACY_FEATURE_COLUMNS:
        frame = compute_legacy_feature_frame(bars)
        indicators = compute_indicators(bars)
    else:
        index_raw = fetch_history(INDEX_TICKER)
        index_bars = drop_incomplete_bar(index_raw, now)
        if index_bars.empty or index_bars.index[-1] < as_of - pd.Timedelta(days=4):
            raise DataError("Market index data is stale; cannot build market-context features", 502)
        frame = compute_feature_frame(bars, index_bars["close"])
        indicators = frame

    latest = frame.iloc[[-1]]
    if latest[cols].isna().to_numpy().any():
        raise DataError(f"Could not compute all features for {display_symbol(ticker)}", 422)

    prob_up = float(predict_proba_up(artifact, latest)[0])
    thresholds = artifact["thresholds"]
    signal = decision_label(prob_up, thresholds["buy"], thresholds["sell"])

    last = indicators.iloc[-1]
    live_price = float(raw["close"].iloc[-1])
    prev_price = float(raw["close"].iloc[-2]) if len(raw) > 1 else live_price
    return {
        "symbol": display_symbol(ticker),
        "as_of": str(as_of.date()),
        "probability_up": prob_up,
        "signal": signal,
        "thresholds": thresholds,
        "live_price": live_price,
        "change_pct": (live_price - prev_price) / prev_price * 100 if prev_price else 0.0,
        "close": float(last["close"]),
        "atr": float(last["atr"]),
        "atr_pct": float(last["atr_pct"]),
        "rsi": float(last["rsi_14"]),
        "macd": float(last["macd"]),
        "macd_signal": float(last["macd_signal"]),
        "bb_upper": float(last["bb_upper"]),
        "bb_lower": float(last["bb_lower"]),
        "model_name": artifact["model_name"],
    }


def trade_levels(scored: dict[str, Any], capital: float | None, risk_pct: float) -> dict[str, Any] | None:
    """ATR-based stop/target and position size for BUY/SELL signals (informational)."""
    if scored["signal"] == "HOLD":
        return None
    close, atr = scored["close"], scored["atr"]
    sign = 1 if scored["signal"] == "BUY" else -1
    stop = close - sign * 1.5 * atr
    target = close + sign * 2.0 * atr
    levels: dict[str, Any] = {
        "side": "long" if sign == 1 else "short (intraday only in the Indian cash market)",
        "entry_reference": f"₹{close:,.2f}",
        "stop_loss": f"₹{stop:,.2f}",
        "target": f"₹{target:,.2f}",
        "rule": "stop = 1.5 x ATR(14), target = 2 x ATR(14)",
    }
    risk_per_share = 1.5 * atr
    if capital and risk_per_share > 0:
        qty = math.floor(capital * (risk_pct / 100.0) / risk_per_share)
        levels["position_size_shares"] = max(qty, 0)
        levels["capital_at_risk"] = f"₹{capital * risk_pct / 100.0:,.2f} ({risk_pct:g}% of capital)"
    return levels


def _raise_http(exc: Exception, context: str) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, DataError):
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    logger.exception("Unexpected error while %s", context)
    raise HTTPException(status_code=500, detail="Internal error, see server logs") from exc


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, Any]:
    info: dict[str, Any] = {
        "status": "ok" if model_artifact else "degraded",
        "model_loaded": model_artifact is not None,
        "model": model_artifact["model_name"] if model_artifact else None,
    }
    if model_artifact:
        info.update(
            thresholds=model_artifact["thresholds"],
            market_source=model_artifact.get("market_source"),
            trained_at=model_artifact.get("trained_at"),
            test_range=(model_artifact.get("split") or {}).get("test_range"),
        )
    return info


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    artifact = require_model()
    symbol = request.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=422, detail="Symbol is required")

    feature_columns = artifact["feature_columns"]
    missing = [c for c in feature_columns if c not in request.features]
    unexpected = [c for c in request.features if c not in feature_columns]
    if missing or unexpected:
        detail: dict[str, Any] = {}
        if missing:
            detail["missing_features"] = missing
        if unexpected:
            detail["unexpected_features"] = unexpected
        raise HTTPException(status_code=422, detail=detail)
    if not all(math.isfinite(request.features[c]) for c in feature_columns):
        raise HTTPException(status_code=422, detail="All feature values must be finite numbers")

    frame = pd.DataFrame([request.features], columns=feature_columns)
    prob_up = float(predict_proba_up(artifact, frame)[0])
    thresholds = artifact["thresholds"]
    return PredictionResponse(
        symbol=symbol,
        prediction="UP" if prob_up >= 0.5 else "DOWN",
        confidence=round(max(prob_up, 1 - prob_up) * 100, 1),
        probability_up=prob_up,
        signal=decision_label(prob_up, thresholds["buy"], thresholds["sell"]),
        model=artifact["model_name"],
    )


@app.get("/stock/analyze")
def analyze_stock(
    symbol: str = Query(default="RELIANCE"),
    capital: float | None = Query(default=None, gt=0, description="Optional capital in INR for position sizing"),
    risk_pct: float = Query(default=1.0, gt=0, le=5, description="Percent of capital risked per trade"),
):
    """Technical snapshot plus the model's next-trading-day view for one NSE/BSE stock."""
    try:
        s = score_symbol(symbol)
    except Exception as exc:
        _raise_http(exc, f"analysing {symbol}")

    p = s["probability_up"]
    direction = {"BUY": "BUY / UP", "SELL": "SELL / DOWN", "HOLD": "HOLD / NEUTRAL"}[s["signal"]]
    rsi = s["rsi"]
    return {
        "symbol": s["symbol"],
        "as_of": s["as_of"],
        "current_price": f"₹{s['live_price']:,.2f}",
        "change_pct": f"{s['change_pct']:+.2f}%",
        "prediction": direction,
        "signal": s["signal"],
        "probability_up": round(p, 4),
        "confidence": f"{int(round(max(p, 1 - p) * 100))}%",
        "risk": volatility_risk(s["atr_pct"]),
        "model_name": s["model_name"],
        "indicators": {
            "rsi": round(rsi, 2),
            "rsi_status": "Overbought" if rsi > 70 else ("Oversold" if rsi < 30 else "Neutral"),
            "macd": round(s["macd"], 2),
            "macd_signal": round(s["macd_signal"], 2),
            "macd_trend": "Bullish Crossover" if s["macd"] > s["macd_signal"] else "Bearish Crossover",
            "bb_upper": f"₹{s['bb_upper']:,.2f}",
            "bb_lower": f"₹{s['bb_lower']:,.2f}",
            "atr_pct": round(s["atr_pct"] * 100, 2),
        },
        "trade_levels": trade_levels(s, capital, risk_pct),
        "disclaimer": DISCLAIMER,
    }


@app.get("/predictions/batch")
def get_batch_predictions(
    symbols: list[str] = Query(default=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "TATAMOTORS.NS"])
):
    """Model view for several stocks. Symbols that fail are skipped."""
    require_model()
    if len(symbols) > MAX_SYMBOLS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_SYMBOLS} symbols per request")

    def work(sym: str) -> dict[str, Any] | None:
        try:
            s = score_symbol(sym)
        except Exception as exc:
            logger.warning("Skipping %s: %s", sym, getattr(exc, "message", exc))
            return None
        p = s["probability_up"]
        direction = {"BUY": "up", "SELL": "down", "HOLD": "hold"}[s["signal"]]
        return {
            "symbol": s["symbol"],
            "prediction": direction,
            "confidence": int(round(max(p, 1 - p) * 100)),
            "probability_up": round(p, 4),
            "risk": volatility_risk(s["atr_pct"]),
            "signal": {"up": "bullish", "down": "risk-off", "hold": "steady"}[direction],
            "as_of": s["as_of"],
        }

    with ThreadPoolExecutor(max_workers=5) as pool:
        return [r for r in pool.map(work, symbols) if r is not None]


def _price_and_change(ticker: str) -> tuple[float, float] | None:
    try:
        closes = fetch_history(ticker, "5d")["close"].dropna()
    except DataError as exc:
        logger.warning("No quote for %s: %s", ticker, exc.message)
        return None
    if closes.empty:
        return None
    price = float(closes.iloc[-1])
    change = (price - float(closes.iloc[-2])) / float(closes.iloc[-2]) * 100 if len(closes) >= 2 else 0.0
    return price, change


@app.get("/markets/overview")
def get_markets():
    """Live-ish market indices and FX rate (cached for a few minutes)."""
    tickers = {
        "NIFTY 50": "^NSEI",
        "SENSEX": "^BSESN",
        "NIFTY BANK": "^NSEBANK",
        "NIFTY IT": "^CNXIT",
        "USD/INR": "INR=X",
    }
    overview = []
    for name, sym in tickers.items():
        quote = _price_and_change(sym)
        if quote:
            overview.append({"name": name, "price": f"{quote[0]:,.2f}", "change": f"{quote[1]:+.2f}%"})
    return overview


@app.get("/watchlist/live")
def get_watchlist(
    symbols: list[str] = Query(default=["ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "ICICIBANK.NS"])
):
    """Latest close and daily change for a watchlist of Indian stocks."""
    if len(symbols) > MAX_SYMBOLS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_SYMBOLS} symbols per request")
    data = []
    for sym in symbols:
        try:
            ticker = format_ticker(sym)
        except DataError:
            continue
        quote = _price_and_change(ticker)
        if quote:
            data.append(
                {
                    "symbol": display_symbol(ticker),
                    "price": f"₹{quote[0]:,.2f}",
                    "change": f"{quote[1]:+.2f}%",
                    "trend": "Momentum" if quote[1] > 0 else "Cooling",
                }
            )
    return data


# DEMO DATA: these are made-up positions, not a real account. Replace with your own source.
USER_POSITIONS = [
    {"symbol": "RELIANCE.NS", "display": "RELIANCE", "qty": 50, "avg_cost": 2850.0},
    {"symbol": "TCS.NS", "display": "TCS", "qty": 35, "avg_cost": 3900.0},
    {"symbol": "INFY.NS", "display": "INFY", "qty": 80, "avg_cost": 1750.0},
    {"symbol": "HDFCBANK.NS", "display": "HDFCBANK", "qty": 100, "avg_cost": 1600.0},
    {"symbol": "TATAMOTORS.NS", "display": "TATAMOTORS", "qty": 120, "avg_cost": 920.0},
]


@app.get("/portfolio/summary")
def get_portfolio_summary():
    """INR portfolio metrics for the demo positions above."""
    holdings = []
    total_invested = 0.0
    current_value = 0.0

    for item in USER_POSITIONS:
        qty, avg_cost = item["qty"], item["avg_cost"]
        invested = qty * avg_cost
        quote = _price_and_change(item["symbol"])
        ltp = quote[0] if quote else avg_cost
        value = qty * ltp
        pnl = value - invested
        total_invested += invested
        current_value += value
        holdings.append(
            {
                "symbol": item["display"],
                "qty": qty,
                "avg_cost": round(avg_cost, 2),
                "ltp": round(ltp, 2),
                "value": round(value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl / invested * 100, 2) if invested > 0 else 0.0,
                "allocation": 0.0,
            }
        )

    for h in holdings:
        h["allocation"] = round(h["value"] / current_value * 100, 1) if current_value > 0 else 0.0

    gain = current_value - total_invested
    return {
        "demo": True,
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "gain": round(gain, 2),
        "roi": round(gain / total_invested * 100, 2) if total_invested > 0 else 0.0,
        "holdings": holdings,
    }
