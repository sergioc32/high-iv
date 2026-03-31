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

### Phase 1 Design Decisions
- Keep `rejections/rejections_tracking.csv` as the symbol-level rejection log.
- Add `opportunities/opportunity_candidates.csv` as the new candidate-level entry-time dataset.
- Keep trade-to-opportunity matching mechanical and strict.
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
- `ev_score = (premium / max_loss) * (1 - short_delta)` is computed for every candidate and stored in `opportunity_candidates.csv` and `analysis/analysis_dataset.csv`.
- Valid-but-non-selected candidates are logged with `rejection_reason_primary = selected_ranked_out`.
- New rejection reasons added: `itm_or_atm`, `long_strike_unavailable`, `short_leg_missing_quote`, `long_leg_missing_quote`.
- `opportunity_candidates.csv` header auto-migrates if a new column is added; old files continue to load cleanly.

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
- [ ] Add run-level metadata to screener output:
  - [x] Generate `run_id` in the screener entry point.
  - [x] Generate `snapshot_ts` for every run.
  - [x] Pass `run_id` and `snapshot_ts` into spread analysis and logging.
- [ ] Add candidate-level logging to `opportunities/opportunity_candidates.csv`:
  - [x] Log one row per evaluated spread candidate.
  - [x] Log selected candidates.
  - [x] Log rejected candidates.
  - [x] Preserve entry-time-only values in this dataset.
  - [x] Log valid-but-non-selected candidates with reason `selected_ranked_out`.
  - [x] Log missing-data cases: `long_strike_unavailable`, `short_leg_missing_quote`, `long_leg_missing_quote`.
  - [x] Log ATM/ITM guard rejections with reason `itm_or_atm`.
- [x] Keep `rejections/rejections_tracking.csv` as the symbol/run-level diagnostic log.
- [ ] Define `opportunity_candidates.csv` Version 1 schema:
  - [x] Identity fields: `run_id`, `snapshot_ts`, `symbol`, `expiration_date`, `short_strike`, `long_strike`, `width`.
  - [x] Market context fields: `stock_price`, `dte`, `earnings_within_dte`.
  - [x] Core spread fields: `premium`, `premium_per_width`, `max_profit`, `max_loss`, `risk_reward_ratio`.
  - [x] Core option fields: `short_delta`, `short_iv`, `atm_iv`, `skew_ratio`, `skew_diff`.
  - [x] EV ranking field: `ev_score`.
  - [x] Selection fields: `candidate_status`, `selected`, `rejection_reason_primary`, `rejection_reason_flags`.
- [ ] Define `opportunity_candidates.csv` Version 2 schema extension:
  - [ ] Add full leg quote fields (`short_bid`, `short_ask`, `long_bid`, `long_ask`, mids).
  - [ ] Add option identifiers (`short_option_symbol`, `long_option_symbol`).
  - [ ] Add OI and option volume fields.
  - [ ] Add bid/ask width percentage fields.
- [x] Build normalized analysis dataset (single table/view for reporting).
- [x] Implement strict opportunity-to-outcome matching logic:
  - [x] Match on `symbol`, `expiration_date`, `short_strike`, `long_strike`.
  - [x] Prefer same-day opportunity rows.
  - [x] Allow at most a narrow date tolerance if operationally necessary.
  - [x] Use `match_status` values: `exact_match`, `missing_match`.
  - [x] Do not add fuzzy or adjusted-execution matching in Phase 1.
- [ ] Build core performance reporting:
  - [ ] Win rate, average PnL, median PnL, max drawdown proxy.
  - [ ] Return segmented by symbol, DTE, width, delta bucket, credit/width, skew bucket.
  - [ ] Rolling weekly/monthly trend metrics.
- [x] Build rejection diagnostics from rejection logs:
  - [x] Top rejection reasons by frequency.
  - [ ] Time trends for each rejection reason.
  - [ ] Sensitivity analysis: what would pass if thresholds were loosened.
  - [x] Add candidate-level rejection review using `opportunity_candidates.csv`.
  - [x] Distinguish symbol-level rejection counts from candidate-level rejection details.
  - [x] Group rejection reasons into rollup buckets (delta / liquidity / pricing_economics / structure / data_quotes / selection).
  - [x] Export reason-level and bucket-level CSV summaries for weekly report ingestion.
  - [x] Add date-window filtering to scope diagnostics to a reporting period.
- [ ] Implement explainable ranking score (v1):
  - [x] Weighted components (liquidity, credit efficiency, delta fit, skew quality, risk/reward quality).
  - [x] Output total score plus component-level explanations.
  - [x] Rank opportunities top-to-bottom with confidence bands.
- [ ] Backtest ranking quality:
  - [ ] Compare top-N vs middle/bottom cohorts on realized outcomes.
  - [ ] Validate score calibration by percentile buckets.
- [ ] Generate weekly report artifact with:
  - [ ] Recommended parameter changes.
  - [ ] Expected impact and confidence.
  - [ ] Human approval step required before applying changes.

### Phase 1 Deliverables
- [x] `analysis/data_quality_audit.py`
- [x] `analysis/build_analysis_dataset.py`
- [x] `analysis/ranking_engine.py`
- [x] `analysis/rejection_diagnostics.py`
- [ ] `analysis/weekly_report.py`
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
- [ ] Implement `analysis/weekly_report.py`.
- [ ] Add strict trade reconciliation after enough candidate history exists.

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
- [ ] Version 2 extension columns:
  - [ ] `short_option_symbol`
  - [ ] `long_option_symbol`
  - [ ] `short_bid`
  - [ ] `short_ask`
  - [ ] `long_bid`
  - [ ] `long_ask`
  - [ ] `short_mid`
  - [ ] `long_mid`
  - [ ] `short_open_interest`
  - [ ] `long_open_interest`
  - [ ] `short_volume`
  - [ ] `long_volume`
  - [ ] `short_bid_ask_width`
  - [ ] `long_bid_ask_width`
  - [ ] `short_bid_ask_width_pct`
  - [ ] `long_bid_ask_width_pct`

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
- [x] Use only `match_status` values:
  - [x] `exact_match`
  - [x] `missing_match`
- [x] Do not add fuzzy matching in Phase 1.

#### `analysis/data_quality_audit.py`
- [x] Validate candidate dataset schema and required columns.
- [x] Validate numeric ranges for spreads, premium, max loss, and risk/reward.
- [x] Check for duplicate candidate rows within the same `run_id`.
- [ ] Check for impossible values in trades open/closed datasets.
- [x] Flag schema drift between candidate log versions.

#### `analysis/rejection_diagnostics.py`
- [x] Continue to summarize `rejections/rejections_tracking.csv` at the symbol level.
- [x] Add candidate-level rejection analysis from `opportunity_candidates.csv`.
- [x] Compare symbol-level and candidate-level rejection distributions.
- [x] Group reasons into rollup buckets for high-level trend visibility.
- [x] Support date-window filtering (`--start-date`, `--end-date`) for weekly reporting windows.
- [x] Export `{prefix}_reason_summary.csv` and `{prefix}_bucket_summary.csv` to `analysis/reports/`.
- [ ] Identify which rejection reasons most often remove otherwise attractive candidates (requires ranking engine).

#### `analysis/ranking_engine.py`
- [x] Read candidate rows with `candidate_status=selected`.
- [x] Build explainable score components from entry-time features only.
- [x] Output total rank score and per-component contributions.
- [x] Keep ranking logic deterministic and transparent.
- [x] Export per-run rankings to `analysis/reports/opportunity_rankings_<run_id>.csv`.
- [x] Include `confidence_score` and `confidence_band` in ranking output.

#### `analysis/weekly_report.py`
- [ ] Use the normalized analysis dataset as the reporting source.
- [ ] Summarize performance by symbol, width, DTE, delta band, and skew bucket.
- [ ] Include rejection trends from both retained symbol log and candidate log.
- [ ] Ingest pre-built CSV exports from `rejection_diagnostics.py`:
  - [ ] Load `analysis/reports/{prefix}_reason_summary.csv` for detailed rejection section.
  - [ ] Load `analysis/reports/{prefix}_bucket_summary.csv` for executive rollup section.
  - [ ] Accept `--rejection-prefix` CLI argument to pick the correct weekly export.
- [ ] Include human-review recommendations only; no auto-apply behavior.
- [ ] Output a markdown summary and a machine-readable CSV artifact to `analysis/reports/`.

---

## Phase 2: Supervised Model + Continuous Learning Loop

### Goal
Train and maintain a predictive model that scores expected trade quality while remaining human-in-the-loop for all strategy changes.

### Checklist
- [ ] Freeze and version feature schema from Phase 1 outputs.
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
- [ ] Weekly reports provide concrete, explainable recommendations.
- [ ] Opportunity ranking shows consistent top-cohort outperformance vs baseline.
- [ ] Rejection analysis identifies at least 2-3 high-impact tuning opportunities per month.
- [ ] Model (Phase 2) improves decision quality vs Phase 1 ranking benchmark.
- [ ] All strategy adjustments remain user-approved (human-in-the-loop).

---

## Decision Clarification
The prior "Decisions" section was **not** asking you questions.
It was a summary of recommended operating choices based on your goals:
- Focus on insights + ranking + rejection diagnostics first.
- Use human-in-the-loop approvals.
- Build toward a long-horizon Phase 2 model after Phase 1 data quality is stable.
