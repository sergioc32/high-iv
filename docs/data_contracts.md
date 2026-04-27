# Data Contracts

## Purpose
This document defines canonical schemas, data types, units, and validation rules used in Phase 1 analytics.

## Dataset: opportunities/opportunity_candidates.csv

### Description
Candidate-level, entry-time dataset. One row per evaluated spread candidate.

### Key principles
- Entry-time only features.
- No outcome-time fields in this dataset.
- Append-only logging.

### Primary keys
- run_id: string (format YYYYMMDD_HHMMSS)
- snapshot_ts: ISO-8601 datetime string
- symbol: underlying ticker
- expiration_date: YYYY-MM-DD
- short_strike: float
- long_strike: float or blank if unavailable

### Field contract
- run_id: string, required
- snapshot_ts: string, required, ISO-8601
- strategy_version: string, required for new rows, strategy engine label (for example v1_conservative, v2_dynamic)
- symbol: string, required
- expiration_date: string, required, YYYY-MM-DD
- dte: integer, required, days
- stock_price: float, required, USD
- year_high_price: float, optional, USD, current 52-week high from equity market snapshot
- year_low_price: float, optional, USD, current 52-week low from equity market snapshot
- range_position_52w: float, optional, unitless, stock position within the 52-week range in [0, 1]
- distance_to_52w_high_pct: float, optional, unitless, pct distance from stock_price to year_high_price
- distance_to_52w_low_pct: float, optional, unitless, pct distance from year_low_price to stock_price
- short_strike: float, required, USD
- long_strike: float, optional, USD
- width: float, optional, USD
- credit_mid: float, optional, USD per contract, midpoint credit estimate
- credit_natural: float, optional, USD per contract, worst-case fill estimate
- credit_expected: float, optional, USD per contract, modeled fill between natural and mid
- fill_quality: float, optional, unitless, credit_expected / credit_mid when credit_mid > 0
- fill_edge: float, optional, USD per contract, credit_expected - credit_natural
- fill_edge_pct: float, optional, unitless, fill_edge / abs(credit_expected)
- mid_capture_pct: float, optional, unitless, share of available natural-to-mid edge captured by credit_expected
- fill_quality_score: float, optional, unitless, blended execution-quality heuristic from fill_quality, mid_capture_pct, and width quality
- avg_width_pct: float, optional, unitless, average of short/long bid-ask width as pct of mid
- mid_weight: float, optional, unitless, dynamic midpoint weight used in credit_expected
- premium: float, optional, USD per contract
- premium_per_width: float, optional, unitless, premium / (width * 100)
- max_profit: float, optional, USD per contract
- max_loss: float, optional, USD per contract
- risk_reward_ratio: float, optional, unitless, max_loss / premium
- ev_score: float, optional, unitless, (premium / max_loss) * (1 - short_delta)
- short_delta: float, optional, absolute delta in [0, 1]
- short_iv: float, optional, decimal IV in (0, 5]
- atm_iv: float, optional, decimal IV in (0, 5]
- skew_ratio: float, optional, short_iv / atm_iv
- skew_diff: float, optional, short_iv - atm_iv
- earnings_within_dte: string, optional, YYYY-MM-DD or blank
- anchor_vs_shift_status: string, optional, {anchor, shifted}
- shift_steps_from_anchor: integer, optional, negative = more OTM, positive = more ITM, zero = anchor
- short_strike_shift: float, optional, USD shift from the anchor short strike
- long_strike_shift: float, optional, USD shift from the anchor long strike
- shift_direction: string, optional, {otm, anchor, itm}
- candidate_status: enum, required, {selected, rejected}
- selected: boolean, required
- rejection_reason_primary: string, optional
- rejection_reason_flags: string, optional

### Candidate status rules
- selected=True => candidate_status must be selected.
- selected=False => candidate_status must be rejected.
- selected=False may include reasons such as:
  - selected_ranked_out
  - credit_natural_too_low
  - credit_expected_too_low
  - risk_reward
  - short_bid_ask_width
  - long_bid_ask_width
  - long_strike_unavailable
  - short_leg_missing_quote
  - long_leg_missing_quote
  - itm_or_atm

### Row Reading Cheat Sheet
Use one candidate row as five blocks:

1. Identity: what spread was tested?
- symbol
- expiration_date
- short_strike
- long_strike
- width

2. Context: what did the market look like then?
- stock_price
- dte
- earnings_within_dte
- year_high_price
- year_low_price
- range_position_52w
- distance_to_52w_high_pct
- distance_to_52w_low_pct

3. Trade economics: what does the spread pay and risk?
- credit_mid: midpoint-based credit estimate
- credit_natural: worst-case fill estimate
- credit_expected: modeled credit used for economics and ranking
- fill_quality: expected credit as a fraction of midpoint credit
- fill_edge: absolute execution headroom above natural credit
- fill_edge_pct: execution headroom normalized by expected credit
- mid_capture_pct: how much of the natural-to-mid edge the expected fill captures
- fill_quality_score: blended execution-quality heuristic for analytics and future ranking work
- avg_width_pct: combined market width quality signal used in fill modeling
- mid_weight: midpoint weight used to build expected credit
- premium: credit received per contract in USD
- max_loss: worst-case loss per contract in USD
- risk_reward_ratio: max_loss / premium
- premium_per_width: premium normalized by spread width

4. Option quality and skew: how rich is the short leg?
- short_delta: absolute delta of the short put
- short_iv: IV of the short put
- atm_iv: IV of the ATM put for the same expiration
- skew_ratio: short_iv / atm_iv
- skew_diff: short_iv - atm_iv
- ev_score: current ranking score, computed as (premium / max_loss) * (1 - short_delta)

5. Structure and shift context: how was this candidate generated?
- anchor_vs_shift_status
- shift_steps_from_anchor
- short_strike_shift
- long_strike_shift
- shift_direction

6. Decision trail: what happened to this candidate?
- candidate_status
- selected
- rejection_reason_primary
- rejection_reason_flags

Quick interpretation examples:
- selected=True: this spread was chosen for that symbol/run.
- rejected + credit_natural_too_low: spread failed the execution-sanity floor on natural credit.
- rejected + credit_expected_too_low: spread failed the expected-credit per-width economics rule.
- rejected + selected_ranked_out: spread passed filters but lost ranking to another valid candidate.

---

## Dataset: analysis/analysis_dataset.csv

### Description
Normalized analytics table joining candidate rows with trade lifecycle fields.

### Join policy
- strict join key: symbol, expiration_date/expiration, short_strike, long_strike
- date tolerance: candidate run date vs trade entry_date within configured tolerance
- match_status values: exact_match, missing_match, or blank for non-selected candidates

### Leakage policy
- Features for modeling must come from entry-time columns only.
- Outcome columns are for evaluation and reporting only.

### Entry-time feature columns
- Identity and structure: run_id, snapshot_ts, symbol, expiration_date, dte, stock_price, short_strike, long_strike, width
- Spread metrics: credit_mid, credit_natural, credit_expected, fill_quality, avg_width_pct, mid_weight, premium, premium_per_width, max_profit, max_loss, risk_reward_ratio, ev_score
- Option metrics: short_delta, short_iv, atm_iv, skew_ratio, skew_diff
- Context: earnings_within_dte
- Candidate metadata: candidate_status, selected, rejection_reason_primary, rejection_reason_flags

### Outcome columns (not model inputs)
- Match metadata: match_status, trade_status
- Trade linkage: trade_id, entry_date
- Open tracking: buying_power_used, current_mark, current_pnl, current_pnl_pct, dte_remaining, days_held, short_strike_breached, exit_signal
- Closed outcomes: close_date, close_debit, close_debit_estimated, close_debit_actual, actual_exit_found, exit_price_source, close_fill_timestamp, close_order_id, match_confidence, fees_estimated, dte_at_close, profit_loss, profit_loss_pct, profit_pct_of_max, annualized_return, is_estimated_exit, exit_type, exit_notes

---

## Dataset: analysis/rejected_candidate_dataset.csv

### Description
Dense rejected-candidate analytics table derived from `opportunities/opportunity_candidates.csv`.

### Purpose
- analyze rejection behavior without trade/outcome sparsity
- compare rejected candidates to selected sibling candidates
- support filter tuning and near-miss review

### Row grain
- one row per rejected candidate

### Source policy
- base candidate columns come from `opportunities/opportunity_candidates.csv`
- derived fields are added for tuning analysis only

### Derived fields
- `rejection_bucket`
- `delta_distance_from_target`
- `moneyness_pct`
- `premium_pct_of_width`
- `width_pct_of_stock`
- `sibling_selected_exists`
- `same_group_candidate_count`
- `same_group_liquidity_failure_count`
- `same_group_ranked_out_exists`

---

## Dataset: analysis/executed_trade_dataset.csv

### Description
Dense executed-trade table derived from the reconciled reporting dataset plus candidate-log enrichment.

### Purpose
- analyze successful vs unsuccessful trades with one row per trade
- support future training-dataset construction
- separate trade analysis from the sparse mixed reporting table

### Row grain
- one row per unique executed trade

### Source policy
- trade linkage and outcome fields come from `analysis/analysis_dataset.csv`
- candidate-only enrichment fields not present in the reporting dataset may be backfilled from `opportunities/opportunity_candidates.csv`

### Additional metadata
- `entry_match_quality`
- `label_quality_weight`

### Label quality guidance
- `1.0` for exact match with actual exit
- `0.8` for adjusted match with actual exit
- `0.5` for exact/adjusted match with estimated exit
- `0.3` for trade-only

---

## Dataset: rejections/rejections_tracking.csv

### Description
Symbol-level rejection counters per run. Diagnostic only.

### Usage policy
- Use for aggregate rejection trends.
- Do not use as candidate-level training data.

---

## Global validation rules
- Monetary fields are in USD per 1 contract unless noted.
- Delta values are absolute and expected in [0, 1].
- Ratios must be >= 0 when present.
- Required identity fields must not be blank.
- Schema changes require explicit versioned update to this contract.
