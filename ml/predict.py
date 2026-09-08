"""Load the saved Phase 7 model and predict next-day direction."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd


def load_model(model_path: str | Path = "ml/artifacts/next_day_direction.joblib") -> dict:
    return joblib.load(model_path)


def predict_direction(features: pd.DataFrame, model_path: str | Path = "ml/artifacts/next_day_direction.joblib") -> pd.DataFrame:
    artifact = load_model(model_path)
    missing = [column for column in artifact["feature_columns"] if column not in features.columns]
    if missing:
        raise ValueError(f"Missing model features: {', '.join(missing)}")

    probabilities = artifact["model"].predict_proba(features[artifact["feature_columns"]])[:, 1]
    return pd.DataFrame(
        {
            "prediction": (probabilities >= 0.5).astype(int),
            "probability_up": probabilities,
            "model": artifact["model_name"],
        },
        index=features.index,
    )