"""FastAPI service for next-trading-day direction predictions on Indian Markets."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "next_day_direction.joblib"
MODEL_PATH = Path(os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH))


class PredictionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    features: dict[str, float]


class PredictionResponse(BaseModel):
    symbol: str
    prediction: str
    confidence: float
    probability_up: float
    model: str


app = FastAPI(title="SmartInvest AI ML API", version="1.0.0")

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model_artifact: dict[str, Any] | None = None


def load_model_artifact() -> dict[str, Any]:
    if not MODEL_PATH.is_file():
        raise RuntimeError(f"Model artifact not found: {MODEL_PATH}")
    artifact = joblib.load(MODEL_PATH)
    required_keys = {"model", "model_name", "feature_columns", "target_definition"}
    missing_keys = required_keys.difference(artifact)
    if missing_keys:
        raise RuntimeError(f"Model artifact is missing metadata: {', '.join(sorted(missing_keys))}")
    return artifact


@app.on_event("startup")
def initialize_model() -> None:
    global model_artifact
    model_artifact = load_model_artifact()


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Computes the 15 required technical indicators from OHLCV prices."""
    data = df.copy()
    data.columns = [col.lower() for col in data.columns]

    # Price & Volume changes
    data["price_change"] = data["close"].pct_change()
    data["volume_change"] = data["volume"].pct_change()

    # Moving averages
    data["sma_5"] = data["close"].rolling(window=5).mean()
    data["ema_12"] = data["close"].ewm(span=12, adjust=False).mean()

    # RSI (14)
    delta = data["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    data["rsi_14"] = 100 - (100 / (1 + rs))
    data["rsi_14"] = data["rsi_14"].fillna(50.0)

    # MACD (12, 26, 9)
    ema_26 = data["close"].ewm(span=26, adjust=False).mean()
    data["macd"] = data["ema_12"] - ema_26
    data["macd_signal"] = data["macd"].ewm(span=9, adjust=False).mean()

    # Bollinger Bands (20, 2 std)
    data["bb_middle"] = data["close"].rolling(window=20).mean()
    bb_std = data["close"].rolling(window=20).std()
    data["bb_upper"] = data["bb_middle"] + (2 * bb_std)
    data["bb_lower"] = data["bb_middle"] - (2 * bb_std)

    return data


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if model_artifact else "degraded",
        "model_loaded": model_artifact is not None,
        "model": model_artifact["model_name"] if model_artifact else None,
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    if model_artifact is None:
        raise HTTPException(status_code=503, detail="Prediction model is not loaded")

    symbol = request.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=422, detail="Symbol is required")

    feature_columns = model_artifact["feature_columns"]
    missing = [column for column in feature_columns if column not in request.features]
    unexpected = [column for column in request.features if column not in feature_columns]
    if missing or unexpected:
        detail = {}
        if missing:
            detail["missing_features"] = missing
        if unexpected:
            detail["unexpected_features"] = unexpected
        raise HTTPException(status_code=422, detail=detail)

    values = [request.features[column] for column in feature_columns]
    if not all(math.isfinite(value) for value in values):
        raise HTTPException(status_code=422, detail="All feature values must be finite numbers")

    frame = pd.DataFrame([request.features], columns=feature_columns)
    probability_up = float(model_artifact["model"].predict_proba(frame)[:, 1][0])
    prediction = "UP" if probability_up >= 0.5 else "DOWN"

    return PredictionResponse(
        symbol=symbol,
        prediction=prediction,
        confidence=round(max(probability_up, 1 - probability_up) * 100, 1),
        probability_up=probability_up,
        model=model_artifact["model_name"],
    )


@app.get("/stock/analyze")
def analyze_stock(symbol: str = Query(default="RELIANCE")):
    """Runs real-time technical analysis and ML prediction on any requested Indian stock."""
    if model_artifact is None:
        raise HTTPException(status_code=503, detail="ML Model not loaded")

    raw_symbol = symbol.strip().upper()
    formatted_ticker = raw_symbol if raw_symbol.endswith(".NS") or raw_symbol.endswith(".BO") else f"{raw_symbol}.NS"
    display_name = formatted_ticker.replace(".NS", "").replace(".BO", "")

    try:
        df = yf.download(formatted_ticker, period="60d", interval="1d", progress=False)
        if df.empty or len(df) < 30:
            raise HTTPException(status_code=404, detail=f"Stock data not found for {display_name}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        features_df = calculate_features(df)
        feature_cols = model_artifact["feature_columns"]
        latest_row = features_df.iloc[[-1]][feature_cols].copy().ffill().bfill()

        current_price = float(features_df["close"].iloc[-1])
        prev_price = float(features_df["close"].iloc[-2])
        change_pct = ((current_price - prev_price) / prev_price) * 100

        rsi = float(features_df["rsi_14"].iloc[-1])
        macd = float(features_df["macd"].iloc[-1])
        macd_sig = float(features_df["macd_signal"].iloc[-1])
        bb_upper = float(features_df["bb_upper"].iloc[-1])
        bb_lower = float(features_df["bb_lower"].iloc[-1])

        prob_up = float(model_artifact["model"].predict_proba(latest_row)[:, 1][0])
        pred_direction = "BUY / UP" if prob_up >= 0.55 else ("SELL / DOWN" if prob_up <= 0.45 else "HOLD / NEUTRAL")
        confidence = int(round(max(prob_up, 1 - prob_up) * 100))

        return {
            "symbol": display_name,
            "current_price": f"₹{current_price:,.2f}",
            "change_pct": f"{change_pct:+.2f}%",
            "prediction": pred_direction,
            "confidence": f"{confidence}%",
            "model_name": model_artifact["model_name"],
            "indicators": {
                "rsi": round(rsi, 2),
                "rsi_status": "Overbought" if rsi > 70 else ("Oversold" if rsi < 30 else "Neutral"),
                "macd": round(macd, 2),
                "macd_signal": round(macd_sig, 2),
                "macd_trend": "Bullish Crossover" if macd > macd_sig else "Bearish Crossover",
                "bb_upper": f"₹{bb_upper:,.2f}",
                "bb_lower": f"₹{bb_lower:,.2f}",
            },
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/predictions/batch")
def get_batch_predictions(
    symbols: list[str] = Query(default=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "TATAMOTORS.NS"])
):
    """Fetches real Indian stock prices, calculates indicators, and runs the ML model."""
    if model_artifact is None:
        raise HTTPException(status_code=503, detail="ML Model not loaded")

    results = []
    feature_cols = model_artifact["feature_columns"]

    for symbol in symbols:
        ticker = symbol.strip().upper()
        formatted_ticker = ticker if ticker.endswith(".NS") or ticker.endswith(".BO") else f"{ticker}.NS"
        display_symbol = formatted_ticker.replace(".NS", "").replace(".BO", "")

        try:
            df = yf.download(formatted_ticker, period="60d", interval="1d", progress=False)
            if df.empty or len(df) < 30:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            features_df = calculate_features(df)
            latest_row = features_df.iloc[[-1]][feature_cols].copy().ffill().bfill()

            prob_up = float(model_artifact["model"].predict_proba(latest_row)[:, 1][0])
            pred_direction = "up" if prob_up >= 0.55 else ("down" if prob_up <= 0.45 else "hold")
            confidence = int(round(max(prob_up, 1 - prob_up) * 100))

            risk = "low" if confidence >= 80 else ("medium" if confidence >= 65 else "high")
            if pred_direction == "up":
                signal = "bullish" if confidence >= 75 else "momentum"
            elif pred_direction == "down":
                signal = "risk-off"
            else:
                signal = "steady"

            results.append({
                "symbol": display_symbol,
                "prediction": pred_direction,
                "confidence": confidence,
                "risk": risk,
                "signal": signal,
            })
        except Exception as e:
            print(f"Error evaluating {ticker}: {e}")
            continue

    return results


@app.get("/markets/overview")
def get_markets():
    """Fetches live market indices and FX rates."""
    tickers = {
        "NIFTY 50": "^NSEI",
        "SENSEX": "^BSESN",
        "NIFTY BANK": "^NSEBANK",
        "NIFTY IT": "^CNXIT",
        "USD/INR": "INR=X",
    }
    overview = []
    for name, sym in tickers.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d")
            if hist.empty:
                continue

            closes = hist["Close"].dropna()
            if len(closes) >= 2:
                prev_close = float(closes.iloc[-2])
                curr_price = float(closes.iloc[-1])
                pct_change = ((curr_price - prev_close) / prev_close) * 100
            else:
                curr_price = float(closes.iloc[-1])
                pct_change = 0.0

            overview.append({
                "name": name,
                "price": f"{curr_price:,.2f}",
                "change": f"{pct_change:+.2f}%",
            })
        except Exception as e:
            print(f"Error fetching market {name}: {e}")
            continue

    return overview


@app.get("/watchlist/live")
def get_watchlist(
    symbols: list[str] = Query(default=["ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "ICICIBANK.NS"])
):
    """Fetches real-time prices in INR for Indian watchlist stocks."""
    data = []
    for sym in symbols:
        ticker = sym.strip().upper()
        formatted_ticker = ticker if ticker.endswith(".NS") or ticker.endswith(".BO") else f"{ticker}.NS"
        display_symbol = formatted_ticker.replace(".NS", "").replace(".BO", "")

        try:
            t = yf.Ticker(formatted_ticker)
            hist = t.history(period="5d")
            if hist.empty:
                continue

            closes = hist["Close"].dropna()
            if len(closes) >= 2:
                prev_close = float(closes.iloc[-2])
                curr_price = float(closes.iloc[-1])
                pct_change = ((curr_price - prev_close) / prev_close) * 100
            else:
                curr_price = float(closes.iloc[-1])
                pct_change = 0.0

            data.append({
                "symbol": display_symbol,
                "price": f"₹{curr_price:,.2f}",
                "change": f"{pct_change:+.2f}%",
                "trend": "Momentum" if pct_change > 0 else "Cooling",
            })
        except Exception as e:
            print(f"Error fetching watchlist {ticker}: {e}")
            continue

    return data


# Tracked Indian NSE stock positions (Realistic buy costs in INR)
USER_POSITIONS = [
    {"symbol": "RELIANCE.NS", "display": "RELIANCE", "qty": 50, "avg_cost": 2850.0},
    {"symbol": "TCS.NS", "display": "TCS", "qty": 35, "avg_cost": 3900.0},
    {"symbol": "INFY.NS", "display": "INFY", "qty": 80, "avg_cost": 1750.0},
    {"symbol": "HDFCBANK.NS", "display": "HDFCBANK", "qty": 100, "avg_cost": 1600.0},
    {"symbol": "TATAMOTORS.NS", "display": "TATAMOTORS", "qty": 120, "avg_cost": 920.0},
]


@app.get("/portfolio/summary")
def get_portfolio_summary():
    """Calculates live INR portfolio metrics, P&L, and asset allocations."""
    holdings = []
    total_invested = 0.0
    current_portfolio_value = 0.0

    for item in USER_POSITIONS:
        sym = item["symbol"]
        display_sym = item["display"]
        qty = item["qty"]
        avg_cost = item["avg_cost"]
        invested = qty * avg_cost

        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="2d")
            closes = hist["Close"].dropna()
            ltp = float(closes.iloc[-1]) if not closes.empty else avg_cost
        except Exception:
            ltp = avg_cost

        curr_val = qty * ltp
        pnl = curr_val - invested
        pnl_pct = (pnl / invested) * 100 if invested > 0 else 0.0

        total_invested += invested
        current_portfolio_value += curr_val

        holdings.append({
            "symbol": display_sym,
            "qty": qty,
            "avg_cost": round(avg_cost, 2),
            "ltp": round(ltp, 2),
            "value": round(curr_val, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "allocation": 0.0,
        })

    for h in holdings:
        h["allocation"] = round((h["value"] / current_portfolio_value * 100), 1) if current_portfolio_value > 0 else 0.0

    total_gain = current_portfolio_value - total_invested
    roi = (total_gain / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_portfolio_value, 2),
        "gain": round(total_gain, 2),
        "roi": round(roi, 2),
        "holdings": holdings,
    }