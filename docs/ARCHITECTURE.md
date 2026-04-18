# Architecture Overview

This document outlines the current design and architecture of the High IV Options Screener application.

## High-Level Architecture

The application is organized around a thin entrypoint and focused service modules.

```text
main.py
  +- SnapshotService
  +- PositionSyncService
  ¦   +- ClosedTradeReconciliationService
  +- ScreenerRunService
  ¦   +- IVScreener
  ¦   +- SpreadAnalyzer
  ¦   +- PersistenceService
  +- SnapshotService

TastytradeAPI
  +- watchlists
  +- market metrics
  +- equity quotes
  +- option chains
  +- option quotes
  +- account positions
  +- paginated account orders
```

## Main Architectural Idea

The codebase now separates responsibilities into four main layers:

1. `main.py`
   - CLI parsing
   - top-level command dispatch
   - authentication bootstrap
   - high-level runtime flow

2. `api/`
   - Tastytrade HTTP interactions
   - response parsing and normalization
   - pagination for account orders

3. `services/`
   - application workflows and persistence boundaries
   - position sync and closed-trade reconciliation
   - weekly snapshots
   - screener orchestration

4. `screener/` and `analysis/`
   - domain-specific strategy logic
   - offline analytics and reporting

## Components

### 1. Main Application (`main.py`)

**Responsibility**: Thin composition root for command routing and top-level orchestration.

**Responsibilities kept in `main.py`:**
- parse CLI flags
- choose between cache clearing, snapshotting, sync-only, and full screener modes
- authenticate the API client
- display top-level summaries and status banners
- delegate real work to services

## 2. API Layer (`api/tastytrade.py`)

**Responsibility**: Encapsulates all Tastytrade API interactions.

**Important methods:**
- `authenticate()`
- `get_watchlist()`
- `get_market_metrics()`
- `get_quotes_batch()`
- `get_option_expirations()`
- `get_option_chain()`
- `get_option_quotes()`
- `get_account_positions()`
- `get_account_orders()`

### Order History Retrieval Modes

`get_account_orders()` supports two usage patterns:

- **Lightweight mode**
  - used by normal sync/reconciliation
  - bounded by `ORDER_HISTORY_MAX_PAGES`
  - intended to fetch only recent filled orders for newly closed trades

- **Deep pagination mode**
  - used by the one-off historical backfill tool
  - can disable page caps and walk until the age cutoff is reached
  - intended for older closed-trade recovery

## 3. Services Layer (`services/`)

### 3.1 Position Sync Service (`position_sync_service.py`)

**Responsibility**: Build the live open-trade snapshot and detect newly closed trades.

**Flow:**
1. call `get_account_positions()`
2. call `parse_option_spreads()`
3. enrich rows with current quotes
4. compute exit signals and display-ready views
5. write `trades/trades_open.csv`
6. compare prior open snapshot against current open snapshot
7. identify disappeared `trade_id` values
8. reconcile new closures against recent filled orders
9. append rows to `trades/trades_closed.csv`

### 3.2 Closed Trade Reconciliation Service (`closed_trade_reconciliation_service.py`)

**Responsibility**: Match newly disappeared spreads to actual order fills.

**Current first-pass matching behavior:**
- exact underlying symbol match
- exact short-leg symbol with `Buy to Close`
- exact long-leg symbol with `Sell to Close`
- only `Filled` orders

**Actual close source precedence:**
1. leg-fill-derived net close value
2. order-level `price` with `price-effect`
3. fallback to estimated value from prior open snapshot

**Result fields produced downstream:**
- `close_debit`
- `close_debit_estimated`
- `close_debit_actual`
- `actual_exit_found`
- `exit_price_source`
- `close_fill_timestamp`
- `close_order_id`
- `match_confidence`

### 3.3 Snapshot Service (`snapshot_service.py`)

**Responsibility**: Create and backfill weekly state snapshots.

**Writes:**
- `snapshots/snapshot_<week>.json`

### 3.4 Screener Run Service (`screener_run_service.py`)

**Responsibility**: Orchestrate the end-to-end screening pipeline.

**Flow:**
1. fetch symbols from configured watchlists
2. fetch market metrics and equity quotes
3. apply IV screening
4. fetch option expirations, chains, and option quotes
5. evaluate spreads through `SpreadAnalyzer`
6. filter and score final opportunities
7. hand persistence to `PersistenceService`

### 3.5 Persistence Service (`persistence_service.py`)

**Responsibility**: Centralized CSV writing.

**Writes:**
- `trades/trades_open.csv`
- `opportunities/opportunities_YYYYMMDD_HHMMSS[_indicative].csv`

### 3.6 Typed Result Models (`run_models.py`)

**Responsibility**: Service-boundary dataclasses for predictable orchestration results.

## 4. Screener Layer (`screener/`)

### 4.1 IV Screener (`iv_screener.py`)

**Responsibility**: Apply IV and liquidity filters to the initial symbol universe.

### 4.2 Spread Analyzer (`spread_analyzer.py`)

**Responsibility**: Evaluate candidate put credit spreads.

**Internal supporting modules:**
- `spread_models.py`
- `spread_scoring.py`
- `spread_logging.py`

**Key behaviors:**
- anchor strike selection
- OTM/ITM shift evaluation
- width locking
- credit and liquidity filtering
- EV scoring
- candidate logging and rejection logging

## 5. Analytics Layer (`analysis/`)

**Responsibility**: Offline review and reporting from stored candidate and trade history.

**Key scripts:**
- `build_analysis_dataset.py`
- `data_quality_audit.py`
- `rejection_diagnostics.py`
- `ranking_engine.py`
- `weekly_report.py`
- `run_weekly_pipeline.py`
- `run_weekly_closeout.py`

## 6. Data Flow

### Open Trade Flow

```text
accounts/{account}/positions
        ?
TastytradeAPI.get_account_positions()
        ?
TastytradeAPI.parse_option_spreads()
        ?
PositionSyncService
        ?
trades/trades_open.csv
```

### New Closed Trade Flow

```text
previous trades_open.csv + current positions snapshot
        ?
PositionSyncService detects disappeared trade_id values
        ?
TastytradeAPI.get_account_orders()  [lightweight recent pagination]
        ?
ClosedTradeReconciliationService
        ?
trades/trades_closed.csv
```

### Historical Closed Trade Backfill Flow

```text
trades/trades_closed.csv
        ?
backfill_closed_trade_actuals.py
        ?
TastytradeAPI.get_account_orders()  [deep pagination]
        ?
historical strike/expiration matching
        ?
update actual close values + recalculate dependent P/L metrics
```

### Screener Flow

```text
watchlists
  ?
market metrics + quotes
  ?
IV screening
  ?
option expirations + chains + option quotes
  ?
SpreadAnalyzer evaluation
  ?
PersistenceService export + console display
```

## 7. Trade Tracking Model

### Open Trades

`trades/trades_open.csv` is the live snapshot of currently held spreads.

Source of truth:
- current account positions
- parsed into spread rows

### Closed Trades

`trades/trades_closed.csv` is created when a previously open spread disappears from the live snapshot.

This means the system still detects the event of closure by snapshot diffing, but now improves the exit price source by reconciling against order history.

### Close Value Semantics

- `close_debit`: canonical best-known close value
- `close_debit_estimated`: estimate derived from prior open-position mark
- `close_debit_actual`: broker-confirmed close value when matched

For accurate realized economics, the system prefers actual leg-fill-derived net close values.

## 8. Configuration Areas

`config.py` currently groups configuration into:
- screening thresholds
- spread construction and liquidity rules
- ranking/scoring controls
- cache TTLs
- watchlists
- exit alerts
- order-history reconciliation controls

Relevant trade-tracking settings:
- `ORDER_HISTORY_LOOKBACK_DAYS`
- `ORDER_HISTORY_MAX_PAGES`

## 9. Key Files Added in the Current Refactor

- `services/position_sync_service.py`
- `services/snapshot_service.py`
- `services/screener_run_service.py`
- `services/persistence_service.py`
- `services/closed_trade_reconciliation_service.py`
- `backfill_closed_trade_actuals.py`
- `screener/spread_models.py`
- `screener/spread_scoring.py`
- `screener/spread_logging.py`

## 10. Design Notes

- `main.py` is intentionally small and orchestration-focused.
- Normal trade reconciliation should remain lightweight and incremental.
- Historical cleanup is intentionally separated into a one-off tool so normal runtime stays fast.
- Actual close values should prefer fill-derived economics over submitted order limits.

## 11. Future Enhancements

- add more tests around backfill and reconciliation edge cases
- support partial closes and more complex roll scenarios
- optionally add explicit backfill modes for already-populated actual rows
- continue building analytics datasets now that realized exits are more trustworthy

---

**Last Updated**: April 17, 2026  
**Version**: 2.2
