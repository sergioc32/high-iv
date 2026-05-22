# Closed Trade Actual Fill Reconciliation Plan

## Summary
Upgrade closed-trade tracking so [trades_closed.csv](c:\Users\sergi\development\highIV\trades\trades_closed.csv) stores broker-confirmed closing values from Tastytrade order history whenever available, while preserving the current estimated close values as a fallback.

The current system is correct for open positions:
- [trades_open.csv](c:\Users\sergi\development\highIV\trades\trades_open.csv) is built from live account positions
- [position_sync_service.py](c:\Users\sergi\development\highIV\services\position_sync_service.py) compares prior and current open positions to infer that a trade has disappeared
- [trades_closed.csv](c:\Users\sergi\development\highIV\trades\trades_closed.csv) is then populated from the last known open-position mark, not from actual filled close orders

This plan keeps that inference step for "trade disappeared" detection, but replaces the closing price source with actual broker order/fill data when possible.

## Current State

### What is working correctly
- Open trades are sourced from live positions via:
  - [tastytrade.py](c:\Users\sergi\development\highIV\api\tastytrade.py)
  - `get_account_positions(...)`
- Spread rows are derived from live positions via:
  - [tastytrade.py](c:\Users\sergi\development\highIV\api\tastytrade.py)
  - `parse_option_spreads(...)`
- [trades_open.csv](c:\Users\sergi\development\highIV\trades\trades_open.csv) is therefore a valid live snapshot of currently held spreads.

### What is incorrect for closed trades
- Closed trades are inferred by disappearance from the prior open snapshot.
- The current closed-trade builder uses the prior row's `current_mark` as the estimated `close_debit`.
- No actual account order history is currently queried in the API wrapper.
- This causes `close_debit` in [trades_closed.csv](c:\Users\sergi\development\highIV\trades\trades_closed.csv) to differ from the real execution price shown in Tastytrade activity.

## Confirmed API Input
The sample `accounts/{account_number}/orders` payload you provided shows that the orders endpoint contains the fields needed for a first implementation:

- order-level fields:
  - `id`
  - `price`
  - `price-effect`
  - `status`
  - `received-at`
  - `terminal-at`
  - `size`
  - `underlying-symbol`
- leg-level fields:
  - `action`
  - `symbol`
  - `quantity`
  - `fills`
- fill-level fields:
  - `fill-price`
  - `filled-at`
  - `quantity`

This means the first pass should use the orders endpoint, not positions, as the source of actual closing values.

## Goal
When a trade disappears from the open positions snapshot:
1. Detect that it was closed, as we do today
2. Query recent account order history from Tastytrade
3. Match the disappeared spread to its real closing order/fill
4. Store both:
   - estimated close value
   - actual close value
5. Use the actual close value as the canonical `close_debit` when a match is found

## Canonical Field Rule
This is the agreed behavior:

- `close_debit` should become the actual fill when available
- `close_debit_estimated` should store the current estimated debit
- `close_debit_actual` should store the broker-confirmed actual close debit

Expected steady state:
- most matched records should have:
  - `close_debit == close_debit_actual`
- unmatched records should have:
  - `close_debit == close_debit_estimated`

## Design Principles
- Preserve current open-trade tracking behavior
- Preserve disappearance-based detection of a closed trade
- Minimize API load by fetching only recent orders
- Keep a robust fallback when order matching fails
- Preserve backward compatibility for downstream analytics
- Make actual-vs-estimated provenance explicit in the CSV schema

## Proposed Architecture

### 1. Extend `TastytradeAPI` with recent order history retrieval
File:
- [tastytrade.py](c:\Users\sergi\development\highIV\api\tastytrade.py)

Add methods such as:
- `get_account_orders(account_number: str | None = None, start_at: str | None = None, end_at: str | None = None, status: str | None = None) -> list[dict]`
- optionally:
  - `get_recent_filled_orders(...)`
  - `normalize_order_history_items(...)`

Primary intent:
- fetch only recent filled or recently terminal orders for the account
- capture enough detail to identify the real closing spread fill:
  - order id
  - filled timestamp
  - net price
  - order status
  - legs
  - action/effect
  - quantity
  - underlying symbol
  - option symbols

### 2. Add closed-trade reconciliation logic
Suggested new file:
- `services/closed_trade_reconciliation_service.py`

Responsibilities:
- search recent orders for a disappeared spread
- match the spread to a likely closing fill
- return a normalized actual-close result

Suggested methods:
- `find_actual_close_for_trade(disappeared_trade: pd.Series, recent_orders: list[dict]) -> ActualCloseMatch | None`
- `extract_actual_close_debit(order: dict) -> float | None`
- `order_matches_trade(order: dict, trade_row: pd.Series) -> bool`

### 3. Update `PositionSyncService` to use reconciliation
File:
- [position_sync_service.py](c:\Users\sergi\development\highIV\services\position_sync_service.py)

Current behavior:
- compare prior open trades to current open trades
- for disappeared trade ids, build a closed-trade record from the prior row

New behavior:
- compare prior open trades to current open trades
- fetch recent orders once per sync
- for each disappeared trade:
  - build estimated close as today
  - attempt order-history match
  - store both estimated and actual values
  - promote actual close value to canonical `close_debit` when found

## API Load Strategy

### Recommendation
Do not fetch all historical orders.

Instead:
- default to a recent rolling lookback window
- fetch once per sync, not once per disappeared trade
- match locally in memory

### Proposed default window
Recommended starting point:
- `ORDER_HISTORY_LOOKBACK_DAYS = 14`

Why `14`:
- gives some safety if a sync is skipped for several days
- still small enough to keep API load light
- avoids missing fills from trades closed slightly earlier than expected

### Single fetch per sync
The intended flow is:
1. detect disappeared trade ids
2. if none disappeared, do not fetch orders
3. if some disappeared, fetch recent orders once
4. reconcile all disappeared trades against that one result set

That gives good accuracy with low API load.

## Matching Rules

### Primary identifiers for a match
Use the prior open-trade row fields:
- `symbol`
- `short_option_symbol`
- `long_option_symbol`
- `short_strike`
- `long_strike`
- `expiration`
- `trade_id`

Best matching priority:
1. exact leg-symbol match
2. same underlying + same strikes + same expiration
3. closing leg actions align with the spread
4. nearest filled timestamp to disappearance date

### Expected close-side behavior
For a short put spread close:
- short leg should be `Buy to Close`
- long leg should be `Sell to Close`

We should normalize order-side semantics into internal forms like:
- `buy_to_close`
- `sell_to_close`
- `sell_to_open`
- `buy_to_open`

### Match confidence levels
Recommended internal states:
- `exact_legs`
- `strike_expiration_match`
- `symbol_only_ambiguous`
- `no_match`

Only use an actual value automatically for strong matches:
- `exact_legs`
- maybe `strike_expiration_match` if leg symbols are absent but the order is clearly unique

## Actual Close Value Rules

### Primary source
Use the order-level net price when available:
- `price`
- `price-effect`

Reason:
- this matches how Tastytrade displays the spread order fill
- it avoids reconstructing net price from separate leg fills unless necessary

Example:
- if order `price = "0.50"` and `price-effect = "Debit"`
- store:
  - `close_debit_actual = 50.0`
  - `close_debit = 50.0`

### Fallback source
If order-level price is missing but leg fills are present:
- compute the spread close debit from the leg fills:
  - `buy_to_close` debit minus `sell_to_close` credit
- normalize to the same contract-dollar format used elsewhere

### Quantity handling
For a single spread:
- `0.50 db` should be stored as `50.0`

For multi-lot spread orders:
- still store per-spread contract-dollar value in:
  - `close_debit_actual`
  - `close_debit`
- do not multiply by size for the canonical field

This keeps the field consistent with the existing `entry_credit` and `current_mark` representation.

## CSV Schema Changes

### Preserve existing fields
Keep the current columns so downstream tools do not break.

### Add new columns
Recommended additions to [trades_closed.csv](c:\Users\sergi\development\highIV\trades\trades_closed.csv):

- `close_debit_estimated`
- `close_debit_actual`
- `actual_exit_found`
- `exit_price_source`
- `close_fill_timestamp`
- `close_order_id`
- `match_confidence`

### Canonical field behavior
Recommended rule:
- `close_debit` remains the best-known closing value
- if actual fill found:
  - `close_debit = close_debit_actual`
- otherwise:
  - `close_debit = close_debit_estimated`

## Record-Building Rules

### Estimated values
Keep current estimate logic:
- estimate from prior `current_mark`
- preserve current scaling safeguards
- store in `close_debit_estimated`

### Actual values
When a broker match is found:
- parse the filled debit from the order
- normalize it to the same contract-dollar format used elsewhere
- store in `close_debit_actual`
- override `close_debit`

### Exit metadata
Recommended updates:
- `is_estimated_exit = False` when actual fill found
- `exit_type = "order_history_match"` when actual fill found
- `exit_type = "api_detection"` when only estimate exists

## Implementation Slices

### Slice 1: API wrapper support
File:
- [tastytrade.py](c:\Users\sergi\development\highIV\api\tastytrade.py)

Add:
- recent account orders fetch method
- optional response normalization helper

Success criteria:
- can fetch a small recent order window
- returns terminal orders with enough detail for matching

### Slice 2: Reconciliation service
New file:
- `services/closed_trade_reconciliation_service.py`

Add:
- order normalization
- leg matching
- actual close debit extraction
- confidence scoring

Success criteria:
- given a disappeared trade row and recent order payloads, returns best actual match or `None`

### Slice 3: Closed-trade builder integration
File:
- [position_sync_service.py](c:\Users\sergi\development\highIV\services\position_sync_service.py)

Update:
- fetch recent orders once when closed trades are detected
- pass them into reconciliation
- write both estimated and actual values

Success criteria:
- closed-trade rows contain new fields
- actual close values appear when matched
- old fallback behavior still works when no order is found

### Slice 4: CSV compatibility and migration
Files:
- [position_sync_service.py](c:\Users\sergi\development\highIV\services\position_sync_service.py)
- potentially [persistence_service.py](c:\Users\sergi\development\highIV\services\persistence_service.py) if needed

Update:
- new columns appended safely
- existing files remain readable
- historical rows without actual values still load correctly

Success criteria:
- no breakage when appending to existing [trades_closed.csv](c:\Users\sergi\development\highIV\trades\trades_closed.csv)

### Slice 5: Tests
Add tests for:
- exact match using leg symbols
- fallback to estimate when no order match exists
- actual close overrides canonical `close_debit`
- one recent orders fetch used for multiple disappeared trades
- CSV output schema stability

## Testing Plan

### Unit tests
Suggested files:
- `tests/test_closed_trade_reconciliation_service.py`
- extend [test_position_sync_service.py](c:\Users\sergi\development\highIV\tests\test_position_sync_service.py)

Cover:
- exact two-leg close match
- mismatched symbol
- ambiguous same-symbol order
- correct normalization of debit values
- actual vs estimated fallback behavior

### Regression tests
Cover:
- existing closed-trade creation still works when no order history is available
- [trades_closed.csv](c:\Users\sergi\development\highIV\trades\trades_closed.csv) still appends rows correctly
- `close_debit` canonical field now uses actual value when available

## Risks and Edge Cases

### 1. Sync gap longer than lookback window
Risk:
- a trade closes, but sync is not run until much later
- recent orders window misses the close

Mitigation:
- use 14-day default lookback
- make it configurable
- fallback to estimated value

### 2. Partial closes
Risk:
- a multi-lot spread is closed in parts

Mitigation:
- match quantity where possible
- start by supporting full close matches first
- document partials as a later enhancement if necessary

### 3. Rolls
Risk:
- a close and a new open happen in one combined order

Mitigation:
- match on closing leg actions and exact symbols
- prefer actual match only when closing legs are clearly identifiable

### 4. Ambiguous orders
Risk:
- multiple similar orders in the same symbol/expiration

Mitigation:
- require exact leg-symbol match for automatic confidence
- otherwise leave actual blank and keep estimate

## Recommended Config Additions
Suggested new config values in [config.py](c:\Users\sergi\development\highIV\config.py):

- `ORDER_HISTORY_LOOKBACK_DAYS = 14`
- `ORDER_HISTORY_MATCH_BUFFER_DAYS = 3`
- optionally:
  - `USE_ACTUAL_CLOSE_RECONCILIATION = True`

## First Pass Scope
The first implementation pass should stay intentionally narrow:

1. add recent order-history retrieval to [tastytrade.py](c:\Users\sergi\development\highIV\api\tastytrade.py)
2. verify the real payload shape in code using the same structure as the provided sample
3. support matching only `Filled` spread-close orders with clear two-leg matches
4. use order-level `price` and `price-effect` as the source of `close_debit_actual`
5. keep the current estimate logic as the fallback

This keeps the first pass practical and low-risk.

## Progress Tracking

### Planned
- [ ] Add recent account order-history retrieval to `TastytradeAPI`
- [ ] Add closed-trade reconciliation service
- [ ] Integrate actual close reconciliation into `PositionSyncService`
- [ ] Expand `trades_closed.csv` schema
- [ ] Add unit tests
- [ ] Add regression tests

### In Progress
- [ ] Add focused tests for reconciliation and closed-trade schema updates

### Completed
- [x] Confirm current closed-trade logic is estimate-based
- [x] Confirm open-trade logic is sourced from live positions
- [x] Confirm orders endpoint includes the fields needed for a first pass
- [x] Decide canonical field rule for `close_debit`
- [x] Add recent account order-history retrieval to `TastytradeAPI`
- [x] Add closed-trade reconciliation service
- [x] Integrate actual close reconciliation into `PositionSyncService`
- [x] Expand `trades_closed.csv` schema



