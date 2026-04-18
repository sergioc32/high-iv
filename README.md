# High IV Options Screener

An automated options screening and trade-tracking tool that identifies high implied volatility stocks, evaluates put credit spread opportunities, tracks live open positions, and reconciles closed trades against Tastytrade order history.

## Features

- **IV Rank Screening**: Filters stocks by implied volatility rank to find elevated IV environments.
- **Watchlist Integration**: Pulls symbols from Tastytrade public watchlists such as S&P 500, NASDAQ 100, High Options Volume, and tasty IVR.
- **Spread Analysis**: Evaluates put credit spreads using delta, DTE, credit quality, liquidity, and risk/reward constraints.
- **EV-Ranked Candidates**: Scores evaluated spreads by EV and selects the best candidate per symbol/expiration.
- **Candidate Logging**: Writes evaluated spread candidates to `opportunities/opportunity_candidates.csv`.
- **Rejection Tracking**: Writes symbol-level rejection counters to `rejections/rejections_tracking.csv`.
- **Live Position Snapshotting**: Builds `trades/trades_open.csv` directly from current account positions.
- **Actual Close Reconciliation**: Newly detected closed trades are matched against recent filled orders so `trades/trades_closed.csv` can store broker-confirmed close values alongside estimated values.
- **Historical Backfill Tool**: One-off script can backfill older closed trades using paginated account order history.
- **Weekly Snapshots**: Creates weekly JSON snapshots of trades and strategy configuration.
- **Analytics Suite**: Offline analysis scripts for data quality checks, diagnostics, rankings, and reporting.

## Prerequisites

- Python 3.10 or higher
- Tastytrade account with API access
- Virtual environment recommended

## Installation

1. Change into the project directory:
```bash
cd c:\Users\sergi\development\highIV
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
```bash
venv\Scripts\activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create a `.env` file in the project root with your credentials and OAuth settings.

## Configuration

Edit `config.py` to customize screening, tracking, and reconciliation behavior.

### Core Strategy Parameters

- `IV_RANK_THRESHOLD`
- `TARGET_DTE`
- `TARGET_DELTA`
- `LONG_PUT_DELTA`
- `PREFERRED_SPREAD_WIDTH`
- `FALLBACK_SPREAD_WIDTH`
- `MAX_STRIKE_INCREMENT`
- `MAX_RISK_REWARD_RATIO`
- `TARGET_PROFIT_PCT`
- `DTE_TOLERANCE`

### Skew and Candidate Selection

- `SKEW_WINDOW_OTM`
- `SKEW_WINDOW_ITM`
- `MIN_SCORE_IMPROVEMENT_PCT`

### Cache and API Tuning

- `CACHE_DIR`
- `CACHE_TTL_SESSION`
- `CACHE_TTL_WATCHLIST`
- `CACHE_TTL_EXPIRATIONS`
- `CACHE_TTL_OPTION_CHAIN`
- `CACHE_TTL_MARKET_METRICS`
- `CACHE_TTL_QUOTES`
- `CACHE_TTL_OPTION_QUOTES`
- `CHAIN_FETCH_DELAY`
- `OPTION_QUOTE_BATCH_SIZE`
- `EQUITY_QUOTE_BATCH_SIZE`

### Closed-Trade Reconciliation

- `ORDER_HISTORY_LOOKBACK_DAYS`: recent order window for normal closed-trade reconciliation.
- `ORDER_HISTORY_MAX_PAGES`: default page cap for lightweight recent order retrieval during normal syncs.

## Usage

Run the full screener:
```bash
python main.py
```

### Command Line Options

Clear all cached data:
```bash
python main.py --clear-cache-all
```

Fresh day run:
```bash
python main.py --fresh-day
```
Clears stale cache entries from prior days, syncs live positions, then continues into the screener.

Sync positions only:
```bash
python main.py --sync-positions
```
Fetches current account positions, parses spreads, displays alerts, and updates `trades/trades_open.csv`.

Weekly snapshot backfill:
```bash
python main.py --weekly-snapshot
```
Creates any missing completed-week snapshot files under `snapshots/`.

### Historical Closed-Trade Backfill

One-off tool to backfill actual close values into historical rows:

```bash
python backfill_closed_trade_actuals.py --lookback-days 180 --date-buffer-days 14
```

Behavior:
- reads `trades/trades_closed.csv`
- paginates through filled account orders
- matches historical spread closes by symbol, expiration, and strikes
- prefers leg-fill-derived net close values over order limit price
- updates canonical `close_debit`
- preserves `close_debit_estimated`
- writes `close_debit_actual`
- recalculates dependent P/L metrics
- creates `trades/trades_closed.csv.bak` by default before writing

## Trade Tracking Model

### Open Trades

`trades/trades_open.csv` is sourced from:
- `accounts/{account}/positions`
- parsed through `TastytradeAPI.parse_option_spreads(...)`

This file is the live snapshot of currently held spreads.

### Closed Trades

`trades/trades_closed.csv` is built in two stages:

1. A trade is considered newly closed when it existed in the prior open snapshot but no longer appears in the current open snapshot.
2. The system then attempts to reconcile that disappeared trade against recent filled account orders.

Closed-trade value fields:
- `close_debit`: canonical best-known close value
- `close_debit_estimated`: last known estimate from the open-position snapshot
- `close_debit_actual`: broker-confirmed close value when reconciliation succeeds

Actual close value precedence:
1. leg-fill-derived net close value
2. order-level `price` with `price-effect`
3. estimate fallback

## Analytics Commands

Build the analysis dataset:
```bash
python analysis/build_analysis_dataset.py
```

Run the data quality audit:
```bash
python analysis/data_quality_audit.py
```

Run rejection diagnostics:
```bash
python analysis/rejection_diagnostics.py
```

Rank selected opportunities from the latest run:
```bash
python analysis/ranking_engine.py
```

Generate weekly report artifacts:
```bash
python analysis/run_weekly_pipeline.py
python analysis/run_weekly_closeout.py
```

## Output Files

Primary runtime outputs:
- `opportunities/opportunities_YYYYMMDD_HHMMSS[_indicative].csv`
- `opportunities/opportunity_candidates.csv`
- `rejections/rejections_tracking.csv`
- `trades/trades_open.csv`
- `trades/trades_closed.csv`
- `snapshots/snapshot_*.json`

Analytics outputs:
- `analysis/analysis_dataset.csv`
- `analysis/reports/*`

## Project Structure

```text
highIV/
+-- api/
¦   +-- tastytrade.py
+-- screener/
¦   +-- iv_screener.py
¦   +-- spread_analyzer.py
¦   +-- spread_logging.py
¦   +-- spread_models.py
¦   +-- spread_scoring.py
+-- services/
¦   +-- closed_trade_reconciliation_service.py
¦   +-- persistence_service.py
¦   +-- position_sync_service.py
¦   +-- run_models.py
¦   +-- screener_run_service.py
¦   +-- snapshot_service.py
+-- analysis/
+-- opportunities/
+-- rejections/
+-- snapshots/
+-- trades/
+-- docs/
¦   +-- ARCHITECTURE.md
+-- backfill_closed_trade_actuals.py
+-- config.py
+-- main.py
+-- README.md
```

## API Endpoints Used

- `/public-watchlists/{name}`
- `/market-metrics`
- `/market-data/by-type?equity=`
- `/option-chains/{symbol}/nested`
- `/market-data/by-type?equity-option=`
- `/accounts/{account}/positions`
- `/accounts/{account}/orders`

## Notes

- `main.py` is now a thin composition root that delegates to focused service modules.
- Normal closed-trade reconciliation uses lightweight paginated order retrieval.
- Historical backfills can request deeper pagination without affecting normal sync behavior.
- All prices and strikes are in USD, with spread economics generally stored in contract-dollar terms such as `0.50 -> 50.0`.

## Support

For API behavior and endpoint documentation, refer to:
https://developer.tastytrade.com/
