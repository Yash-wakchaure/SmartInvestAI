# Phase 6-7: ML Data Pipeline and Model Training

The training command compares Logistic Regression, Random Forest, and XGBoost
when XGBoost is installed. It reports accuracy, precision, recall, F1, ROC-AUC,
and a confusion matrix for each comparison. The primary model is selected by
validation ROC-AUC, with validation F1 as the tie-breaker.

## Target contract

For each ticker and trading date `t`:

```text
target(t) = 1 if close(t + 1) > close(t), otherwise 0
```

The target is created with a same-ticker `close.shift(-1)`. The final row for
each ticker has no known next-day close and is removed. This definition must be
used unchanged by preprocessing, training, evaluation, and inference.

## Features

The pipeline uses only values available at date `t`:

- `open`, `high`, `low`, `close`, `volume`
- `price_change`, `volume_change`
- `sma_5`, `ema_12`
- `rsi_14`
- `macd`, `macd_signal`
- `bb_middle`, `bb_upper`, `bb_lower`

Rolling and exponential indicators are calculated separately for each ticker.
The source file's precomputed indicator columns are intentionally ignored so
their calculation and timing cannot introduce leakage.

## Split policy

Rows are sorted by `ticker` and `date`, then each ticker is split independently:

- first 70%: training
- next 15%: validation
- final 15%: test

No random shuffling is used. Feature calculations happen before splitting, but
each feature at date `t` uses only dates at or before `t`; the target uses only
the next close and is never included in the feature matrix.

Run from the `SmartInvestAI` directory:

```text
python ml/pipeline.py --input ../Datasets/infolimpioavanzadoTarget.csv/infolimpioavanzadoTarget.csv
```

The selected model is refit on the training and validation rows and saved to
`ml/artifacts/next_day_direction.joblib`. It contains the fitted estimator,
feature list, and target definition, so prediction requests do not retrain it.
Use `ml/predict.py` to load that artifact and call `predict_direction` with a
DataFrame containing the same engineered feature columns.

## FastAPI service

Start the API from the `SmartInvestAI` directory:

```text
uvicorn ml.api:app --host 0.0.0.0 --port 8000
```

The service loads the saved artifact once at startup. It exposes `GET /health`
and `POST /predict`. The prediction request must contain every feature listed
in `feature_columns` above; extra or missing features are rejected so the API
cannot silently send an incompatible vector to the model.

## Node integration and decision support

Node calls the Python service through `ML_API_URL` (default:
`http://127.0.0.1:8000`) at `POST /api/predictions`. Node does not create or
alter the model prediction. It converts the model confidence to a percentage
for display and preserves the probability as `modelProbability`.

The current transparent decision rules are:

- `BUY`: probability of UP is at least `0.65`
- `SELL`: probability of UP is at most `0.35`
- `HOLD`: otherwise
- `HIGH` risk: confidence below `0.55`, absolute price change at least `5%`,
  or Bollinger-band width at least `15%` of its middle value
- `MEDIUM` risk: confidence below `0.65`, absolute price change at least `2%`,
  or Bollinger-band width at least `8%` of its middle value
- `LOW` risk: none of the above conditions apply

These signals are decision-support labels, not guarantees or financial advice.
`modelProbability` means the trained model's estimated class probability; it
is not the probability of making a profit.