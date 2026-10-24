# SmartInvest AI: ML pipeline, backtest and API

Predicts whether a stock's **next close will be above today's close**. Realistic accuracy for this
problem is **50-56%**. The goal of this code is a model you can evaluate honestly, not a big
accuracy number. If a run shows 60%+, suspect leakage first.

## Quick start

Run everything from the `SmartInvestAI` directory.

```text
pip install -r ml/requirements.txt

# 1. train (also writes metrics.json and test_predictions.csv next to the model)
python ml/pipeline.py --input path/to/data.csv

# 2. backtest the held-out test period, with Indian costs
python ml/backtest.py --predictions ml/artifacts/test_predictions.csv

# 3. serve
uvicorn ml.api:app --host 0.0.0.0 --port 8000

# tests (pip install -r ml/requirements-dev.txt)
python -m pytest ml/tests
```

Useful training options: `--train-end 2022-01-01 --val-end 2023-07-01` (explicit split dates),
`--sample-tickers 50` (fast experiments), `--market-source csv --index-csv nifty.csv` or
`--market-source yfinance --index-ticker ^NSEI` (real index for market features),
`--refit-all` (after evaluation, refit the chosen model on all rows).

## Data requirements

CSV with columns `date, ticker, open, high, low, close, volume`. Other columns are ignored.

* Prices should be **split/dividend adjusted**, like Yahoo's `auto_adjust=True`, which the API uses.
  Rows next to moves above 50% are dropped as probable bad data.
* Your repo stores CSVs in **Git LFS**. If the file starts with `version https://git-lfs...` it is only
  a pointer; the pipeline detects this and tells you to run `git lfs pull`.
* **Use data from the market you serve.** The API scores NSE stocks, so train on Indian data
  (or accept that the model is applied to a market it never saw).

## What changed and why

| Problem in the old version | Fix |
|---|---|
| Per-ticker 70/15/15 row split: different tickers' test periods overlapped other tickers' training periods | **Global calendar-date split** plus a 1-day embargo before each cutoff |
| Raw prices (`open/high/low/close`, `sma_5`, `bb_*`) as features, so the model could learn which stock it was looking at | **Scale-free features only** (returns, ratios, %B, ATR%). A test checks that multiplying prices by 10 changes nothing |
| No baseline | Every metric is shown against an **always-predict-majority-class baseline**, with a p-value |
| One split only | **Walk-forward** folds on the development period, **per-ticker** results |
| No market context | Index return/volatility and **relative strength vs the market** |
| Uncalibrated "confidence" | **Platt-calibrated probabilities**, fitted on validation only |
| Features computed differently in `pipeline.py` and `api.py` | One shared `common.py` used by training, API and `predict.py` |
| API used 60 days of history, today's unfinished bar, RSI=50 when there were no losses | ~1 year of history, **incomplete bar dropped** during market hours, RSI=100 in that case |
| Three different BUY/SELL thresholds | **One threshold**, stored in the model artifact (`thresholds`) |
| "Risk" derived from model confidence | **Volatility (ATR%) based risk**, ATR stop-loss/target and position sizing |

## Features (all causal and scale-free)

* returns: `ret_1, ret_3, ret_5, ret_10`
* day-trader candle features: `gap_pct` (overnight gap), `range_pct`, `body_pct`, `close_pos` (where the day closed in its range)
* volatility: `atr_pct` (Wilder ATR / close), `vol_20`
* volume: `rel_volume` (log volume vs 20-day average), `volume_chg`
* trend/oscillators: `rsi_14` (Wilder), `macd_pct`, `macd_hist_pct`, `pct_b`, `bb_width`, `close_vs_sma5/sma20/ema12`
* range position: `dist_high_20`, `dist_low_20`
* market context: `mkt_ret_1, mkt_ret_5, mkt_vol_20, rel_strength_5`

Market features use the equal-weighted average of the tickers in your CSV by default
(`--market-source proxy`). **The API uses `^NSEI`.** For an exact train/serve match, train with
`--market-source yfinance` or `--market-source csv` using NIFTY data. The artifact records which one was used
(`/health` shows it).

## Evaluation protocol

1. Train several models on the **train** period. Pick the one with the best **validation** ROC-AUC.
2. Calibrate its probabilities on **validation**.
3. Score the untouched **test** period once. This is the number to report.
4. Walk-forward folds (train+validation only) show whether the result is stable or luck.
5. The saved model is the one that was tested. `--refit-all` retrains it on all rows afterwards;
   the reported metrics still come from the un-refit model.

What to look at in the output:

* **accuracy vs baseline**: the edge is the difference. 0.5 to 2 points is realistic.
* **ROC-AUC**: 0.50 means no signal. 0.52-0.55 is already a good result for daily direction.
* **strong signals**: accuracy only on days when the model is at least 55/60/65% sure, and how many days that is.
  High accuracy on very few days is noise; check `n`.
* **walk-forward**: how many folds beat the baseline? Mean ± std.
* The p-value treats rows as independent, but stocks move together on the same day, so it is optimistic.

On pure random-walk data the tests require AUC within 0.44-0.56. A model that "finds" more than that on
random data has leaked.

## Backtest and costs

`ml/backtest.py` trades the test-period signals: long when `P(up) >= threshold`, equal weight, idle cash earns 0,
compared with equal-weight buy-and-hold of the same stocks.

* `--execution close` (default): enter at today's close, exit at tomorrow's close (matches the target).
  Positions held on consecutive signals pay costs only once. This is treated as a **delivery** trade.
* `--execution open`: intraday, tomorrow's open to close. `--allow-short` is allowed only here.
* Costs per side (approximate, **check your broker's charge calculator**): delivery STT 0.1% on both sides,
  stamp duty, exchange and SEBI fees, GST on fees, plus `--slippage-bps` (default 5). Delivery round trip is
  roughly 0.3% all-in, which is far larger than a 1-2 point accuracy edge. That is normal, and it is the reason
  most next-day direction models do not survive costs.
* The headline threshold is fixed before the run. The sweep table is informational; choosing the best row on the
  test period would be overfitting to the test set.

## API

All previous endpoints and field names still work. New fields are additive.

* `GET /health`: model, thresholds, market source, training date, test range
* `POST /predict`: body `{symbol, features}` with the features in `feature_columns`. Returns `prediction` (UP/DOWN at 0.5),
  `signal` (BUY/SELL/HOLD from the thresholds), `probability_up`, `confidence`
* `GET /stock/analyze?symbol=RELIANCE&capital=500000&risk_pct=1`: indicators, `as_of` date of the last complete bar,
  `probability_up`, volatility `risk`, and (for BUY/SELL) `trade_levels` with ATR stop, target and share count
* `GET /predictions/batch?symbols=TCS.NS&symbols=INFY.NS`: parallel, cached, failed symbols are skipped
* `GET /markets/overview`, `GET /watchlist/live`, `GET /portfolio/summary` (the portfolio is **demo data**, flagged `"demo": true`)

`confidence` is the model's probability for the predicted direction (`max(p, 1-p)`). It is **not** certainty
and not the chance of making a profit. A daily-direction model will rarely exceed 60%.

Settings via environment variables: `MODEL_PATH`, `CORS_ORIGINS` (comma separated), `INDEX_TICKER`,
`DATA_CACHE_SECONDS`, `LOG_LEVEL`.

### Node integration

Node calls the Python service at `ML_API_URL` (default `http://127.0.0.1:8000`). **Update the decision rules there:**
the old README used BUY at 0.65 and SELL at 0.35, but calibrated next-day probabilities almost never reach 0.65, so
that rule would never fire. Use the `signal` field returned by the API (thresholds come from the model artifact,
default 0.55 / 0.45, change with `--buy-threshold`) instead of recomputing them in Node. Do not reuse the old
confidence-based risk rules.

## Limitations (say these in interviews)

* Next-day direction is close to a coin flip; the edge, if any, is small and costs can remove it.
* Equal-weight, one test period, no market-impact model. A positive backtest is evidence, not proof.
* Features are technical only (no news, fundamentals, order flow).
* The market proxy used in training differs slightly from `^NSEI` unless you train with a real index.
* Yahoo data can be delayed, adjusted late, or rate limited; the API caches for 5 minutes.
* Educational project, not financial advice.
