# Analytics Dataset Evolution Plan

## Objective
Create a clear path from the current reporting-oriented analytics layer to a set of dense, reliable datasets that support:

- rejected-candidate diagnostics
- executed-trade performance analysis
- model-ready feature engineering
- future supervised learning without leakage

This plan treats the current analytics stack as a strong Phase 1 foundation and defines the next steps needed to make the data better suited for tuning, ranking improvements, and eventually ML.

---

## Current State Summary

### Canonical reporting dataset
- Current canonical reporting file: `analysis/analysis_dataset.csv`
- Current purpose: reporting and cross-source reconciliation
- Current limitation: it is not model-ready because it mixes:
  - candidate rows
  - candidate rows linked to trades
  - trade-only rows with no candidate linkage

### Current observed data shape
- Total rows in `analysis/analysis_dataset.csv`: `33,222`
- Selected candidate rows: `586`
- Rejected candidate rows: `32,612`
- Trade-only rows: `24`
- Unique closed trade records: `33`
- Unique closed trades with exact or adjusted entry linkage: `9`
- Unique closed trades with `trade_only` linkage: `24`
- Unique closed trades with actual exits available: `31`
- Unique symbols in closed trade history: `15`
- Closed trade date range: `2026-01-27` to `2026-04-17`

### What this means
- The current dataset is good for reporting, diagnostics, and reconciliation.
- The current dataset is not the right shape for direct ML training.
- The biggest current bottleneck is not just closed-trade count, but feature-linked closed-trade count.

---

## Guiding Principles

### 1. Keep reporting and modeling datasets separate
- `analysis/analysis_dataset.csv` should remain the reporting layer.
- Dense analysis/training datasets should be built separately.

### 2. Entry-time features only for any model input
- No post-entry monitoring fields may be used as predictive features.
- No outcome fields may be used as predictive features.
- Reconciliation metadata should be used for label-quality weighting, not prediction.

### 3. Improve observability before changing live scoring too aggressively
- New candidate-quality signals should usually be captured and logged first.
- Analytics should evaluate whether those signals actually separate good from bad outcomes.
- Only then should those signals be promoted into live ranking or filters.

### 4. Human-in-the-loop remains the operating model
- Analytics can recommend score changes, threshold changes, or new features.
- No automatic strategy changes should happen without review.

---

## Target Dataset Architecture

### Dataset 1: Reporting dataset
**File:** `analysis/analysis_dataset.csv`

**Purpose**
- Weekly reporting
- trade reconciliation visibility
- segmentation and diagnostics

**Status**
- Already implemented
- Keep as canonical reporting dataset
- Do not treat as the primary ML training table

### Dataset 2: Rejected candidate dataset
**Proposed file:** `analysis/rejected_candidate_dataset.csv`

**Purpose**
- understand why candidates are rejected
- identify tunable filters that may be too strict
- compare rejected candidates to selected candidates within the same run context

**Row grain**
- one row per rejected candidate

**Primary sources**
- `opportunities/opportunity_candidates.csv`
- optional run-level context from rankings or grouped sibling candidates

### Dataset 3: Executed trade dataset
**Proposed file:** `analysis/executed_trade_dataset.csv`

**Purpose**
- analyze successful vs unsuccessful trades
- create a dense one-row-per-trade dataset
- support future training dataset creation

**Row grain**
- one row per unique executed trade

**Primary sources**
- `trades/trades_closed.csv`
- `trades/trades_open.csv` when needed for lifecycle continuity
- matched entry-time features from `opportunities/opportunity_candidates.csv`

### Dataset 4: Training dataset
**Proposed file:** `ml/training_dataset.csv`

**Purpose**
- supervised learning inputs
- time-aware evaluation
- no leakage

**Row grain**
- one row per unique executed trade eligible for training

**Primary sources**
- derived from `analysis/executed_trade_dataset.csv`

---

## Workstream A: Executed Trade Dataset

### Goal
Build a clean one-row-per-trade dataset that links executed trades back to entry-time features and carries outcome fields plus label-quality metadata.

### Why this matters
- This is the main bridge between trade outcomes and candidate features.
- Right now only a small portion of unique closed trades are linked back to candidate rows with `exact_match` or `adjusted_match`.
- This is the most important blocker for future supervised learning.
- Some trades still come from reviewed setup context even when they are not exact candidate-log matches.
- Provenance and review-context metadata help preserve partial analytical value for those rows without overstating confidence.

### Proposed file
- `analysis/build_executed_trade_dataset.py`

### Proposed output
- `analysis/executed_trade_dataset.csv`

### Required columns
- `trade_id`
- `symbol`
- `entry_date`
- `close_date`
- `trade_status`
- `match_status`
- `entry_match_quality`
- `strategy_version`
- `actual_exit_found`
- `exit_price_source`
- `close_fill_timestamp`
- `close_order_id`
- `match_confidence`
- `label_quality_weight`
- `feature_provenance`
- `reviewed_setup_found`
- `reviewed_setup_match_type`
- `review_context_quality`

### Entry-time feature columns
- `run_id`
- `snapshot_ts`
- `expiration_date`
- `dte`
- `stock_price`
- `short_strike`
- `long_strike`
- `width`
- `premium`
- `premium_per_width`
- `max_profit`
- `max_loss`
- `risk_reward_ratio`
- `short_delta`
- `short_iv`
- `atm_iv`
- `skew_ratio`
- `skew_diff`
- `earnings_within_dte`
- `credit_mid`
- `credit_natural`
- `credit_expected`
- `fill_quality`
- `avg_width_pct`
- `mid_weight`

### Outcome columns
- `close_debit`
- `close_debit_estimated`
- `close_debit_actual`
- `fees_estimated`
- `dte_at_close`
- `profit_loss`
- `profit_loss_pct`
- `profit_pct_of_max`
- `annualized_return`
- `is_estimated_exit`
- `exit_type`
- `exit_notes`

### Label-quality policy
- `1.0` for `exact_match` plus actual exit
- `0.8` for `adjusted_match` plus actual exit
- `0.5` for exact or adjusted match with estimated exit
- `0.3` for `trade_only`

### Acceptance criteria
- one row per unique executed trade
- exact and adjusted matches preserved
- trade-only rows retained but clearly flagged
- actual-vs-estimated exit provenance included
- output can be used for executed-trade analysis without joining to the reporting dataset

### Checklist
- [x] Create `analysis/build_executed_trade_dataset.py`
- [x] Build one-row-per-trade reconciliation logic
- [x] Add label-quality weighting
- [x] Add provenance and review-context metadata
- [x] Write `analysis/executed_trade_dataset.csv`
- [x] Document schema in `docs/data_contracts.md`

---

## Workstream B: Rejected Candidate Dataset

### Goal
Build a dense dataset dedicated to rejected-candidate analysis so filter tuning does not depend on the sparse mixed reporting dataset.

### Why this matters
- Rejection diagnostics are already useful, but they are mostly summary-oriented.
- A dense rejected-candidate table will let us compare rejected setups directly against selected setups and identify near-miss opportunities.

### Proposed file
- `analysis/build_rejected_candidate_dataset.py`

### Proposed output
- `analysis/rejected_candidate_dataset.csv`

### Row grain
- one row per rejected candidate

### Required columns
- `run_id`
- `snapshot_ts`
- `strategy_version`
- `symbol`
- `expiration_date`
- `dte`
- `stock_price`
- `short_strike`
- `long_strike`
- `width`
- `premium`
- `premium_per_width`
- `max_profit`
- `max_loss`
- `risk_reward_ratio`
- `short_delta`
- `short_iv`
- `atm_iv`
- `skew_ratio`
- `skew_diff`
- `earnings_within_dte`
- `credit_mid`
- `credit_natural`
- `credit_expected`
- `fill_quality`
- `avg_width_pct`
- `mid_weight`
- `candidate_status`
- `selected`
- `rejection_reason_primary`
- `rejection_reason_flags`

### Helpful derived columns
- `rejection_bucket`
- `delta_distance_from_target`
- `moneyness_pct`
- `premium_pct_of_width`
- `width_pct_of_stock`
- `sibling_selected_exists`
- `same_group_candidate_count`
- `same_group_liquidity_failure_count`
- `same_group_ranked_out_exists`

### Acceptance criteria
- one row per rejected candidate
- rejection bucket and derived context fields added
- output supports direct grouping by reason, symbol, strategy, DTE, delta, skew, and width

### Checklist
- [x] Create `analysis/build_rejected_candidate_dataset.py`
- [x] Add derived rejection analysis fields
- [x] Write `analysis/rejected_candidate_dataset.csv`
- [x] Document schema in `docs/data_contracts.md`

---

## Workstream C: Executed Trade Analysis

### Goal
Understand which entry-time conditions are associated with strong vs weak realized trade outcomes.

### Proposed file
- `analysis/trade_outcome_review.py`

### Output
- markdown and CSV summaries under `analysis/reports/`

### Primary questions
- What features are common among profitable trades?
- What features are common among losing trades?
- Do exact and adjusted matches behave differently?
- Do actual-exit trades differ from estimated-exit trades?
- Does strategy version matter?
- Which symbols or setup shapes are underperforming?

### Suggested first analyses
- win/loss segmentation by:
  - symbol
  - width
  - DTE bucket
  - delta bucket
  - skew bucket
  - `premium_per_width`
  - `fill_quality`
  - `credit_expected / width`
- outcome breakdown by:
  - `match_status`
  - `actual_exit_found`
  - `exit_price_source`
  - `strategy_version`

### Acceptance criteria
- one report focused on trade outcomes only
- exact vs adjusted vs trade-only explicitly separated
- actual vs estimated exits explicitly separated
- suitable as a weekly or monthly decision-support artifact

### Checklist
- [x] Create `analysis/trade_outcome_review.py`
- [x] Add match-quality and exit-quality segmentation
- [x] Export markdown summary
- [x] Export machine-readable CSV summary

---

## Workstream D: Rejected Candidate Review

### Goal
Turn rejected-candidate analytics into an actionable tuning tool.

### Proposed file
- `analysis/rejected_candidate_review.py`

### Output
- markdown and CSV summaries under `analysis/reports/`

### Primary questions
- Which filters reject the most candidates?
- Which rejection reasons are increasing over time?
- Which rejected candidates look closest to acceptable?
- Which rejection reasons are blocking otherwise attractive candidates?
- Are some filters too aggressive for certain symbols, widths, or volatility regimes?

### Suggested first analyses
- frequency by rejection reason
- rejection share by symbol
- rejection share by strategy version
- rejection share by DTE bucket and width
- near-miss review for:
  - `credit_expected_too_low`
  - `risk_reward`
  - `delta_bounds_max`
  - `selected_ranked_out`
- compare rejected vs selected distributions for:
  - `skew_ratio`
  - `short_delta`
  - `premium_per_width`
  - `fill_quality`
  - trend/extension features added later

### Acceptance criteria
- can identify the top tuning opportunities by filter and symbol
- can identify “good-looking rejects” without manual CSV inspection

### Checklist
- [x] Create `analysis/rejected_candidate_review.py`
- [x] Add near-miss analysis
- [x] Add selected-vs-rejected comparison tables
- [x] Export markdown summary
- [x] Export machine-readable CSV summary

---

## Workstream E: Model-Ready Feature Engineering

### Goal
Freeze a leakage-safe feature set that can later feed baseline supervised models.

### Proposed file
- `ml/build_training_dataset.py`

### Proposed output
- `ml/training_dataset.csv`

### Core feature policy
- Use entry-time fields only.
- Exclude lifecycle fields and all outcome fields.
- Keep reconciliation metadata as sample-weighting and label-quality metadata only.

### Recommended base features
- `dte`
- `stock_price`
- `short_strike`
- `long_strike`
- `width`
- `premium`
- `premium_per_width`
- `max_profit`
- `max_loss`
- `risk_reward_ratio`
- `short_delta`
- `short_iv`
- `atm_iv`
- `skew_ratio`
- `skew_diff`
- `earnings_within_dte`
- `credit_mid`
- `credit_natural`
- `credit_expected`
- `fill_quality`
- `avg_width_pct`
- `mid_weight`
- `strategy_version`

### Recommended derived features
- `moneyness_pct = (stock_price - short_strike) / stock_price`
- `width_pct_of_stock = width / stock_price`
- `premium_pct_of_width = premium / (width * 100)`
- `iv_spread = short_iv - atm_iv`
- `delta_distance_from_target = abs(short_delta - target_delta)`
- `has_earnings_before_exit`
- DTE bucket
- delta bucket
- skew bucket
- width bucket

### Labels to prepare
- `win_flag`
- `profit_loss`
- `profit_loss_pct`
- `profit_pct_of_max`
- `annualized_return`
- optional future targets:
  - target-profit hit probability
  - downside-risk probability

### Excluded from features
- `trade_status`
- `close_date`
- `close_debit`
- `close_debit_actual`
- `close_debit_estimated`
- `profit_loss`
- `profit_loss_pct`
- `annualized_return`
- `current_mark`
- `current_pnl`
- `current_pnl_pct`
- `dte_remaining`
- `exit_signal`
- `match_status`
- `actual_exit_found`
- `exit_price_source`

### Acceptance criteria
- one row per training-eligible executed trade
- no leakage fields present in input columns
- time-aware splits supported
- sample weights included from label quality

### Checklist
- [x] Create `ml/build_training_dataset.py`
- [x] Freeze feature schema version
- [x] Add leakage guard checks
- [x] Add provenance-aware sample weighting
- [ ] Write `ml/training_dataset.csv`

---

## Workstream F: Training Data Audit

### Goal
Validate that the future training dataset is trustworthy before any model training begins.

### Proposed file
- `ml/training_data_audit.py`

### Checks to add
- schema validation
- missing-value coverage by feature
- label distribution
- win/loss balance
- exact vs adjusted vs trade-only counts
- actual-vs-estimated exit counts
- time-based split integrity
- duplicate trade detection
- leakage checks

### Acceptance criteria
- clear pass/fail view of training readiness
- machine-readable and human-readable output

### Checklist
- [x] Create `ml/training_data_audit.py`
- [x] Add label-quality checks
- [x] Add time-split integrity checks
- [x] Add leakage checks

---

## Readiness Gates For Supervised Modeling

### Replace the old generic gate with a stricter one
Model readiness should be based on unique, feature-linked, high-quality trade rows.

### Recommended minimum gates
- [ ] At least `50` exact or adjusted matched unique closed trades
- [ ] Preferred: at least `75`
- [ ] At least `20` losing matched trades
- [ ] At least `20` unique symbols in matched-trade history
- [ ] At least `80%` of training rows have actual exits
- [ ] Trade-only rows excluded or heavily down-weighted
- [ ] No critical leakage issues
- [ ] Time-aware validation split implemented

### Current snapshot vs target
- Current unique closed trades: `33`
- Current unique matched closed trades (`exact_match` + `adjusted_match`): `9`
- Current unique trade-only closed trades: `24`
- Current unique closed trades with actual exits: `31`

### Current conclusion
- Continue analytics foundation work now.
- Do not start serious supervised modeling yet.
- Priority should be improving feature-linked trade coverage and dense dataset generation.

---

## Scoring And Signal Development Strategy

### Problem statement
Current scoring signals such as Align Score and skew-based signals are helpful, but they do not fully capture setup quality.

Example issue:
- A setup can look strong on skew and alignment while still being unattractive because price is extended after a rapid multi-week run-up.
- A spread can also score well on economics while still being unlikely to fill efficiently.

### Recommended operating approach
Use a two-step strategy:

#### Step 1: Instrument first
Add new candidate-quality signals to datasets and logs before using them to drive live scoring aggressively.

#### Step 2: Validate through analytics
Use rejected-candidate review and executed-trade outcome review to determine whether the signals actually help distinguish better trades from worse trades.

Only after that:
- add the best signals into live ranking
- revise Align Score or replace it with a more evidence-based score

### Signals worth instrumenting next

#### Trend / extension / price-position signals
- Phase 1 priority signals from current market snapshot data:
  - `range_position_52w`
  - `distance_to_52w_high_pct`
  - `distance_to_52w_low_pct`
  - `year_high_price`
  - `year_low_price`
- Phase 2 trend/extension signals that require historical price bars or stored market history:
  - `return_20d`
  - `return_40d`
  - `return_60d`
  - `price_vs_20dma_pct`
  - `price_vs_50dma_pct`
  - `price_vs_200dma_pct`
  - `realized_volatility_20d`

These help capture the “SOXL problem” where a setup may look statistically attractive on option terms but still be late-stage or extended.

#### Fill / execution quality signals
- `fill_edge = credit_expected - credit_natural`
- `fill_edge_pct = (credit_expected - credit_natural) / abs(credit_expected)`
- `mid_capture_pct = (credit_expected - credit_natural) / max(0.01, credit_mid - credit_natural)`
- `fill_quality_score` built from:
  - natural vs expected distance
  - expected vs mid distance
  - bid/ask width metrics
  - OI and volume metrics when available

These help distinguish trades that look good on paper from trades that are likely to fill cleanly.

#### Structural quality signals
- `anchor_vs_shift_status`
- `shift_steps_from_anchor`
- `short_strike_shift`
- `long_strike_shift`
- `execution_alignment`
- `shift_direction`
- whether the candidate is a ranked-out alternative
- whether a symbol repeatedly fails the same filter type

### Signals that should not immediately become hard filters
- price-extension metrics
- range-position metrics
- fill metrics

These should be used first as:
- logged features
- ranking components
- analysis dimensions

Only later, if strongly supported by data, should any become hard exclusion rules.

---

## Recommended Implementation Order

### Phase 1: Dense datasets
1. Build `analysis/executed_trade_dataset.csv`
2. Build `analysis/rejected_candidate_dataset.csv`
3. Document both schemas

### Phase 2: Review tools
1. Build `analysis/trade_outcome_review.py`
2. Build `analysis/rejected_candidate_review.py`
3. Add reporting outputs

### Phase 3: New signal instrumentation
1. Add currently available trend/extension fields to candidate logging:
   - `year_high_price`
   - `year_low_price`
   - `range_position_52w`
   - `distance_to_52w_high_pct`
   - `distance_to_52w_low_pct`
2. Add fill-quality fields to candidate logging:
   - `fill_edge`
   - `fill_edge_pct`
   - `mid_capture_pct`
   - `fill_quality_score`
3. Add structural-context fields to candidate logging and downstream datasets:
   - `anchor_vs_shift_status`
   - `shift_steps_from_anchor`
   - `shift_direction`
   - ranked-out context
4. Include all new signals in dense datasets and review outputs
5. Defer rolling return and moving-average features until historical bar access or stored price history is available

### Phase 4: Training preparation
1. Build `ml/training_dataset.csv`
2. Build `ml/training_data_audit.py`
3. Freeze feature schema version

### Phase 5: Modeling
1. Start baseline supervised models only after readiness gates are met
2. Benchmark against current ranking and weekly-review process

---

## Progress Tracker

### Dataset architecture
- [ ] Keep `analysis/analysis_dataset.csv` as reporting-only dataset
- [x] Add `analysis/executed_trade_dataset.csv`
- [x] Add `analysis/rejected_candidate_dataset.csv`
- [x] Add `ml/build_training_dataset.py`
- [ ] Add `ml/training_dataset.csv`

### Executed trade workflow
- [x] Build executed trade dataset builder
- [x] Add label-quality weighting
- [x] Improve match-quality visibility
- [x] Add provenance and review-context visibility

### Rejected candidate workflow
- [x] Build rejected candidate dataset builder
- [x] Add near-miss analysis
- [x] Add selected-vs-rejected comparisons

### Feature engineering
- [x] Freeze base feature schema
- [x] Add derived entry-time features
- [ ] Add 52-week range/extension signals
- [ ] Add rolling return and moving-average signals later when historical bars are available
- [ ] Add fill/execution quality signals
- [ ] Add structural context signals

### ML readiness
- [x] Build training dataset builder
- [x] Build training data audit
- [x] Implement time-aware split indicators
- [x] Validate readiness gates

---

## Decision Summary

### Recommended answer to “before analytics or after analytics?”
Do both, but in the right order:

1. Add a small number of high-value new signals now
   - especially trend/extension and fill-quality fields
2. Log them and carry them into the dense datasets
3. Use analytics to evaluate whether they actually improve trade selection
4. Only then promote them into live scoring and ranking changes

### Why this is the best path
- It avoids overfitting your intuition into the live score too early.
- It lets the analytics layer tell you whether your instincts are consistently right.
- It keeps your strategy improvements evidence-based instead of purely anecdotal.

---

## Data Availability Notes

### Current market snapshot fields already available
Based on the current market-data response shape, the following equity-level fields are readily available now:

- `year-low-price`
- `year-high-price`
- `open`
- `day-high-price`
- `day-low-price`
- `close`
- `prev-close`
- `mark`
- `last`
- `volume`

This makes the following extension features straightforward to add now:

- `year_high_price`
- `year_low_price`
- `range_position_52w`
- `distance_to_52w_high_pct`
- `distance_to_52w_low_pct`

### Fields not directly available from the current snapshot
These are not present in the current snapshot payload and would require either:

- historical daily candle retrieval from the API, or
- locally stored daily price history

Deferred fields:
- `return_20d`
- `return_40d`
- `return_60d`
- `price_vs_20dma_pct`
- `price_vs_50dma_pct`
- `price_vs_200dma_pct`
- `realized_volatility_20d`

### Recommendation
Start with the 52-week context fields immediately because they are low-friction and directly address the “overextended but high-scoring” problem. Add rolling-return and moving-average signals later when a historical-price path is in place.
