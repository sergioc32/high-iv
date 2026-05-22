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
- market-context strategy identification is planned but not fully implemented
- ML modeling is not yet the live decision-maker
- trading remains manual rather than automated

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

- market regime taxonomy is not finalized
- symbol extension taxonomy is not finalized
- selector thresholds are not defined in config
- selector fields are not yet fully persisted into forward outputs
- no selector review loop exists yet in weekly reporting

### Decision Notes From Current Market Behavior

- Many successful recent put-spread trades have occurred while symbols looked extended.
- Because of that, `v1` selector logic should not punish extended names too aggressively on the put side.
- Likewise, a symbol being near a 52-week high is not enough by itself to justify a strong call-spread thesis.
- Examples like `MU` and `INTC` show why the selector should remain informational at this stage rather than prescriptive.

### Implementation Plan

1. Finalize market regime logic using `SPY` and `QQQ`
2. Finalize symbol extension buckets
3. Implement `services/strategy_selector.py`
4. Annotate live opportunities with selector fields
5. Display `put_selector_score` and `call_selector_score` in the CLI
6. Persist selector fields in new outputs going forward

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

- every run has explainable market context
- every symbol with valid opportunities can show both selector scores
- no strategy is filtered yet
- selector fields can be analyzed historically going forward

---

## Initiative 2: Data Foundation And Outcome Labeling

### Goal

Build the datasets needed to support better scoring and ML modeling.

### Why It Matters

Without reliable labels and decision-time features, any model or improved trade score will be weak or misleading.

### What Is Missing

- stronger joins between candidate, selected, executed, and closed-trade data
- execution-quality fields captured consistently
- realized outcome labels defined clearly
- strategy-aware training datasets for both puts and calls
- versioning of scoring and strategy behavior over time

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

1. Audit current analysis datasets for missing decision-time fields
2. Expand executed-trade and closed-trade joins
3. Define canonical labels for ML and score evaluation
4. Persist strategy-aware training features
5. Add weekly and monthly validation reports on data completeness

### Exit Criteria

- selected and executed trades can be tied back to their original candidate context
- outcome labels are defined and reproducible
- puts and calls can be analyzed separately without schema drift

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

1. Freeze the role of `strategy_alignment_score`
2. Define selector-score scale and interpretation
3. Define the first `model_score` target
4. Define the first `trade_score` formula
5. Add reporting that shows score components side by side
6. Backtest score behavior against realized trade outcomes

### Suggested Score Bands

Example only and subject to later tuning:

- `0-59`: ignore
- `60-74`: review only
- `75-84`: strong candidate
- `85+`: potential future automation band

### Exit Criteria

- each score has a clear purpose
- score components can be inspected independently
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

- `ALIGNMENT_SCORE_VERSION` config value
- alignment-version field in relevant outputs
- component-level alignment score fields persisted in the live opportunity flow
- tests covering score version propagation and component persistence

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

- probability of profit
- probability of reaching target before stop
- expected return on risk
- expected PnL

### Recommended Sequencing

1. Build separate put and call training datasets
2. Create baseline models per strategy
3. Compare against heuristic-only performance
4. Add model outputs into reporting
5. Only later consider a unified cross-strategy model

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
