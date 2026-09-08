"""FastAPI service for next-trading-day direction predictions."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
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
        confidence=max(probability_up, 1 - probability_up),
        probability_up=probability_up,
        model=model_artifact["model_name"],
    )