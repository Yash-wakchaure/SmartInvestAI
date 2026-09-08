"""Leakage-safe baseline pipeline for next-trading-day direction prediction."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline

try:
    from xgboost import XGBClassifier
except ImportError:
    XGBClassifier = None


BASE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]
FEATURE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "price_change",
    "volume_change",
    "sma_5",
    "ema_12",
    "rsi_14",
    "macd",
    "macd_signal",
    "bb_middle",
    "bb_upper",
    "bb_lower",
]
TARGET_COLUMN = "target"


def load_market_data(input_path: str | Path) -> pd.DataFrame:
    data = pd.read_csv(input_path, usecols=BASE_COLUMNS, parse_dates=["date"])
    data["ticker"] = data["ticker"].astype(str).str.upper().str.strip()
    numeric_columns = [column for column in BASE_COLUMNS if column not in {"date", "ticker"}]
    data[numeric_columns] = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=BASE_COLUMNS).sort_values(["ticker", "date"])
    return data.reset_index(drop=True)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    losses = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    relative_strength = gains / losses.replace(0, np.nan)
    return 100 - (100 / (1 + relative_strength))


def add_features_and_target(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    grouped = result.groupby("ticker", group_keys=False)

    result["price_change"] = grouped["close"].pct_change()
    result["volume_change"] = grouped["volume"].pct_change()
    result["sma_5"] = grouped["close"].transform(lambda values: values.rolling(5, min_periods=5).mean())
    result["ema_12"] = grouped["close"].transform(lambda values: values.ewm(span=12, adjust=False).mean())
    result["rsi_14"] = grouped["close"].transform(_rsi)

    result["ema_26"] = grouped["close"].transform(lambda values: values.ewm(span=26, adjust=False).mean())
    result["macd"] = result["ema_12"] - result["ema_26"]
    result["macd_signal"] = result.groupby("ticker")["macd"].transform(
        lambda values: values.ewm(span=9, adjust=False).mean()
    )

    result["bb_middle"] = grouped["close"].transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    rolling_std = grouped["close"].transform(
        lambda values: values.rolling(20, min_periods=20).std()
    )
    result["bb_upper"] = result["bb_middle"] + 2 * rolling_std
    result["bb_lower"] = result["bb_middle"] - 2 * rolling_std

    next_close = grouped["close"].shift(-1)
    result[TARGET_COLUMN] = (next_close > result["close"]).astype("Int64")
    result.loc[next_close.isna(), TARGET_COLUMN] = pd.NA
    result[FEATURE_COLUMNS] = result[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    return result.drop(columns=["ema_26"]).dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN]).reset_index(drop=True)


def chronological_split(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_parts = []
    validation_parts = []
    test_parts = []
    for _, ticker_data in data.groupby("ticker", sort=False):
        ticker_data = ticker_data.sort_values("date")
        train_end = int(len(ticker_data) * 0.70)
        validation_end = train_end + int(len(ticker_data) * 0.15)
        train_parts.append(ticker_data.iloc[:train_end])
        validation_parts.append(ticker_data.iloc[train_end:validation_end])
        test_parts.append(ticker_data.iloc[validation_end:])

    return (
        pd.concat(train_parts).sort_values(["ticker", "date"]).reset_index(drop=True),
        pd.concat(validation_parts).sort_values(["ticker", "date"]).reset_index(drop=True),
        pd.concat(test_parts).sort_values(["ticker", "date"]).reset_index(drop=True),
    )


def build_models() -> dict[str, object]:
    models = {
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="median"),
            LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42,
            class_weight="balanced",
            n_jobs=-1,
        ),
    }
    if XGBClassifier is not None:
        models["xgboost"] = XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )
    return models


def evaluate_model(model: object, frame: pd.DataFrame) -> dict[str, object]:
    probabilities = model.predict_proba(frame[FEATURE_COLUMNS])[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    target = frame[TARGET_COLUMN].astype(int)
    return {
        "accuracy": accuracy_score(target, predictions),
        "precision": precision_score(target, predictions, zero_division=0),
        "recall": recall_score(target, predictions, zero_division=0),
        "f1": f1_score(target, predictions, zero_division=0),
        "roc_auc": roc_auc_score(target, probabilities),
        "confusion_matrix": confusion_matrix(target, predictions).tolist(),
    }


def train_and_evaluate(data: pd.DataFrame, model_path: str | Path) -> dict[str, object]:
    train, validation, test = chronological_split(data)
    validation_results = {}
    models = build_models()
    for name, model in models.items():
        model.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN].astype(int))
        validation_results[name] = evaluate_model(model, validation)

    selected_name = max(
        validation_results,
        key=lambda name: (validation_results[name]["roc_auc"], validation_results[name]["f1"]),
    )
    selected_model = build_models()[selected_name]
    combined = pd.concat([train, validation], ignore_index=True)
    selected_model.fit(combined[FEATURE_COLUMNS], combined[TARGET_COLUMN].astype(int))
    test_results = evaluate_model(selected_model, test)
    artifact = {
        "model": selected_model,
        "model_name": selected_name,
        "feature_columns": FEATURE_COLUMNS,
        "target_definition": "1 if same-ticker next close is greater than current close, otherwise 0",
        "interval": "next trading day",
    }
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)

    print(f"rows: train={len(train)}, validation={len(validation)}, test={len(test)}")
    for name, metrics in validation_results.items():
        print(f"{name} validation: {metrics}")
    print(f"selected model: {selected_name}")
    print(f"selected model test: {test_results}")
    print(f"saved model: {model_path}")
    return {
        "validation": validation_results,
        "selected_model": selected_name,
        "test": test_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to the OHLCV CSV file")
    parser.add_argument("--model-output", default="ml/artifacts/next_day_direction.joblib")
    args = parser.parse_args()
    data = add_features_and_target(load_market_data(args.input))
    if XGBClassifier is None:
        print("xgboost unavailable: install xgboost to include that comparison")
    train_and_evaluate(data, args.model_output)


if __name__ == "__main__":
    main()