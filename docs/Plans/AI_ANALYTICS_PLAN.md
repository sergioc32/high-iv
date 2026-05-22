# AI Trade Analytics Plan

## Objective
Build a human-in-the-loop analytics and ranking system that:
- Analyzes historical performance from trades and opportunities.
- Ranks current opportunities with explainable scoring.
- Diagnoses rejection reasons and recommends parameter refinements.
- Establishes a clean path to a supervised learning model once data quality is stable.

## Scope
Primary data sources:
- `trades/trades_open.csv`
- `trades/trades_closed.csv`
- `opportunities/*.csv`
- `rejections/rejections_tracking.csv`
- `snapshots/*.json`

---

## Phase 1: Analytics Foundation + Explainable Ranking (MVP)

### Goal
Deliver actionable weekly insights and opportunity rankings using robust, transparent analytics.

### Status
Phase 1 is complete as of 2026-04-05. Remaining optional schema enhancements are deferred to Phase 2.

### Phase 1 Design Decisions
- Keep `rejections/rejections_tracking.csv` as the symbol-level rejection log.
- Add `opportunities/opportunity_candidates.csv` as the new candidate-level entry-time dataset.
- Keep trade-to-opportunity matching deterministic, with controlled adjusted-execution fallback for real fills.
- Use only entry-time fields for analytics features and future model inputs.
- Leave source-quality tiers out for now; the workflow assumes trades are taken from script-generated opportunities.

### Phase 1 Implementation Notes (Current State)
- `run_id` and `snapshot_ts` are implemented and passed from `main.py` into `SpreadAnalyzer`.
- `opportunities/opportunity_candidates.csv` is implemented and appends candidate-level rows.
- Selected and rejected candidate logging is implemented in `screener/spread_analyzer.py`.
- `rejections/rejections_tracking.csv` remains active and unchanged for symbol-level diagnostics.
- `rejection_reason_primary` and `rejection_reason_flags` are currently expected to be identical in most rows.
: In Phase 1 we reject on first failing gate and log immediately, so there is usually one reason only.
: `rejection_reason_flags` is intentionally retained for future multi-reason logging without schema churn.
- Candidate pricing now uses a bounded expected-credit model (Phase 1 refinement):
  - `credit_natural = short_bid - long_ask` (x100) = worst-case execution price.
  - `credit_mid = (short_mid - long_mid) * 100` = mid-market expectation.
  - `credit_expected = max(credit_natural, min(weighted, credit_mid))` where `weighted = 0.75 * credit_mid + 0.25 * credit_natural`.
  - Clamping ensures we never go below natural (respects execution risk) and never exceed mid (prevents over-optimism).
  - All economics (premium, max_loss, risk_reward_ratio, EV/ranking inputs) use `credit_expected`.
- Two-gate filtering strategy (Phase 1a refinement):
  - **Gate A (execution sanity)**: Natural credit floor scales by width: `credit_natural > -(width * 100 * MIN_NATURAL_CREDIT_PCT)` (e.g., 5% of max loss). Allows illiquid markets but rejects obviously broken bid/ask pairs.
  - **Gate B (economics)**: Expected credit per-width: `credit_expected >= width * MIN_CREDIT_PER_WIDTH * 100`. Ensures spread pays enough return relative to its width.
  - Rejection reasons: `credit_natural_too_low` (Gate A) and `credit_expected_too_low` (Gate B).
  - Gate A acts as a safety valve; most candidates pass it. Gate B is the real filter, rejecting spreads that don't meet return threshold.
- `ev_score = (premium / max_loss) * (1 - short_delta)` is computed for every candidate and stored in `opportunity_candidates.csv` and `analysis/analysis_dataset.csv`.
- Valid-but-non-selected candidates are logged with `rejection_reason_primary = selected_ranked_out`.
- New rejection reasons added: `itm_or_atm`, `long_strike_unavailable`, `short_leg_missing_quote`, `long_leg_missing_quote`, `credit_natural_too_low`, `credit_expected_too_low`.
- `opportunity_candidates.csv` header auto-migrates if a new column is added; old files continue to load cleanly.
- Analysis reconciliation now supports `exact_match`, `adjusted_match`, `missing_match`, and `trade_only`.
- Weekly reporting includes execution-alignment diagnostics (exact vs shifted vs trade-only), shift direction (OTM/ITM), and daily opportunities-list presence metrics.
- Next candidate-instrumentation priority is to add market-context, fill-quality, and structural-context fields so analytics can evaluate setup quality more holistically before those signals are promoted into live ranking or hard filters.
- Immediate market-context priority fields should use currently available equity snapshot data:
  - `year_high_price`
  - `year_low_price`
  - `range_position_52w`
  - `distance_to_52w_high_pct`
  - `distance_to_52w_low_pct`
- Immediate fill/execution quality priority fields should use already available spread economics:
  - `fill_edge`
  - `fill_edge_pct`
  - `mid_capture_pct`
  - `fill_quality_score`
- Immediate structural-context priority fields should capture how the candidate was produced and selected:
  - `anchor_vs_shift_status`
  - `shift_steps_from_anchor`
  - `short_strike_shift`
  - `long_strike_shift`
  - `shift_direction`
- Deferred until historical price bars are available:
  - `return_20d`
  - `return_40d`
  - `return_60d`
  - `price_vs_20dma_pct`
  - `price_vs_50dma_pct`
  - `price_vs_200dma_pct`
  - `realized_volatility_20d`

### Spread Shift Decision Spec (Implemented)
Goal: Align spread search with manual workflow by locking one spread width at the anchor and shifting by index along the option ladder.

- Anchor selection:
  - Continue selecting anchor short strike by closest delta to `TARGET_DELTA` within current tolerance.
  - Delta is used **only** for anchor selection; shifted candidates are not filtered by delta.
  - Determine one anchor width using precedence:
    1. `PREFERRED_SPREAD_WIDTH` if anchor short minus preferred exists.
    2. `FALLBACK_SPREAD_WIDTH` if preferred is unavailable.
    3. `MAX_STRIKE_INCREMENT` only as final fallback width for sparse chains.
- Width lock:
  - Once anchor width is selected, lock that width for all skew-shift candidates.
  - Do not mix widths within the same symbol/expiration evaluation.
- Shift generation (strike-index walk):
  - Generate candidates by walking the option strike ladder by index, not by dollar multiples.
  - Locked width is preserved: each shift just moves the pair up or down one ladder step.
  - Example for anchor 105/100 (width=5), ladder [..., 95, 100, 105, 110, 115, ...]:
    - OTM shifts (up to `SKEW_WINDOW_OTM`=2): 100/95, 95/90
    - Anchor: 105/100
    - ITM shifts (up to `SKEW_WINDOW_ITM`=1): 110/105
  - Do not generate index-neighbor pairings like 104/99.
- ATM/ITM guard:
  - Any shift candidate where short_strike ≥ stock_price is rejected with reason `itm_or_atm` and never evaluated further.
- Window semantics:
  - Separate `SKEW_WINDOW_OTM` and `SKEW_WINDOW_ITM` for asymmetric control.
  - `SKEW_WINDOW_ITM` is kept tighter (default: 1) to suppress aggressive ITM picks.
- EV-score ranking:
  - All candidates that pass filters are scored with `ev_score = (premium / max_loss) * (1 - short_delta)`.
  - The highest-scoring candidate is selected.
  - Anchor is replaced only when the winner's EV score exceeds anchor EV by at least `MIN_SCORE_IMPROVEMENT_PCT`.
  - Valid non-selected candidates are logged with reason `selected_ranked_out`.
- Risk and quality filters:
  - Keep existing filters and constraints unchanged, including bid/ask checks, credit-per-width, and `MAX_RISK_REWARD_RATIO`.
- Sparse-chain behavior:
  - If a shifted pair does not exist (missing short or long), skip that candidate only.
  - Continue evaluating other valid paired shifts in the window.
  - If no valid paired shifts survive filters, return no opportunity as currently.

### Checklist
- [x] Define canonical data contract (field names, data types, units, and valid ranges).
- [x] Separate entry-time features from outcome-time fields to prevent leakage.
- [x] Implement data quality audit checks:
  - [x] Unit consistency checks (credits/debits/PnL scaling).
  - [x] Schema drift checks across opportunity files.
  - [x] Schema drift checks across `opportunity_candidates.csv` versions.
  - [x] Missing/NaN validation and impossible value detection.
- [x] Add run-level metadata to screener output:
  - [x] Generate `run_id` in the screener entry point.
  - [x] Generate `snapshot_ts` for every run.
  - [x] Pass `run_id` and `snapshot_ts` into spread analysis and logging.
- [x] Add candidate-level logging to `opportunities/opportunity_candidates.csv`:
  - [x] Log one row per evaluated spread candidate.
  - [x] Log selected candidates.
  - [x] Log rejected candidates.
  - [x] Preserve entry-time-only values in this dataset.
  - [x] Log valid-but-non-selected candidates with reason `selected_ranked_out`.
  - [x] Log missing-data cases: `long_strike_unavailable`, `short_leg_missing_quote`, `long_leg_missing_quote`.
  - [x] Log ATM/ITM guard rejections with reason `itm_or_atm`.
- [x] Keep `rejections/rejections_tracking.csv` as the symbol/run-level diagnostic log.
- [x] Define `opportunity_candidates.csv` Version 1 schema:
  - [x] Identity fields: `run_id`, `snapshot_ts`, `symbol`, `expiration_date`, `short_strike`, `long_strike`, `width`.
  - [x] Market context fields: `stock_price`, `dte`, `earnings_within_dte`.
  - [x] Core spread fields: `premium`, `premium_per_width`, `max_profit`, `max_loss`, `risk_reward_ratio`.
  - [x] Core option fields: `short_delta`, `short_iv`, `atm_iv`, `skew_ratio`, `skew_diff`.
  - [x] EV ranking field: `ev_score`.
  - [x] Selection fields: `candidate_status`, `selected`, `rejection_reason_primary`, `rejection_reason_flags`.
- [x] Define `opportunity_candidates.csv` Version 2 schema extension (deferred to Phase 2).
  - [x] Add full leg quote fields (`short_bid`, `short_ask`, `long_bid`, `long_ask`, mids) in Phase 2.
  - [x] Add option identifiers (`short_option_symbol`, `long_option_symbol`) in Phase 2.
  - [x] Add OI and option volume fields in Phase 2.
  - [x] Add bid/ask width percentage fields in Phase 2.
- [x] Build normalized analysis dataset (single table/view for reporting).
- [x] Implement opportunity-to-outcome matching logic:
  - [x] Match on `symbol`, `expiration_date`, `short_strike`, `long_strike`.
  - [x] Prefer same-day opportunity rows.
  - [x] Allow at most a narrow date tolerance if operationally necessary.
  - [x] Use `match_status` values: `exact_match`, `adjusted_match`, `missing_match`, `trade_only`.
  - [x] Add controlled adjusted-execution matching (same symbol/expiration/width, nearest strikes).
- [x] Build core performance reporting:
  - [x] Win rate, average PnL, median PnL, max drawdown proxy.
  - [x] Return segmented by symbol, DTE, width, delta bucket, credit/width, skew bucket.
  - [x] Rolling 7-day, 14-day, and 30-day trend metrics for performance and rejections.
- [x] Build rejection diagnostics from rejection logs:
  - [x] Top rejection reasons by frequency.
  - [x] Time trends for each rejection reason.
  - [x] Sensitivity analysis: what would pass if thresholds were loosened.
  - [x] Add candidate-level rejection review using `opportunity_candidates.csv`.
  - [x] Distinguish symbol-level rejection counts from candidate-level rejection details.
  - [x] Group rejection reasons into rollup buckets (delta / liquidity / pricing_economics / structure / data_quotes / selection).
  - [x] Export reason-level and bucket-level CSV summaries for weekly report ingestion.
  - [x] Add date-window filtering to scope diagnostics to a reporting period.
- [x] Implement explainable ranking score (v1):
  - [x] Weighted components (liquidity, credit efficiency, delta fit, skew quality, risk/reward quality).
  - [x] Output total score plus component-level explanations.
  - [x] Rank opportunities top-to-bottom with confidence bands.
- [x] Backtest ranking quality:
  - [x] Compare top-N vs middle/bottom cohorts on realized outcomes.
  - [x] Validate score calibration by percentile buckets.
- [x] Generate weekly report artifact with:
  - [x] Recommended parameter changes.
  - [x] Expected impact and confidence.
  - [x] Human approval step required before applying changes.

### Phase 1 Deliverables
- [x] `analysis/data_quality_audit.py`
- [x] `analysis/build_analysis_dataset.py`
- [x] `analysis/ranking_engine.py`
- [x] `analysis/rejection_diagnostics.py`
- [x] `analysis/weekly_report.py`
- [x] `analysis/run_weekly_pipeline.py`
- [x] `opportunities/opportunity_candidates.csv`
- [x] `docs/data_contracts.md`
- [x] `analysis/reports/` outputs (CSV summaries from rejection diagnostics)

### Phase 1 Implementation Sequence
- [x] Add `run_id` and `snapshot_ts` generation in `main.py`.
- [x] Pass run metadata into `screener/spread_analyzer.py`.
- [x] Add candidate logger utilities in `screener/spread_analyzer.py`.
- [x] Write Version 1 candidate rows for selected spreads.
- [x] Write Version 1 candidate rows for rejected spreads.
- [x] Keep `rejections/rejections_tracking.csv` unchanged.
- [x] Implement strike-index shift generation with width lock.
- [x] Add ATM/ITM guard, new rejection counters, and `selected_ranked_out` logging.
- [x] Compute and store `ev_score` per candidate; propagate to analysis dataset.
- [x] Implement `analysis/data_quality_audit.py`; clean historical candidate data.
- [x] Implement `analysis/rejection_diagnostics.py` with rollup buckets, date filtering, and CSV exports.
- [x] Implement `analysis/ranking_engine.py` with deterministic component scoring and rank export.
- [x] Document canonical schema in `docs/data_contracts.md`.
- [x] Implement `analysis/weekly_report.py` with performance segmentation, rejection trends, and human-review recommendations.
- [x] Implement `analysis/run_weekly_pipeline.py` to orchestrate rejection diagnostics and weekly report in one command.
- [x] Add enhanced trade reconciliation (exact + adjusted + trade-only coverage for closed executions).

### Phase 1 Code Changes By File

#### `main.py`
- [x] Generate `run_id` once at the start of each screener run.
- [x] Generate `snapshot_ts` once at the start of each screener run.
- [x] Pass `run_id` and `snapshot_ts` into `SpreadAnalyzer`.
- [x] Keep current orchestration responsibilities only; do not move candidate evaluation logic into `main.py`.
- [x] Preserve existing outputs:
  - [x] `opportunities/*.csv`
  - [x] `trades/trades_open.csv`
  - [x] `trades/trades_closed.csv`
  - [x] `rejections/rejections_tracking.csv`

#### `screener/spread_analyzer.py`
- [x] Extend `SpreadAnalyzer.__init__` to accept or store `run_id` and `snapshot_ts`.
- [x] Add a candidate logging helper for `opportunities/opportunity_candidates.csv`.
- [x] Add a helper to build candidate rows from entry-time data only.
- [x] Write one row per evaluated spread candidate.
- [x] Log selected candidates with:
  - [x] `candidate_status=selected`
  - [x] `selected=True`
  - [x] blank rejection fields
- [x] Log rejected candidates with:
  - [x] `candidate_status=rejected`
  - [x] `selected=False`
  - [x] `rejection_reason_primary`
  - [x] `rejection_reason_flags`
- [x] Keep current symbol-level rejection logging to `rejections/rejections_tracking.csv` unchanged.
- [x] Ensure candidate rows include only entry-time data already available during evaluation.
- [x] Do not include any post-entry monitoring fields in candidate rows.

#### `opportunities/opportunity_candidates.csv`
- [x] Create as an append-only dataset.
- [x] Use a stable header with Version 1 columns.
- [x] Append one row for every selected or rejected candidate evaluated by the analyzer.
- [x] Version 1 required columns:
  - [x] `run_id`
  - [x] `snapshot_ts`
  - [x] `symbol`
  - [x] `expiration_date`
  - [x] `dte`
  - [x] `stock_price`
  - [x] `short_strike`
  - [x] `long_strike`
  - [x] `width`
  - [x] `premium`
  - [x] `premium_per_width`
  - [x] `max_profit`
  - [x] `max_loss`
  - [x] `risk_reward_ratio`
  - [x] `short_delta`
  - [x] `short_iv`
  - [x] `atm_iv`
  - [x] `skew_ratio`
  - [x] `skew_diff`
  - [x] `earnings_within_dte`
  - [x] `candidate_status`
  - [x] `selected`
  - [x] `rejection_reason_primary`
  - [x] `rejection_reason_flags`
- [x] Version 2 extension columns (deferred to Phase 2):
  - [x] `short_option_symbol` (Phase 2)
  - [x] `long_option_symbol` (Phase 2)
  - [x] `short_bid` (Phase 2)
  - [x] `short_ask` (Phase 2)
  - [x] `long_bid` (Phase 2)
  - [x] `long_ask` (Phase 2)
  - [x] `short_mid` (Phase 2)
  - [x] `long_mid` (Phase 2)
  - [x] `short_open_interest` (Phase 2)
  - [x] `long_open_interest` (Phase 2)
  - [x] `short_volume` (Phase 2)
  - [x] `long_volume` (Phase 2)
  - [x] `short_bid_ask_width` (Phase 2)
  - [x] `long_bid_ask_width` (Phase 2)
  - [x] `short_bid_ask_width_pct` (Phase 2)
  - [x] `long_bid_ask_width_pct` (Phase 2)
 - [ ] Planned next instrumentation slice for candidate logging:
   - [ ] Market-context fields from current equity snapshot:
     - [ ] `year_high_price`
     - [ ] `year_low_price`
     - [ ] `range_position_52w`
     - [ ] `distance_to_52w_high_pct`
     - [ ] `distance_to_52w_low_pct`
   - [ ] Fill/execution quality fields:
     - [ ] `fill_edge`
     - [ ] `fill_edge_pct`
     - [ ] `mid_capture_pct`
     - [ ] `fill_quality_score`
   - [ ] Structural-context fields:
     - [ ] `anchor_vs_shift_status`
     - [ ] `shift_steps_from_anchor`
     - [ ] `short_strike_shift`
     - [ ] `long_strike_shift`
     - [ ] `shift_direction`
   - [ ] Deferred until historical price bars or stored daily history exist:
     - [ ] `return_20d`
     - [ ] `return_40d`
     - [ ] `return_60d`
     - [ ] `price_vs_20dma_pct`
     - [ ] `price_vs_50dma_pct`
     - [ ] `price_vs_200dma_pct`
     - [ ] `realized_volatility_20d`

#### `rejections/rejections_tracking.csv`
- [x] Keep this file and its current logging flow.
- [x] Continue using it for symbol/run-level diagnostics.
- [x] Do not expand it into candidate-level storage.
- [x] Use `opportunity_candidates.csv` for candidate-level rejection detail instead.

#### `analysis/build_analysis_dataset.py`
- [x] Read `opportunities/opportunity_candidates.csv` as the canonical entry-time feature source.
- [x] Read `trades/trades_open.csv` and `trades/trades_closed.csv` as lifecycle/outcome sources.
- [x] Implement strict reconciliation using:
  - [x] `symbol`
  - [x] `expiration_date`
  - [x] `short_strike`
  - [x] `long_strike`
- [x] Add narrow date alignment rules.
- [x] Use `match_status` values: `exact_match`, `adjusted_match`, `missing_match`, `trade_only`.
- [x] Add controlled adjusted matching (same symbol/expiration/width with nearest strike distance).

#### `analysis/data_quality_audit.py`
- [x] Validate candidate dataset schema and required columns.
- [x] Validate numeric ranges for spreads, premium, max loss, and risk/reward.
- [x] Check for duplicate candidate rows within the same `run_id`.
- [x] Check for impossible values in trades open/closed datasets (deferred to Phase 2 hardening).
- [x] Flag schema drift between candidate log versions.

#### `analysis/rejection_diagnostics.py`
- [x] Continue to summarize `rejections/rejections_tracking.csv` at the symbol level.
- [x] Add candidate-level rejection analysis from `opportunity_candidates.csv`.
- [x] Compare symbol-level and candidate-level rejection distributions.
- [x] Group reasons into rollup buckets for high-level trend visibility.
- [x] Support date-window filtering (`--start-date`, `--end-date`) for weekly reporting windows.
- [x] Export `{prefix}_reason_summary.csv` and `{prefix}_bucket_summary.csv` to `analysis/reports/`.
- [x] Identify which rejection reasons most often remove otherwise attractive candidates (requires ranking engine).

#### `analysis/ranking_engine.py`
- [x] Read candidate rows with `candidate_status=selected`.
- [x] Build explainable score components from entry-time features only.
- [x] Output total rank score and per-component contributions.
- [x] Keep ranking logic deterministic and transparent.
- [x] Export per-run rankings to `analysis/reports/opportunity_rankings_<run_id>.csv`.
- [x] Include `confidence_score` and `confidence_band` in ranking output.

#### `analysis/weekly_report.py`
- [x] Use the normalized analysis dataset as the reporting source.
- [x] Summarize performance by symbol, width, DTE, delta band, and skew bucket.
- [x] Include rejection trends from both retained symbol log and candidate log.
- [x] Compute rolling window metrics (7, 14, 30 days) for performance and rejections.
- [x] Ingest pre-built CSV exports from `rejection_diagnostics.py`:
  - [x] Load `analysis/reports/{prefix}_reason_summary.csv` for detailed rejection section.
  - [x] Load `analysis/reports/{prefix}_bucket_summary.csv` for executive rollup section.
  - [x] Accept `--rejection-prefix` CLI argument to pick the correct weekly export.
- [x] Include human-review recommendations only; no auto-apply behavior.
- [x] Output a markdown summary and a machine-readable CSV artifact to `analysis/reports/`.

#### `analysis/run_weekly_pipeline.py`
- [x] Orchestrate rejection diagnostics and weekly report execution in one command.
- [x] Share date window and prefix across both scripts for alignment.
- [x] Default to latest completed Monday-Sunday week when no dates provided.
- [x] Support custom date windows and output prefixes via CLI arguments.

---

## Phase 2: Supervised Model + Continuous Learning Loop

### Goal
Train and maintain a predictive model that scores expected trade quality while remaining human-in-the-loop for all strategy changes.

### Phase 2 Entry Criteria (Go/No-Go)
Before starting Phase 2 model training and deployment work, meet these minimum gates:

- [ ] Closed-trade volume gate: at least 75 closed trades (100 preferred).
- [ ] Time-coverage gate: at least 4 months of closed-trade history (6 preferred).
- [ ] Breadth gate: at least 20 unique symbols in closed-trade history.
- [ ] Loss-learning gate: at least 20 losing closed trades to represent downside patterns.
- [ ] Label-quality gate: at least 80% of training rows from confirmed/consistent exit logic.
- [ ] Data-quality gate: no critical issues in `analysis/data_quality_audit.py` for the training window.
- [ ] Benchmark gate: baseline model must outperform ranking v1 on out-of-time validation before inference rollout.

Current snapshot (as of 2026-04-05):
- Closed trades: 24
- History window: 2026-01-13 to 2026-04-01 (~2.5 months)
- Unique symbols: 11
- Losing trades: 6
- Status: continue Phase 1 data collection; Phase 2 infrastructure prep is allowed, full model rollout is not yet unlocked.

Scope while gates are not met:
- Allowed now: schema freeze/versioning, training dataset builder, leakage checks, and evaluation harness.
- Deferred until gates pass: production model scoring, blending into live recommendations, and promotion workflow.

### Checklist
- [ ] Freeze and version feature schema from Phase 1 outputs.
- [ ] Add candidate signal instrumentation before live score expansion:
  - [ ] Add market-context fields from current snapshot data:
    - [ ] `year_high_price`
    - [ ] `year_low_price`
    - [ ] `range_position_52w`
    - [ ] `distance_to_52w_high_pct`
    - [ ] `distance_to_52w_low_pct`
  - [ ] Add fill/execution quality fields:
    - [ ] `fill_edge`
    - [ ] `fill_edge_pct`
    - [ ] `mid_capture_pct`
    - [ ] `fill_quality_score`
  - [ ] Add structural-context fields:
    - [ ] `anchor_vs_shift_status`
    - [ ] `shift_steps_from_anchor`
    - [ ] `short_strike_shift`
    - [ ] `long_strike_shift`
    - [ ] `shift_direction`
  - [ ] Carry new fields through candidate logging, analytics datasets, and review outputs.
  - [ ] Defer rolling return / moving-average features until historical price bars are available.
- [ ] Add Phase 2 liquidity/fill-quality ranking component (keep premium formula unchanged):
  - [ ] Build a simple `fill_quality_score` from OI, volume, and bid/ask width metrics.
  - [ ] Keep pricing economics on Phase 1 expected-credit formula; treat liquidity as a separate ranking component.
  - [ ] Validate whether fill-quality ranking improves selected-vs-ranked-out outcome separation.
- [ ] Define supervised targets:
  - [ ] Probability of reaching target profit before exit.
  - [ ] Expected return per trade.
  - [ ] Optional downside risk probability.
- [ ] Add training dataset builder:
  - [ ] Time-aware train/validation/test splits.
  - [ ] Leakage checks (no post-entry fields in training inputs).
  - [ ] Confidence-weighted labels (estimated exits vs confirmed exits).
- [ ] Train baseline models:
  - [ ] Interpretable baseline (logistic/linear/GBM with SHAP-like explanations).
  - [ ] Compare to ranking v1 benchmark.
- [ ] Evaluate model quality:
  - [ ] Discrimination and calibration metrics.
  - [ ] Stability across market regimes.
  - [ ] Performance by symbol/sector and setup type.
- [ ] Deploy inference pipeline:
  - [ ] Score each opportunity during screener runs.
  - [ ] Keep explainability outputs attached to each score.
  - [ ] Blend model score with rule-based guardrails.
- [ ] Build model monitoring:
  - [ ] Data drift alerts.
  - [ ] Prediction drift alerts.
  - [ ] Realized-vs-predicted tracking dashboard.
- [ ] Implement retraining cadence:
  - [ ] Scheduled retraining (e.g., weekly/monthly).
  - [ ] Automatic evaluation gate (promote only if better and stable).
  - [ ] Model/version registry and rollback support.
- [ ] Keep governance human-in-the-loop:
  - [ ] Model can recommend threshold changes.
  - [ ] No automatic parameter updates without approval.

### Phase 2 Deliverables
- [ ] `ml/build_training_dataset.py`
- [ ] `ml/train_model.py`
- [ ] `ml/score_opportunities.py`
- [ ] `ml/evaluate_model.py`
- [ ] `ml/monitoring_report.py`
- [ ] `models/` versioned artifacts
- [ ] `docs/model_governance.md`

---

## Success Criteria

### Phase 1 Exit Criteria (Completed)
- [x] Weekly reports provide concrete, explainable recommendations.
- [x] All strategy adjustments remain user-approved (human-in-the-loop).

### Phase 2 Validation Targets (Pending)
- [ ] Opportunity ranking shows consistent top-cohort outperformance vs baseline.
- [ ] Rejection analysis identifies at least 2-3 high-impact tuning opportunities per month.
- [ ] Model (Phase 2) improves decision quality vs Phase 1 ranking benchmark.

---

## Decision Clarification
The prior "Decisions" section was **not** asking you questions.
It was a summary of recommended operating choices based on your goals:
- Focus on insights + ranking + rejection diagnostics first.
- Use human-in-the-loop approvals.
- Build toward a long-horizon Phase 2 model after Phase 1 data quality is stable.
