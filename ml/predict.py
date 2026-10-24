"""Load the saved model and predict next-trading-day direction.

Library use:
    from ml.predict import predict_direction, predict_from_ohlcv

Command line (needs a stock OHLCV csv and a market-index csv, both with a date column):
    python ml/predict.py --ohlcv-csv RELIANCE.csv --index-csv NIFTY.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

try:
    from .common import compute_feature_frame, decision_label, normalize_ohlcv, predict_proba_up
except ImportError:  # pragma: no cover
    from common import compute_feature_frame, decision_label, normalize_ohlcv, predict_proba_up  # type: ignore

DEFAULT_MODEL_PATH = "ml/artifacts/next_day_direction.joblib"


def load_model(model_path: str | Path = DEFAULT_MODEL_PATH) -> dict:
    artifact = joblib.load(model_path)
    required = {"model", "model_name", "feature_columns", "target_definition", "thresholds"}
    missing = required.difference(artifact)
    if missing:
        raise ValueError(
            f"Model artifact is missing {sorted(missing)}. It was probably trained with an older "
            "pipeline - retrain with `python ml/pipeline.py --input <csv>`."
        )
    return artifact


def predict_direction(features: pd.DataFrame, model_path: str | Path = DEFAULT_MODEL_PATH, artifact: dict | None = None) -> pd.DataFrame:
    """Predict from a DataFrame that already holds the engineered feature columns."""
    artifact = artifact or load_model(model_path)
    missing = [c for c in artifact["feature_columns"] if c not in features.columns]
    if missing:
        raise ValueError(f"Missing model features: {', '.join(missing)}")
    if features[artifact["feature_columns"]].isna().any().any():
        raise ValueError("Feature values contain NaN; compute them from enough history first")

    probabilities = predict_proba_up(artifact, features)
    thresholds = artifact["thresholds"]
    return pd.DataFrame(
        {
            "prediction": (probabilities >= 0.5).astype(int),
            "probability_up": probabilities,
            "signal": [decision_label(p, thresholds["buy"], thresholds["sell"]) for p in probabilities],
            "model": artifact["model_name"],
        },
        index=features.index,
    )


def predict_from_ohlcv(
    ohlcv: pd.DataFrame,
    market_close: pd.Series,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    artifact: dict | None = None,
) -> pd.DataFrame:
    """Compute features from raw daily bars and predict for the day after the last bar."""
    artifact = artifact or load_model(model_path)
    bars = normalize_ohlcv(ohlcv)
    frame = compute_feature_frame(bars, market_close)
    latest = frame.iloc[[-1]]
    return predict_direction(latest, artifact=artifact)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--ohlcv-csv", required=True, help="date,open,high,low,close,volume (>= 120 daily rows)")
    parser.add_argument("--index-csv", required=True, help="date,close of the market index")
    args = parser.parse_args()

    def read(path: str) -> pd.DataFrame:
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        return df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])

    stock = read(args.ohlcv_csv)
    index = read(args.index_csv)["close"]
    result = predict_from_ohlcv(stock, index, args.model)
    print(result.to_string())


if __name__ == "__main__":
    main()
