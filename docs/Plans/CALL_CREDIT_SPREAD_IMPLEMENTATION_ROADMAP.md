# Call Credit Spread Implementation Roadmap

## Purpose

This document turns the current planning discussion into an execution-ready roadmap for adding a new `call credit spread` strategy to the project while preserving the long-term goal of multi-strategy, market-aware strategy selection.

For the next broader system phase covering scoring, ML, strategy identification, and automated execution, see [NEXT_PHASE_SCORING_ML_AUTOTRADE_ROADMAP.md](/abs/path/c:/Users/sergi/development/highIV/docs/NEXT_PHASE_SCORING_ML_AUTOTRADE_ROADMAP.md).

The guiding principle is:

1. Reuse the current put-spread machinery where it is truly strategy-agnostic.
2. Avoid forcing call spreads into put-specific assumptions.
3. Build the call strategy independently first.
4. Integrate both strategies only after the data contracts, scoring, and analytics can support them cleanly.

## Current Working Assumptions

These are the assumptions currently treated as defaults based on the latest plan answers:

- New strategy type: `call credit spread`
- Intent: bearish / mean-reversion / overextended-name premium selling
- Same as put strategy for v1:
  - `TARGET_DTE`
  - `DTE_TOLERANCE`
  - `PREFERRED_SPREAD_WIDTH`
  - `FALLBACK_SPREAD_WIDTH`
  - `MAX_RISK_REWARD_RATIO`
  - earnings handling and penalties
  - initial screened symbol universe
  - high-IV top-of-funnel universe
- Shared in principle, but expected to diverge later:
  - ranking framework
  - ranking weights
- Separate from put strategy for v1:
  - long call protection target should have its own config value
  - initial `LONG_CALL_DELTA = 0.08`
- Example symmetry:
  - put short leg target delta: `0.16` absolute on the put side
  - call short leg target delta: `0.16` absolute on the call side

## Decision Log

The following decisions have been made from the current planning round:

- Use the same `TARGET_DTE`, `DTE_TOLERANCE`, `PREFERRED_SPREAD_WIDTH`, `FALLBACK_SPREAD_WIDTH`, and `MAX_RISK_REWARD_RATIO` as puts for v1.
- Use the same earnings handling and penalties as puts for v1.
- Run the initial call strategy against the same screened symbol universe as puts.
- Keep the same high-IV top-of-funnel universe for the first version.
- Start with the shared ranking framework, but plan for separate call-specific weights later.
- Use `LONG_CALL_DELTA = 0.08` for the initial call-side protection target.
- For the first integrated runtime, use separate terminal sections with separate CSVs.
- For the first selector version, use a soft preference rather than a hard gate.
- Allow the same stock to qualify for both strategies if it meets the requirements.
- Use all four suggested context inputs in the first selector version:
  - broad market trend
  - symbol range position within 52 weeks
  - distance to 52-week high
  - earnings proximity

## Current Status And Next Work

There are no major strategy-definition blockers remaining from the current question set.

The initial runtime implementation is now in place, but the implementation still needs
hardening and cleanup before the strategy selector and analytics phases should proceed.

## Implementation Status As Of 2026-05-15

Status legend: `[x]` complete, `[~]` partially complete, `[ ]` not started.

Completed or substantially complete:

- call-specific config values exist in `config.py`
- strategy identity fields are documented in `docs/data_contracts.md`
- `CallSpreadAnalyzer` exists and is wired into the runtime
- runtime can evaluate puts, calls, or both
- `--puts-only` and `--calls-only` are available for faster focused runs
- put and call outputs are displayed and saved separately
- option quote collection supports put/call symbols and expected-move strike pruning
- baseline call analyzer and multi-strategy service tests exist
- call ranking now has its own strategy-aware profile, calibration pool, and 52-week extension context
- call ranking has been validated against the first real call-spread output batch

Still needed next:

1. Decide whether optional runtime polish is worth doing before strategy selection.
2. Reevaluate whether more shared analyzer mechanics should move into a dedicated shared engine.
3. Add the market-context selector after call generation and scoring are stable.
4. Expand analytics and ML so later tuning can use strategy-specific history.

## High-Level Outcome

When this roadmap is complete, we should be able to:

- run the existing screener and independently evaluate `put credit spreads` and `call credit spreads`
- output separate opportunity sections for each strategy
- log strategy-tagged candidate data without mixing call and put semantics
- score each strategy appropriately within its own framework
- later add a market-aware selector that decides when puts, calls, or both should be favored
- extend analytics and ML to evaluate both strategies cleanly

## Non-Goals For The First Delivery

- No immediate cross-strategy "winner-takes-all" ranking
- No immediate rewrite of all analytics to fully unify puts and calls
- No immediate live-trading automation changes beyond screening support
- No attempt to solve the full market-context decision tree before call-spread generation is stable

## Recommended Architecture Direction

The existing code already has reusable pieces, but the current pipeline is still put-first in several places:

- `main.py`
- `services/screener_run_service.py`
- `screener/spread_analyzer.py`
- `analysis/ranking_engine.py`
- `docs/data_contracts.md`

The recommended direction is:

1. Keep the current put strategy working during the refactor.
2. Extract shared spread economics and shared evaluation infrastructure.
3. Create a dedicated call-spread analyzer instead of branching the current put analyzer with many conditional paths.
4. Make logs, outputs, and scoring strategy-aware before combining strategy results.

---

## Milestone 0: Strategy Definition And Data Contract Decisions

### Goal

Lock the v1 definition of the call credit spread strategy before code changes start.

### Deliverables

- written strategy defaults for call credit spreads
- strategy-aware naming rules
- strategy-aware data contract additions
- documented questions and decision log

### File-Level Changes

- Modify `config.py`
  - add call-specific config values if they should diverge from put values
  - reorder the file into shared/general, put-strategy, call-strategy, ranking, and runtime sections
- Modify `docs/data_contracts.md`
  - add strategy identity fields
  - document which fields are strategy-neutral vs strategy-specific
- Modify `docs/ARCHITECTURE.md`
  - update the screener flow from single-strategy to multi-strategy-ready
- Create `docs/CALL_CREDIT_SPREAD_IMPLEMENTATION_ROADMAP.md`
  - this file

### Proposed Data Contract Additions

Add the following columns to `opportunities/opportunity_candidates.csv` and downstream derived datasets:

- `strategy_id`
  - example: `put_credit_spread`, `call_credit_spread`
- `strategy_family`
  - example: `credit_spread`
- `option_side`
  - example: `put`, `call`
- `directional_bias`
  - example: `bullish`, `bearish`, `neutral_to_bullish`, `neutral_to_bearish`
- `short_leg_type`
  - example: `short_put`, `short_call`
- `long_leg_type`
  - example: `long_put`, `long_call`

These fields will make future analytics, scoring calibration, and ML joins much safer.

### Config Structure Recommendation

Recommendation: keep a single `config.py` for now, but reorganize it clearly instead of creating a separate call-only config file.

Recommended section order:

1. shared/general screener settings
2. shared spread evaluation settings
3. put credit spread settings
4. call credit spread settings
5. ranking settings
6. persistence/display/runtime settings

Why this is the better v1 choice:

- shared values stay in one obvious place
- put/call differences remain easy to compare side by side
- `main.py` and service wiring stay simpler
- avoids duplicated config-loading patterns too early

When a separate config module would become worth it:

- if strategy-specific settings grow substantially
- if each strategy gets its own runner with many unique controls
- if you want per-strategy import isolation later, such as `put_config.py` and `call_config.py`

For now, the cleaner move is:

- one `config.py`
- better sectioning
- clear naming such as `PUT_*` and `CALL_*` for strategy-specific variables

### Checklist

- [x] Confirm the call strategy is `call credit spread`
- [x] Confirm short-call target delta should mirror put short-delta in absolute terms
- [x] Confirm long-call target delta should use its own config value
- [x] Confirm width, DTE, earnings handling, and initial universe are shared for v1
- [x] Confirm separate terminal sections and strategy-labeled CSV rows/files for v1
- [x] Lock initial `LONG_CALL_DELTA`
- [x] Update data contracts with strategy identity fields

### Exit Criteria

- defaults are documented
- strategy identity fields are agreed
- config structure direction is agreed
- no open ambiguity remains on initial call-side protection targeting

---

## Milestone 1: Shared Spread Engine Extraction

### Goal

Separate reusable spread-evaluation infrastructure from put-specific strategy logic.

### Why This Matters

If we skip this step, the call-spread feature will likely duplicate large parts of the put analyzer and make the later strategy-selector phase harder to maintain.

### Proposed Refactor Shape

Keep strategy-specific logic separate from shared mechanics:

- shared:
  - numeric helpers
  - bid/ask quality checks
  - credit modeling
  - candidate/rejection/result models
  - common logging helpers
  - common opportunity assembly pieces
- strategy-specific:
  - leg lookup from chain
  - anchor strike selection
  - allowed ITM/OTM movement semantics
  - skew/context calculations
  - delta interpretation
  - ranking preferences

### File-Level Changes

- Modify `screener/spread_models.py`
  - expand typed models to include strategy identity fields
  - add shared structures that both put and call analyzers can use
- Modify `screener/spread_scoring.py`
  - keep reusable economics helpers here
  - generalize leg lookup helpers or move them into new strategy-aware access helpers
- Modify `screener/spread_logging.py`
  - ensure candidate/rejection logging can record strategy identity fields
- Modify `screener/spread_analyzer.py`
  - reduce responsibility to put-specific evaluation logic or turn it into a put strategy implementation
- Create `screener/put_spread_analyzer.py`
  - put-specific analyzer extracted from current `SpreadAnalyzer`
- Create `screener/call_spread_analyzer.py`
  - placeholder or initial skeleton during this phase
- Create `screener/strategy_types.py`
  - enums/constants for strategy ids, option sides, directional bias
- Create `screener/chain_access.py`
  - shared helpers for strike lookup by option side
- Create `screener/shared_spread_engine.py`
  - shared candidate evaluation utilities and common filters where practical

### Checklist

- [x] Preserve current put strategy behavior during initial call rollout
- [~] Extract shared spread economics, models, and logging helpers
- [x] Add call-side leg lookup helpers in shared scoring utilities
- [x] Make candidate logging strategy-aware
- [x] Make rejection tracking fully strategy-aware
- [~] Reevaluate file boundaries for shared, put-specific, and call-specific behavior
- [x] Consider extracting `chain_access.py` and/or `shared_spread_engine.py`

### Exit Criteria

- current put flow still works
- reusable logic has a stable home
- new strategy can be added without copy-pasting the whole analyzer

---

## Milestone 2: Standalone Call Credit Spread Analyzer

### Goal

Build the first working call credit spread evaluator without integrating it into the existing runtime output yet.

### Strategy Semantics To Implement

For v1, the call analyzer should mirror the current put spread structure where sensible:

- find the short-call anchor near the target absolute delta
- choose the long call for width-defined protection
- evaluate candidate shifts around the anchor
- enforce liquidity, fill, and risk/reward filters
- calculate spread economics using the same shared credit model
- return an opportunity payload in the same broad shape as the put analyzer, but strategy-tagged

### Important Caution

"Inverse" does not mean "identical." The mechanics are similar, but the market context features and ranking behavior should not be assumed to be the same.

### File-Level Changes

- Create `screener/call_spread_analyzer.py`
  - call anchor selection
  - candidate construction for short-call / long-call spreads
  - call-side opportunity assembly
- Modify `screener/chain_access.py`
  - add call lookup helpers such as strike-to-call accessors
- Modify `screener/spread_scoring.py`
  - if needed, rename helpers so they do not imply puts only
- Modify `tests/test_spread_analyzer.py`
  - split put-only tests into `tests/test_put_spread_analyzer.py`
- Create `tests/test_call_spread_analyzer.py`
  - call chain fixtures
  - anchor selection tests
  - shift-selection tests
  - rejection logging tests
  - output-shape tests

### Checklist

- [~] Build call-side chain fixtures with realistic call greeks and quotes
- [x] Confirm short-call delta is treated as absolute value for filtering and ranking inputs
- [x] Confirm long-call width and protection rules for v1
- [x] Log call candidates using the same candidate log schema plus strategy identity
- [x] Keep put and call analyzers independently testable
- [x] Add more call analyzer hardening tests for missing long calls, wide markets, delta bounds, no valid width, and rejection logging

### Exit Criteria

- a standalone call analyzer can evaluate mocked call chains successfully
- tests prove the analyzer works independently from the current main pipeline

---

## Milestone 3: Call-Specific Scoring And Score Normalization

### Goal

Introduce a scoring path for call credit spreads that reuses the framework shape without blindly reusing put-spread assumptions.

### Why This Matters

The current alignment and EV workflow assumes a single strategy universe. If we blend puts and calls too early, scores will become hard to interpret.

### Recommended Scoring Model Split

Use two score layers:

- `strategy_alignment_score`
  - "how attractive is this candidate within its own strategy?"
- `strategy_selection_score`
  - future score for "should we prefer this strategy over other available strategies?"

For now, only the first layer is required for call spreads.

### Reuse vs New Logic

Likely reusable:

- EV-style economics
- liquidity scoring framework
- earnings penalty framework
- fill-quality logic

Likely strategy-specific:

- delta preference curve
- skew interpretation
- extension / overbought context
- distance to 52-week high vs low importance
- any future trend or mean-reversion context

### File-Level Changes

- Modify `analysis/ranking_engine.py`
  - make scoring strategy-aware
  - branch calibration by `strategy_id`
  - avoid mixing put and call selected histories into one calibration distribution
- Modify `config.py`
  - add call-specific ranking weights if needed
  - add strategy-specific delta preference settings if needed
- Create `tests/test_call_spread_scoring.py`
  - verify call-specific alignment behavior
- Modify `tests/test_spread_scoring.py`
  - keep shared economics tests here

### Checklist

- [x] Decide whether call spreads should use separate config weights from day one
- [x] Calibrate call alignment using only call-spread candidates
- [x] Preserve the current put ranking behavior
- [x] Avoid raw cross-strategy score comparisons in v1

### Exit Criteria

- put and call spreads each have interpretable within-strategy scores
- no hidden calibration leakage between strategies

---

## Milestone 4: Runtime Integration With Dual Output Sections

### Goal

Allow `main.py` to run both strategies and print separate opportunity sections:

- `Put Credit Spread Opportunities`
- `Call Credit Spread Opportunities`

### Recommended Integration Approach

Do not duplicate the entire run service. Instead, make the orchestration capable of running multiple strategy analyzers against shared market inputs.

### File-Level Changes

- Modify `services/screener_run_service.py`
  - support multiple analyzers or a strategy runner abstraction
  - collect both put and call option symbols where needed
  - evaluate opportunities per strategy
  - persist outputs cleanly
- Modify `main.py`
  - update header and summary text to be multi-strategy-aware
  - display both strategy sections
- Modify `utils/display.py`
  - display strategy-specific sections
  - ensure tables label opportunity type clearly
- Modify `services/persistence_service.py`
  - decide whether saved opportunity CSVs remain combined or become per-strategy sections/files
- Modify `tests/test_screener_run_service.py`
  - add tests for multi-strategy orchestration

### Integration Decision To Make

Choose one of these output patterns:

1. Combined CSV with `strategy_id` column
2. Separate per-run CSVs by strategy
3. One combined CSV plus optional per-strategy exports

Current v1 implementation:

- combined candidate log with `strategy_id`
- separate opportunity CSVs by strategy
- separate terminal sections for readability

### Checklist

- [x] Update quote collection to support both put and call symbols
- [x] Keep put-only behavior available during rollout with `--puts-only`
- [x] Add call-only runtime path with `--calls-only`
- [x] Print separate opportunity tables by strategy
- [x] Save outputs with strategy identity preserved
- [x] Add integration tests with fake analyzers for both strategies
- [x] Prune option quotes by enabled side and expected-move strike range

### Exit Criteria

- one run can generate put and call opportunity outputs
- outputs are readable and unambiguous
- current put-only and call-only focused runs remain available
- persistence does not lose strategy identity

---

## Milestone 5: Market Context And Strategy Identification

### Goal

Introduce a rule-based market and symbol context layer that identifies how suitable each symbol is for put spreads and call spreads without filtering either strategy yet.

### Recommendation

Start with rules, not ML.

Rule-based logic will be easier to inspect, tune, and debug while the dataset for call spreads is still immature.

Recommended first mode:

- `STRATEGY_SELECTOR_MODE = "identify_only"`

Meaning:

- put and call strategies still both run
- nothing is filtered out by the selector
- each symbol receives a `put_selector_score` and `call_selector_score`
- selector output is descriptive and auditable, not yet a gate
- selector scores are separate from candidate-level `strategy_alignment_score`

Longer-term possible modes:

- `prioritize_only`
- `soft_filter`
- `hard_filter`

### Example Inputs

- broad market regime
  - primary proxies: `SPY` and `QQQ`
  - per-proxy regime labels such as bullish, neutral, extended_bullish, weak
  - combined market summary such as `market_regime_summary`
- symbol extension state
  - near 52-week high
  - upper range
  - mid-range
  - lower range
  - near 52-week low
- symbol-specific context
  - 52-week range position
  - distance to 52-week high
  - distance to 52-week low
  - earnings proximity

### First Implementation Scope

Milestone 5 v1 should score the symbol context, not the individual spread candidate.

That means:

- `strategy_alignment_score`
  - remains candidate-level and strategy-specific from Milestone 3
- `put_selector_score`
  - becomes a symbol-context suitability score for put spreads
- `call_selector_score`
  - becomes a symbol-context suitability score for call spreads

These answer different questions and should remain separate.

Guardrails from the current planning round:

- keep the selector informational only in `v1`
- remain put-first in overall strategy philosophy
- do not treat extension alone as a reason to reject put spreads
- do not treat a near-52-week-high label alone as strong proof for call spreads
- make selector thresholds and score weights easy to tune in config
- tag the first implementation with a selector version such as `selector_version = "v1"`

Agreed taxonomy thresholds for `v1`:

- market regime per proxy:
  - `extended_bullish`: `range_position_52w >= 92` and `distance_to_52w_high_pct <= 3%`
  - `bullish`: `range_position_52w 72-91` and `distance_to_52w_high_pct <= 12%`
  - `neutral`: `range_position_52w 45-71`
  - `weak`: `range_position_52w 25-44`
  - `risk_off`: `range_position_52w 0-24` or `distance_to_52w_low_pct <= 5%`
- combined market summary:
  - use `SPY` and `QQQ` together
  - if regime values differ by `>= 3`, label as `mixed`
  - otherwise classify by the average regime value
- symbol extension:
  - `near_high`: `92-100`
  - `upper_range`: `75-91`
  - `mid_range`: `45-74`
  - `lower_range`: `20-44`
  - `near_low`: `0-19`

Recommended selector fields moving forward:

- `market_regime_spy`
- `market_regime_qqq`
- `market_regime_summary`
- `symbol_extension_bucket`
- `selector_version`
- `put_selector_score`
- `call_selector_score`
- `selector_preferred_strategy`
- `selector_confidence`
- `selector_reason`

### Example First-Pass Logic

- increase `put_selector_score` when:
  - market regime is constructive or neutral
  - symbol is not extremely overextended near the high, but do not over-penalize extension in strong tape
  - symbol is mid-range to modestly strong rather than stretched
- increase `call_selector_score` when:
  - symbol is near the top of its 52-week range using a stricter threshold such as `0.92`
  - symbol extension is elevated
  - market context is not in obvious breakdown mode
- use `selector_preferred_strategy` only as an informational label for now
- allow informational states such as `put`, `call`, `both`, and `none`
- keep both put and call opportunity sections visible regardless of selector outcome

Agreed `v1` selector score construction:

- start `put_selector_score` and `call_selector_score` at `50`
- apply a market-regime adjustment
- apply a symbol-extension adjustment
- apply a staged earnings penalty
- clamp the final score to `0-100`

Agreed `v1` put selector adjustments:

- market:
  - `extended_bullish` -> `+12`
  - `bullish` -> `+15`
  - `neutral` -> `+6`
  - `mixed` -> `0`
  - `weak` -> `-10`
  - `risk_off` -> `-20`
- extension:
  - `near_high` -> `0`
  - `upper_range` -> `+8`
  - `mid_range` -> `+12`
  - `lower_range` -> `-8`
  - `near_low` -> `-22`

Agreed `v1` call selector adjustments:

- market:
  - `extended_bullish` -> `+10`
  - `bullish` -> `+6`
  - `neutral` -> `0`
  - `mixed` -> `-4`
  - `weak` -> `-12`
  - `risk_off` -> `-22`
- extension:
  - `near_high` -> `+18`
  - `upper_range` -> `+8`
  - `mid_range` -> `-2`
  - `lower_range` -> `-14`
  - `near_low` -> `-24`

Agreed staged earnings penalties:

- `post_cycle` or no earnings before expiration -> `0`
- `late_cycle` -> `-6`
  - earnings happens with `0-21 DTE` remaining
- `pre_cycle` -> `-18`
  - earnings happens with `22+ DTE` remaining
- `imminent` -> `-25`
  - earnings within `7 calendar days`

Agreed `v1` preferred-strategy interpretation:

- `call` if `call_selector_score >= put_selector_score + 12`
- `put` if `put_selector_score >= call_selector_score + 6`
- `both` if both are viable and neither clears the preferred-strategy margin
- `none` if both are weak

Agreed `v1` score bands:

- `weak`: `< 45`
- `marginal`: `45-54`
- `viable`: `55-69`
- `strong`: `70+`

Agreed `v1` minimum viability rules:

- use `55` as the minimum viable selector score floor
- if neither score reaches `55`, label the selector state as `none`
- if both scores are `>= 55` and neither side clears the preferred-strategy margin, label as `both`
- treat the `55` floor as an informational suitability floor, not a trade-execution threshold

### File-Level Changes

- Create `services/strategy_selector.py`
  - rule-based market regime classification
  - symbol extension classification
  - put/call selector score output
  - selector explanation text
- Modify `config.py`
  - add selector mode
  - add market regime thresholds for `SPY` and `QQQ`
  - add symbol-extension thresholds
  - add selector confidence / preferred-strategy margin settings
- Modify `services/screener_run_service.py`
  - compute market context once per run
  - compute symbol selector scores before final display
  - attach selector annotations to put and call opportunities
- Modify `utils/display.py`
  - keep current put and call sections
  - add `put_selector_score` and `call_selector_score` to CLI output for information only
- Modify `docs/data_contracts.md`
  - document selector fields for new outputs moving forward
- Create `tests/test_strategy_selector.py`
  - market regime tests
  - symbol extension tests
  - identify-only mode tests
  - explanation and confidence tests

### Checklist

- [ ] Define the first market regime taxonomy
- [ ] Define the first symbol-extension taxonomy
- [x] Decide initial selector mode should be `identify_only`
- [x] Preserve both put and call sections with no selector filtering in v1
- [x] Use `SPY` and `QQQ` as the first market proxies
- [x] Define the first selector output fields
- [x] Decide how to display selector scores in the CLI
  - show `put_selector_score` and `call_selector_score` for information only
- [ ] Persist selector fields for new outputs moving forward without rewriting historical files

### Exit Criteria

- market context can be explained in plain English for each run
- each symbol can be explained in plain English for why put score and call score differ
- selector outputs are visible alongside normal put and call opportunity output
- selector outputs can be audited and tuned without guessing
- selector remains identification-only and does not filter either strategy in v1

---

## Milestone 6: Analytics And ML Expansion

### Goal

Extend the data pipeline so call-spread candidates and outcomes can be analyzed and modeled alongside put spreads without corrupting historical interpretation.

### Recommended Sequencing

1. Make datasets strategy-aware.
2. Build strategy-specific reports first.
3. Add shared comparative reporting second.
4. Attempt unified predictive modeling only after both strategies have enough history.

### File-Level Changes

- Modify `analysis/build_analysis_dataset.py`
  - carry `strategy_id` and related strategy fields through to analysis datasets
- Modify `analysis/build_executed_trade_dataset.py`
  - preserve strategy type for closed-trade joins
- Modify `analysis/build_rejected_candidate_dataset.py`
  - support strategy-aware rejection views
- Modify `analysis/rejected_candidate_review.py`
  - add strategy filters
- Modify `analysis/rejection_diagnostics.py`
  - report rejections by strategy
- Modify `analysis/weekly_report.py`
  - add strategy-sliced summaries
- Modify `ml/build_training_dataset.py`
  - add strategy identity and strategy-specific feature handling
- Modify `services/run_models.py`
  - if needed, expand service result payloads to carry per-strategy outputs
- Add or update tests around dataset generation

### Checklist

- [ ] Add strategy columns to all relevant derived datasets
- [ ] Preserve backward compatibility where possible for old logs
- [ ] Separate training/evaluation slices by strategy in early ML phases
- [ ] Document any required historical backfill or null-handling rules

### Exit Criteria

- reports can segment results by strategy
- ML datasets can train without mixing incompatible call/put assumptions

---

## Suggested Execution Order

1. Milestone 0: strategy definition and data contracts
2. Milestone 1: shared spread engine extraction
3. Milestone 2: standalone call analyzer
4. Milestone 3: call-specific scoring
5. Milestone 4: dual-output runtime integration
6. Milestone 5: market-context strategy selection
7. Milestone 6: analytics and ML expansion

## Rollout Safety Notes

- Do not rewrite the existing put strategy and call strategy in one step.
- Keep the current put flow green while extracting shared pieces.
- Add tests before integrating call spreads into the live runtime path.
- Make candidate logs strategy-aware before generating large amounts of mixed-strategy historical data.

## Open Questions For Sergi

Most of these have now been answered. Keep this section as a planning record and use the `Decision Log` above as the current source of truth.

### Strategy Definition

1. Should the initial call credit spread use the exact same `TARGET_DTE`, `DTE_TOLERANCE`, `PREFERRED_SPREAD_WIDTH`, `FALLBACK_SPREAD_WIDTH`, and `MAX_RISK_REWARD_RATIO` as puts?
   - Recommendation: `yes` for v1 
   YES

2. Should the initial long call protection target mirror the current `LONG_PUT_DELTA` in absolute terms?
   - Recommendation: `yes` for v1
   NO, it will need its own.
   Follow-up decision: use `LONG_CALL_DELTA = 0.08` for now.

3. Should the call strategy use the same earnings handling and penalties as the put strategy at launch?
   - Recommendation: `yes` for v1
   YES

### Universe And Screening

4. Should the initial call credit spread analyzer run on the same screened symbol universe as the put strategy?
   - Recommendation: `yes` for v1, then refine later with strategy-aware prefilters
   YES

5. Should high IV still be the main top-of-funnel screen for call spreads, or do you want any additional "overextension" screen before option-chain evaluation?
   - Recommendation: start with the same high-IV universe and add overextension as a strategy-scoring or selector feature
   YES, same IV universe

### Scoring And Output

6. Do you want call spreads to have their own ranking weights in `config.py` from day one, or should we begin with shared weights and split later?
   - Recommendation: shared framework, separate config namespace available from day one
   Can start with shared but will need its own later.

7. For the first integrated runtime, do you prefer:
   - separate terminal sections with one combined CSV
   - separate terminal sections with separate CSVs
   - both
   - Recommendation: separate terminal sections with one combined CSV tagged by `strategy_id`
   Separate terminal sections with separate CSVs to start. Later we will likely want one combined CSV, but for now keep it separate.

### Strategy Selector

8. In the first selector version, should market context be:
   - a hard gate that suppresses one strategy
   - a soft preference that reorders opportunities
   - both
   - Recommendation: soft preference first, hard gate only after enough review data exists
   Soft preference. We can change this later once it is worked out better, and a hard gate can be implemented much later. Also, a stock can qualify for both strategies if it meets the requirements.

9. Which market-context signals do you want in the very first selector version?
   - Recommendation:
     - broad market trend
     - symbol range position within 52 weeks
     - distance to 52-week high
     - earnings proximity
   All 4 sounds perfect.

## Definition Of Done For The Full Initiative

- call credit spreads can be evaluated reliably
- put and call candidates are logged with clean strategy identity
- both strategies can be displayed in one runtime
- scoring is strategy-aware
- market-context selection exists in an inspectable first version
- analytics and ML can distinguish put and call strategy outcomes cleanly
