# Next Phase Scoring, ML, And Auto-Trade Roadmap

## Purpose

This document covers the next major phase after the initial call-credit-spread rollout.

The original call-spread roadmap got us to:

- dual put/call runtime support
- strategy-aware logging and analytics contracts
- call-specific ranking
- separate output and review flows

This roadmap picks up from there and focuses on the next system layers:

1. strategy identification
2. better scoring architecture
3. ML-backed trade evaluation
4. automated execution safeguards and rollout

## Relationship To The Existing Call-Spread Roadmap

Keep [CALL_CREDIT_SPREAD_IMPLEMENTATION_ROADMAP.md](/abs/path/c:/Users/sergi/development/highIV/docs/CALL_CREDIT_SPREAD_IMPLEMENTATION_ROADMAP.md) as the historical implementation record for the call-spread buildout.

Use this document as the active roadmap for the next phase.

For the broader long-term direction behind these phases, also keep
[LONG_TERM_TRADE_SCORE_VISION.md](/abs/path/c:/Users/sergi/development/highIV/docs/Plans/LONG_TERM_TRADE_SCORE_VISION.md)
as the north-star document for what the system is ultimately trying to achieve.

Reasoning:

- the call-spread roadmap is now mostly an implementation history plus a few remaining Milestone 5 and 6 items
- the next phase is broader than call spreads and now applies to the full multi-strategy system
- a new document keeps the future plan cleaner than stretching the original file too far

## Current State

As of this roadmap:

- put credit spreads and call credit spreads both run in the screener
- candidate logs and downstream analytics are strategy-aware
- call spreads have their own ranking profile
- the current `strategy_alignment_score` exists and is useful, but it is still heuristic
- market-context strategy identification is now implemented in `identify_only` mode
- selector fields now flow through live outputs, `analysis_dataset`, `executed_trade_dataset`, and selector-aware reporting
- alignment score versioning and component breakdowns are now persisted in live outputs
- ML modeling is not yet the live decision-maker
- trading remains manual rather than automated

### Completed So Far

- [x] put/call strategy runtime and output separation
- [x] strategy-aware candidate logging and analytics contracts
- [x] call-specific ranking profile
- [x] alignment score hardening and versioning
- [x] identify-only selector implementation
- [x] selector persistence into forward analytics datasets
- [x] selector-aware weekly and trade-outcome reporting

### Still Ahead

- [ ] selector-driven historical review with enough post-rollout history to be meaningful
- [ ] formal `model_score`
- [ ] formal combined `trade_score`
- [ ] decision-policy thresholds
- [ ] automation and broker execution controls

## Target Score Architecture

The long-term scoring system should be layered rather than relying on one single score.

### 1. Strategy Alignment Score

Purpose:

- score the quality of a specific spread candidate within its own strategy

Notes:

- keep this heuristic and interpretable
- do not remove it when ML arrives
- use it as a transparent component and fallback signal

### 2. Strategy Selector Scores

Purpose:

- score how suitable the current symbol and market context are for each strategy

Initial selector scores:

- `put_selector_score`
- `call_selector_score`

Notes:

- these are symbol-context scores, not candidate scores
- they should remain separate from `strategy_alignment_score`
- first version is identify-only, not filtering

### 3. Model Score

Purpose:

- provide a data-backed estimate of trade quality from historical outcomes

Examples:

- probability of profit
- expected return on risk
- expected PnL
- expected drawdown or loss risk

### 4. Trade Score

Purpose:

- combine the heuristic score, strategy suitability, model output, and execution/risk controls into one final action score

High-level shape:

- `trade_score = f(alignment_score, selector_score, model_score, execution_quality, risk_controls)`

## Guiding Principles

- Keep interpretable heuristic scores even after ML is added.
- Start with separate put and call modeling before attempting a unified model.
- Do not let automation outrun validation.
- Prefer forward-only persistence instead of rewriting historical files.
- Make every automated decision auditable.

---

## Initiative 1: Strategy Identification Layer

### Goal

Finish the rule-based identify-only selector so each symbol receives a put-suitability score and a call-suitability score.

### Locked v1 Guardrails

- The system remains put-first in philosophy and expected usage.
- Call-selector logic is informational and exploratory, not a sign that call spreads are preferred over put spreads.
- Selector scores must not filter trades in `v1`.
- Selector scores must be easy to tune in config because current market conditions can create unusual extension behavior.
- Extension should be treated as context, not as a hard veto against put spreads and not as an automatic endorsement of call spreads.
- Call-spread history will mature more slowly than put-spread history, so call selector conclusions should be treated with lower trust early on.
- Add a version label for the selector logic, starting with `selector_version = "v1"`.

### Why It Matters

This becomes the first real strategy-choice layer and eventually an input into model-driven trade scoring.

### What Is Missing

- selector history is still sparse because rollout is recent
- weekly and trade-outcome selector sections are informational but still in rollout mode
- selector-aware recommendations are not implemented yet
- selector-era closed-trade history is not large enough yet to validate usefulness
- always-review symbol handling for strategic names like `SPY`, `QQQ`, and `IWM` is not implemented yet

### Decision Notes From Current Market Behavior

- Many successful recent put-spread trades have occurred while symbols looked extended.
- Because of that, `v1` selector logic should not punish extended names too aggressively on the put side.
- Likewise, a symbol being near a 52-week high is not enough by itself to justify a strong call-spread thesis.
- Examples like `MU` and `INTC` show why the selector should remain informational at this stage rather than prescriptive.

### Implementation Plan

1. Finalize market regime logic using `SPY` and `QQQ` `[x]`
2. Finalize symbol extension buckets `[x]`
3. Implement `services/strategy_selector.py` `[x]`
4. Annotate live opportunities with selector fields `[x]`
5. Display `put_selector_score` and `call_selector_score` in the CLI `[x]`
6. Persist selector fields in new outputs going forward `[x]`
7. Carry selector fields into `analysis_dataset` / `executed_trade_dataset` `[x]`
8. Add selector-aware weekly and trade-outcome review sections `[x]`
9. Add selector-aware recommendation logic once enough selector-era history exists `[ ]`
10. Add an always-review universe for strategic symbols so names like `SPY`, `QQQ`, and `IWM` are analyzed even when they do not naturally surface in the main funnel `[ ]`

### Core Output Fields

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

### Initial v1 Selector Decisions

- Use `put`, `call`, `both`, and `none` as the informational selector states.
- Use a stricter `near_high` threshold of `0.92` for the first pass.
- Penalize put suitability near highs less aggressively than originally proposed.
- Keep call suitability scoring conservative until there is enough closed-trade history to trust it more.

### Agreed v1 Taxonomy Thresholds

#### Market Regime Thresholds

Use `SPY` and `QQQ` independently first, then combine them into a summary regime.

Per-proxy regimes:

- `extended_bullish`
  - `range_position_52w >= 92`
  - and `distance_to_52w_high_pct <= 3%`
- `bullish`
  - `range_position_52w 72-91`
  - and `distance_to_52w_high_pct <= 12%`
- `neutral`
  - `range_position_52w 45-71`
- `weak`
  - `range_position_52w 25-44`
- `risk_off`
  - `range_position_52w 0-24`
  - or `distance_to_52w_low_pct <= 5%`

Combined `market_regime_summary`:

- first map regimes to:
  - `risk_off = 0`
  - `weak = 1`
  - `neutral = 2`
  - `bullish = 3`
  - `extended_bullish = 4`
- if the difference between `SPY` and `QQQ` regime values is `>= 3`, label summary as `mixed`
- otherwise use the average:
  - `>= 3.5` -> `extended_bullish`
  - `>= 2.5` -> `bullish`
  - `>= 1.5` -> `neutral`
  - `>= 0.5` -> `weak`
  - `< 0.5` -> `risk_off`

#### Symbol Extension Thresholds

Use a `0-100` range-position scale for the first selector version:

- `near_high`
  - `92-100`
- `upper_range`
  - `75-91`
- `mid_range`
  - `45-74`
- `lower_range`
  - `20-44`
- `near_low`
  - `0-19`

Interpretation notes:

- for put spreads, `upper_range` and `near_high` should only create a mild penalty in `v1`
- for call spreads, `near_high` is informative but not sufficient by itself to imply a strong trade thesis
- these thresholds are informational only in `v1` and should be easy to tune in config

### Agreed v1 Score Composition

Use a simple additive scoring model for both selector scores:

- start each selector score at `50`
- apply a market-regime adjustment
- apply a symbol-extension adjustment
- apply a staged earnings penalty
- clamp the final result to `0-100`

Reasoning:

- symbol extension should matter more than market regime
- the selector must remain informational only in `v1`
- the current tape shows that extended symbols can still produce strong put-spread outcomes, so extension should not become a hard anti-put signal

#### Put Selector Score

Start at `50`.

Market adjustment:

- `extended_bullish` -> `+12`
- `bullish` -> `+15`
- `neutral` -> `+6`
- `mixed` -> `0`
- `weak` -> `-10`
- `risk_off` -> `-20`

Extension adjustment:

- `near_high` -> `0`
- `upper_range` -> `+8`
- `mid_range` -> `+12`
- `lower_range` -> `-8`
- `near_low` -> `-22`

Interpretation:

- keep the put-side penalty near highs intentionally mild in `v1`
- favor constructive or neutral tape plus symbols that are not near breakdown

#### Call Selector Score

Start at `50`.

Market adjustment:

- `extended_bullish` -> `+10`
- `bullish` -> `+6`
- `neutral` -> `0`
- `mixed` -> `-4`
- `weak` -> `-12`
- `risk_off` -> `-22`

Extension adjustment:

- `near_high` -> `+18`
- `upper_range` -> `+8`
- `mid_range` -> `-2`
- `lower_range` -> `-14`
- `near_low` -> `-24`

Interpretation:

- call scores should depend meaningfully on extension
- near-high context should help call suitability, but not so much that it overwhelms all other context

### Agreed v1 Earnings Penalty

Use staged earnings treatment similar to the current approach, with emphasis on where earnings fall relative to the likely trade lifecycle.

Recommended stages:

- `post_cycle` or no earnings before expiration -> `0`
- `late_cycle`
  - earnings happens with `0-21 DTE` remaining
  - penalty: `-6`
- `pre_cycle`
  - earnings happens with `22+ DTE` remaining
  - penalty: `-18`
- `imminent`
  - earnings within `7 calendar days`
  - penalty: `-25`

Interpretation:

- if earnings is likely to occur after the trade would often be closed, the penalty should be lighter
- if earnings is likely to occur while the trade is still expected to be open, the penalty should be much more severe
- imminent earnings should be the strongest warning

### Agreed v1 Preferred Strategy Interpretation

This remains descriptive only in `v1`.

- `call`
  - if `call_selector_score >= put_selector_score + 12`
- `put`
  - if `put_selector_score >= call_selector_score + 6`
- `both`
  - if both scores are reasonably viable and neither side clears the preferred-strategy margin
- `none`
  - if both scores are weak

Interpretation:

- keep a modest built-in put bias when assigning the descriptive preferred strategy
- do not distort the raw selector scores too much just to force that bias
- let the asymmetry live mostly in the descriptive interpretation layer

### Agreed v1 Score Bands And Viability Floors

Use the following descriptive score bands:

- `weak`
  - `< 45`
- `marginal`
  - `45-54`
- `viable`
  - `55-69`
- `strong`
  - `70+`

Interpretation:

- `weak` means the symbol/context does not support the strategy well
- `marginal` means the score is informative but not strong enough to treat the strategy as a preferred idea
- `viable` is the minimum floor for a strategy to count as realistically suitable
- `strong` means the symbol/context is clearly favorable for that strategy

### Agreed v1 State Logic

Use these rules for the informational `put/call/both/none` state:

- `none`
  - if both scores are `weak`
  - or if neither score reaches the minimum viable floor of `55`
- `put`
  - if `put_selector_score >= 55`
  - and `put_selector_score >= call_selector_score + 6`
- `call`
  - if `call_selector_score >= 55`
  - and `call_selector_score >= put_selector_score + 12`
- `both`
  - if both scores are `>= 55`
  - and neither side clears the preferred-strategy margin

Notes:

- this keeps `none` available for situations where both strategies really are poor fits
- this also prevents a mildly positive but still weak score from being labeled as a preferred strategy
- the `55` floor is a minimum viability threshold, not a trading threshold

### Exit Criteria

- [x] every run has explainable market context
- [x] every symbol with valid opportunities can show both selector scores
- [x] no strategy is filtered yet
- [x] selector fields can be analyzed historically going forward
- [ ] enough selector-era history exists for meaningful selector-vs-outcome review

---

## Initiative 2: Data Foundation And Outcome Labeling

### Goal

Build the datasets needed to support better scoring and ML modeling.

### Why It Matters

Without reliable labels and decision-time features, any model or improved trade score will be weak or misleading.

### What Is Missing

- selector-era history is still shallow in the closed-trade layer
- execution-quality fields are only partially populated across older history
- realized outcome labels defined clearly
- strategy-aware training datasets for both puts and calls need continued growth
- score-version history exists, but model-version history does not yet

### Required Dataset Layers

#### Decision-Time Features

- strategy identity
- symbol
- DTE
- width
- short delta
- skew metrics
- EV metrics
- liquidity metrics
- risk/reward
- earnings context
- market regime
- selector scores
- 52-week range context

#### Execution Fields

- expected credit
- natural credit
- actual fill
- fill slippage
- order timestamp
- trade size

#### Outcome Labels

- realized PnL
- realized return on risk
- profitable or not
- hit target or not
- days held
- exit reason

#### Nice-To-Have Later

- max adverse excursion
- max favorable excursion
- intratrade drawdown

### Implementation Plan

1. Audit current analysis datasets for missing decision-time fields `[x]`
2. Expand executed-trade and closed-trade joins `[x]`
3. Define canonical labels for ML and score evaluation `[ ]`
4. Persist strategy-aware training features `[partial]`
5. Add weekly and monthly validation reports on data completeness `[partial]`

### Exit Criteria

- [x] selected and executed trades can be tied back to their original candidate context
- outcome labels are defined and reproducible
- [x] puts and calls can be analyzed separately without schema drift

---

## Initiative 3: Score Architecture Redesign

### Goal

Move from a single heuristic alignment score into a layered scoring framework.

### Why It Matters

The current `strategy_alignment_score` is useful, but it is carrying too much responsibility by itself.

### Recommended Score Stack

#### Alignment Score

- candidate quality within strategy

#### Selector Scores

- strategy suitability for the symbol and market context

#### Model Score

- outcome estimate from historical data

#### Trade Score

- final decision score used for review, ranking, and eventually automation

### What Is Missing

- formal definitions for each score
- normalization rules between scores
- score-combination rules
- confidence weighting
- score-band policy for review vs action

### Implementation Plan

1. Freeze the role of `strategy_alignment_score` `[x]`
2. Define selector-score scale and interpretation `[x]`
3. Define the first `model_score` target `[ ]`
4. Define the first `trade_score` formula `[ ]`
5. Add reporting that shows score components side by side `[partial]`
6. Backtest score behavior against realized trade outcomes `[ ]`

### Suggested Score Bands

Example only and subject to later tuning:

- `0-59`: ignore
- `60-74`: review only
- `75-84`: strong candidate
- `85+`: potential future automation band

### Exit Criteria

- [x] each score has a clear purpose
- [x] score components can be inspected independently
- the final `trade_score` is more predictive than alignment score alone

### First Implementation Slice: Alignment Score Hardening

Before implementing selector scoring or model scoring, the first score-architecture task should be to harden and instrument the existing `strategy_alignment_score` rather than redesign it immediately.

#### Why Start Here

- `strategy_alignment_score` already exists and is strategy-aware
- it is already used in runtime scoring, reporting, and ranking
- changing too many score layers at once would make it harder to understand which change improved or degraded results
- better observability is more valuable right now than immediate formula churn

#### What To Do First

1. Freeze the role of alignment score
   - keep it candidate-level only
   - do not mix selector logic into it
   - do not let it become a substitute for strategy suitability scoring

2. Add alignment score versioning
   - add something like `ALIGNMENT_SCORE_VERSION = "v1"` in config
   - carry that value into outputs and downstream datasets
   - make it possible to compare scoring behavior across future revisions

3. Persist alignment component breakdowns in live outputs
   - delta component
   - skew component
   - EV component
   - liquidity component
   - extension component
   - directional adjustment
   - earnings adjustment

4. Keep earnings inside alignment score for now
   - do not move earnings treatment between score layers yet
   - keep the current alignment-level earnings logic stable until selector scoring is added

5. Add tuning visibility
   - make daily outputs and reports show the component values clearly enough for review
   - make it easy to compare high-score trades versus realized outcomes later

6. Only then consider formula refinement
   - after instrumentation is in place
   - after we can compare recent runs without guessing

#### First Implementation Deliverables

- `ALIGNMENT_SCORE_VERSION` config value `[x]`
- alignment-version field in relevant outputs `[x]`
- component-level alignment score fields persisted in the live opportunity flow `[x]`
- tests covering score version propagation and component persistence `[x]`

#### Non-Goals For This Slice

- do not redesign the full alignment formula yet
- do not introduce selector scores into trade ranking yet
- do not introduce ML into scoring yet
- do not change trade filtering behavior

---

## Initiative 4: ML Modeling

### Goal

Add data-backed modeling to improve trade evaluation and future strategy selection.

### Why It Matters

ML should help us move from good heuristics to measurable predictive edge, but only after the data foundation is solid.

### What Is Missing

- enough closed-trade history by strategy
- stable target labels
- training dataset generation for both strategies
- evaluation framework for model calibration and drift

### Modeling Principles

- start with separate put and call models
- compare against heuristic baselines
- optimize for calibration and practical value, not just accuracy
- keep model outputs explainable enough for review

### Candidate Model Targets

Primary first target:

- expected return on risk

Secondary companion targets:

- probability of profit
- probability of reaching target before stop
- expected PnL

### Locked First `model_score` Decision

The first live `model_score` should be based on:

- `expected_return_on_risk`

Reasoning:

- it maps well to spread trading decisions
- it is more informative than a simple win/loss label
- it connects naturally to later `trade_score` construction
- it lets us compare trades with different credits and widths on a normalized basis

The first `model_score` should not try to replace the heuristic score stack.
Instead, it should become one additional component alongside:

- `strategy_alignment_score`
- `put_selector_score` / `call_selector_score`
- execution-quality and risk-control checks

### First Modeling Shape

Start with a strategy-specific regression-style prediction target:

- put model predicts expected return on risk for put credit spreads
- call model predicts expected return on risk for call credit spreads

Then derive a normalized `model_score` from that prediction for downstream use.

Recommended first outputs:

- `predicted_return_on_risk`
- `model_score`
- `model_score_version`

Recommended auxiliary outputs for later comparison:

- `predicted_pop`
- `predicted_hit_target_prob`

### Canonical First Label Definition

Use realized return on risk as the primary label:

- `realized_return_on_risk = realized_pnl / max_loss_at_entry`

Canonical denominator decision:

- use `max_loss_at_entry` as the first and only denominator for the initial model target
- do not mix `buying_power_used` and `max_loss_at_entry`
- do not fall back between multiple risk denominators in the first model version

Reasoning:

- `max_loss_at_entry` is more aligned with defined-risk spread structure
- it should be more historically consistent than broker/account-specific buying power usage
- one canonical denominator keeps the target easier to interpret and trust
- `buying_power_used` can remain available later as a separate execution or account-context feature if needed

Label handling notes:

- closed trades only for supervised training
- keep open trades out of the first training target
- preserve sign, so losing trades remain negative
- wins and losses should both stay in the regression target rather than being clipped

### First Feature Groups

The first model should use only decision-time or entry-time fields, not future leakage.

Core candidate-quality features:

- `short_delta`
- `dte`
- `width`
- `premium`
- `premium_per_width`
- `risk_reward_ratio`
- `ev_score`
- `short_iv`
- `atm_iv`
- `skew_ratio`
- `skew_diff`
- `fill_quality`
- `fill_quality_score`
- `avg_width_pct`
- `credit_mid`
- `credit_natural`
- `credit_expected`

Context features:

- `range_position_52w`
- `distance_to_52w_high_pct`
- `distance_to_52w_low_pct`
- `market_regime_summary`
- `symbol_extension_bucket`
- `put_selector_score`
- `call_selector_score`
- `selector_preferred_strategy`
- `selector_confidence`
- `earnings_within_dte`
- `selector_earnings_stage`
- `selector_earnings_penalty`

Versioning and regime tracking:

- `strategy_id`
- `strategy_version`
- `alignment_score_version`
- `selector_version`

Optional early exclusions:

- exclude rows with very poor label quality
- exclude rows with missing core fields required for the first model

### First-Pass ML Dataset Definition

This section defines the initial training dataset contract for the first `model_score`.

#### Training-Row Inclusion Rules

Include only rows that meet all of the following:

- closed trades only
- valid `profit_loss`
- valid `max_loss_at_entry`
- tied back to reviewed trade context
- sufficient entry-time feature coverage for the first model

Recommended first inclusion statuses:

- include:
  - `exact_match`
  - `adjusted_match`
- exclude initially:
  - `trade_only`

Reasoning:

- the first model should prioritize training-label trust over dataset size
- `trade_only` rows can still be useful later, but they are weaker for the first supervised model because their decision-time context is less certain

#### Canonical Input Rule

Use only information that was known at trade entry.

This means:

- include decision-time and entry-time context
- do not include future-outcome fields as predictors
- do not include fields that depend on how the trade later behaved

Examples of fields that should stay out of the feature set:

- `days_held`
- `profit_loss`
- `annualized_return`
- `profit_pct_of_max`
- any exit-time or post-entry lifecycle field

#### Primary Label

The first supervised target should be:

- `realized_return_on_risk = realized_pnl / max_loss_at_entry`

This is the main quantity the first `model_score` should learn to predict.

#### Secondary Evaluation Metrics

The first model should still be judged with time-aware and practical trade metrics, even though those are not input features.

Track at least:

- `days_held`
- `annualized_return`
- `profit_pct_of_max`

Reasoning:

- a trade that earns the same return in fewer days is more useful
- time-to-outcome matters operationally even if it is not the first prediction target
- these metrics help us see whether the model is ranking efficient trades or just eventual winners

#### First Derived Distance Features

Include strike-distance context where available or easily derivable:

- `distance_to_short_strike_points`
- `distance_to_short_strike_pct`
- `distance_to_short_strike_std` if it can be computed cleanly from existing data

Reasoning:

- these help normalize how aggressive or conservative the entry was
- they reflect how far the short strike sat from current price in more meaningful ways than raw strike alone

#### Future Feature Backlog

These are good candidates for later expansion but should not block the first model:

- same-day price change %
- whether the stock was red or green at entry
- intraday extension / mean-reversion context
- realized move vs expected move
- richer standard-deviation distance context if not already available

Reasoning:

- these could capture entry-timing edge that matters in practice
- they are useful ideas, but the first model should start with the strong feature set already available rather than waiting for perfect context

#### First Modeling Philosophy

Keep the first model intentionally simple and trustworthy:

- prioritize clean labels over maximum row count
- prioritize understandable features over feature sprawl
- use secondary evaluation to judge trade efficiency, not just raw return
- grow feature richness after the first baseline is stable

### First Modeling Constraints

- start with separate put and call models
- do not train one unified model yet
- require closed trades only
- use label-quality weighting when available
- compare against a simple baseline before trusting the model
- avoid using fields that were computed after trade entry

### First Baseline Comparisons

Before trusting the model, compare it against:

- `strategy_alignment_score` alone
- selector scores alone
- a simple heuristic blend like:
  - alignment + selector suitability

The first question is not whether the model is perfect.
The first question is whether it adds measurable value over the current heuristic stack.

### First `model_score` Interpretation

The first `model_score` should be a normalized representation of expected return on risk.

Recommended first interpretation:

- higher `model_score` means the historical pattern suggests better expected return on risk
- lower `model_score` means historically weaker expected trade quality

Recommended first output scale:

- `0-100`

But keep the raw prediction too:

- `predicted_return_on_risk`

That way we retain both:

- an interpretable model output
- a normalized score usable in later `trade_score`

### How `model_score` Feeds Future `trade_score`

The eventual `trade_score` should combine:

- alignment score
- selector score
- model score
- execution quality
- hard risk gates

High-level shape:

- `trade_score = f(alignment_score, selector_score, model_score, execution_quality, risk_controls)`

Interpretation:

- `alignment_score` says whether the spread itself looks structurally strong
- selector scores say whether the strategy fits the current market/symbol context
- `model_score` says what similar trades have actually tended to return
- `trade_score` says whether the full setup should be acted on

### Recommended Sequencing

1. Freeze the first label as `expected_return_on_risk`
2. Build separate put and call training datasets
3. Create baseline models per strategy
4. Compare against heuristic-only performance
5. Add raw predicted return on risk into reporting
6. Add normalized `model_score` into reporting
7. Only later consider a unified cross-strategy model

### Evaluation Areas

- calibration
- out-of-sample stability
- feature drift
- score usefulness in top-ranked trades
- incremental value over heuristic scoring

### Exit Criteria

- at least one model materially improves trade ranking or outcome prediction
- model behavior is stable enough for forward use
- model output can be incorporated into `trade_score`

### Immediate Next Implementation Slice

1. Freeze the first target:
   - `expected_return_on_risk`
2. Audit whether `buying_power_used` is complete enough to support a stable label
3. Define the exact training-row inclusion rules
4. Define the first model output fields:
   - `predicted_return_on_risk`
   - `model_score`
   - `model_score_version`
5. Build the first baseline evaluation report

---

## Initiative 5: Trade Decision Policy

### Goal

Define how the system converts scores into practical decisions.

### Why It Matters

Even a strong model is not enough without clear decision policy, thresholds, and safety gates.

### What Is Missing

- formal trade-score thresholds
- confidence requirements
- explicit minimum safety gates
- rules for when a score is informative versus actionable

### Required Decision Layers

#### Review Layer

- a trade is visible and explainable

#### Candidate Layer

- a trade is strong enough for active consideration

#### Execution-Eligible Layer

- a trade meets all score and safety requirements

### Implementation Plan

1. Define minimum score bands
2. Define required confidence for each band
3. Define non-negotiable execution gates
4. Add reports showing how many trades pass each layer
5. Validate thresholds in paper-trade style review

### Exit Criteria

- every opportunity can be categorized into a policy band
- score thresholds can be tested before automation is enabled

---

## Initiative 6: Automated Execution

### Goal

Allow the script to place trades automatically only when a trade meets strict score and risk requirements.

### Why It Matters

Auto-trading should be the last step in the chain and should rely on validated scoring plus hard safety controls.

### Required Hard Requirements

The user has already identified these as core requirements:

- no earnings window
- minimum liquidity
- max total exposure
- acceptable risk/reward
- minimum available option buying power in the account

### Additional Recommended Hard Requirements

- max open positions
- max exposure per symbol
- max exposure per strategy
- stale-quote protection
- minimum trade confidence
- kill switch
- paper-trade mode before live mode

### Automation Rollout Stages

1. Manual only
2. Generate order ticket only
3. Paper-trade auto-execution
4. Small-size live auto-execution
5. Scaled live auto-execution

### What Is Missing

- broker execution service for real order placement
- dry-run and paper-trade support
- account-state checks
- buying-power checks
- position and exposure controls
- order audit logging
- failure recovery and retry policy

### Implementation Plan

1. Build a broker execution abstraction
2. Add dry-run and paper-trade modes
3. Add account-state and buying-power checks
4. Add position sizing and exposure controls
5. Add audit logging for every auto-trade decision
6. Gate live automation behind score thresholds and paper validation

### Exit Criteria

- no automated order can be placed without all hard requirements passing
- every automated decision is logged and explainable
- paper mode is stable before live mode is enabled

---

## What Is Missing By Major Goal

### To Reach Better Strategy Selection

- finish identify-only selector
- persist selector fields
- collect enough selector-vs-outcome history to evaluate usefulness

### To Reach Better Scoring

- formal layered score architecture
- score normalization
- more outcome-linked validation

### To Reach Reliable ML

- more closed-trade history
- stronger labels
- strategy-separated training workflows

### To Reach Safe Auto-Trading

- validated `trade_score`
- account-aware safety gates
- execution service
- paper validation

---

## Suggested Execution Order

1. Finish strategy identification
2. Strengthen analysis and training datasets
3. Redesign score architecture
4. Build and evaluate first ML models
5. Define trade decision policy and thresholds
6. Add paper-trade automation
7. Add tightly controlled live automation

## Open Questions

These do not block keeping this roadmap, but they will matter before implementation:

1. What should the first `model_score` predict?
   - probability of profit
   - expected return on risk
   - both

2. What should count as a successful trade for threshold setting?
   - raw profitability
   - target-hit probability
   - return-on-risk threshold

3. How much closed-trade history do we want before trusting call-side models?

4. Should future automation place one-lot starters first, or use dynamic sizing from day one?

5. What minimum option buying power floor should be enforced before any automated order can be sent?

## Recommended Next Planning Step

Before coding this phase, the next planning pass should define:

1. the selector taxonomy and thresholds
2. the first model target
3. the first `trade_score` formula
4. the minimum auto-trade safety gates and thresholds
