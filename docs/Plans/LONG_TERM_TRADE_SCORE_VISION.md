# Long-Term Trade Score Vision

## Purpose

This document is the long-term north star for the system.

It is not just about building another score.
It is about building a decision framework that helps answer:

- Is this a good trade?
- Is this a trade I should actually take?
- Is this trade realistically fillable?
- Am I filtering out a trade I should have kept?
- Am I skipping a trade because of good judgment, or because of avoidable bias/fear?

This should stay separate from the shorter implementation roadmaps so the broader goal does not get lost while we work through smaller phases.

## What Success Means

The real goal is not just to predict return on risk from already executed trades.

The real goal is to produce a trusted trade score that helps:

- find the right trade
- favor trades that fit the actual strategy and risk style
- identify trades that are realistically fillable
- reduce missed good opportunities
- reduce discretionary mistakes
- support eventual safe automation

The score does not need to be perfect.
It needs to be good enough to improve decision quality and maintain strong overall returns over time.

## Current Reality

What already works well:

- the put-spread strategy is producing useful opportunities
- recent monthly returns have been strong
- the current output plus human judgment is producing good trade selection
- the system already captures many of the rules that previously required manual research
  - high IV
  - acceptable risk/reward
  - decent fill potential
  - spread structure quality

What is still missing:

- not every surfaced opportunity is one that should actually be traded
- the system does not yet understand discretionary skip reasons well
- fillability is still only partially modeled
- rejected opportunities are not yet modeled as possible future recovery opportunities
- the current ML work only sees executed trades, which creates selection bias

## Important Constraint: Capital Matters

The account size matters and should shape the system.

Current practical constraints:

- the account started around `$5k`
- some days produce far more opportunities than can actually be traded
- even with automation, trade count must stay constrained

Long-term automation policy assumptions:

- at most `1` automated trade per day
- only if account option buying power is at least `50%`
- hard capital and exposure controls should stay above opportunity count

This means the long-term score is not just a ranking tool.
It is also a capital-allocation tool.

## The Real Decision Problem

There are at least five separate questions in play:

### 1. Trade Quality

Does the setup itself look structurally strong?

This is where things like:

- alignment score
- selector scores
- return-on-risk modeling
- market context
- spread economics

all belong.

### 2. Trade Acceptance

Is this a trade the account owner should actually want to take?

Examples:

- `SOXL` may meet the math but still feel wrong because it is a `3x` semiconductor ETF
- `COIN` may be acceptable while other crypto-related names are not
- unknown or unfamiliar names may create hesitation even if the setup looks statistically fine

This is not noise.
This is a real part of the decision process.

The long-term system should help answer:

- Am I right to skip this?
- Am I making a mistake by skipping it?
- Is the math stronger than my discomfort?

### 3. Fillability

Can the trade actually be entered at a reasonable price?

This matters because:

- some trades look good but are hard to fill
- some trades do not fill quickly enough to matter
- some trades would work, but not at the target credit

This should eventually become its own modeled concept, not just a side note.

### 4. Rejected Opportunity Recovery

Did the system filter out a trade that would have been good?

This matters because:

- many symbols are rejected before final ranking
- some of those rejected opportunities may actually be worth revisiting
- the rejected dataset exists partly to help us learn where filters are too strict

### 5. Always-Review Symbols

Are there symbols that should be analyzed consistently even if they rarely surface through the normal screening funnel?

This matters because:

- some symbols are strategically more desirable than the average stock
- broad index ETFs are often more familiar, more liquid, and less idiosyncratic than single names
- symbols like `SPY`, `QQQ`, and `IWM` may be important enough that they should almost always be reviewed

This is not the same thing as forcing a trade.
It is about guaranteeing analysis coverage for a small strategic universe.

## Long-Term Score Architecture

The eventual system should likely be layered, not one single monolithic score.

### 1. Strategy Alignment Score

Purpose:

- candidate-quality score within a strategy

Role:

- heuristic
- interpretable
- trusted baseline

### 2. Strategy Selector Scores

Purpose:

- symbol and market-context suitability for put vs call

Role:

- context score
- separate from candidate quality

### 3. Trade Quality Model

Purpose:

- predict likely economic quality of the trade

Examples:

- expected return on risk
- probability of profit
- probability of acceptable outcome within target hold window

### 4. Trade Acceptance Model

Purpose:

- predict whether a setup is one that should actually be taken

This should eventually learn from:

- trades taken
- trades skipped
- explicit skip reasons
- instrument-type preferences
- known discomfort areas

### 5. Fillability Model

Purpose:

- predict whether the trade is realistically fillable at an acceptable price

### 6. Rejected-Opportunity Recovery Model

Purpose:

- identify filtered-out setups that may have been mistakes to reject

### 7. Always-Review Universe Layer

Purpose:

- guarantee regular analysis coverage for strategically important symbols like `SPY`, `QQQ`, and `IWM`

This layer should answer:

- was the symbol reviewed today?
- did it produce a valid put spread, call spread, both, or neither?
- if not, why not?

### 8. Final Trade Score

Purpose:

- combine the layers above into a final decision score

High-level shape:

- `trade_score = f(alignment, selector, quality_model, acceptance_model, fillability, risk_controls)`

## What The Trade Acceptance Layer Really Means

This is one of the most important long-term ideas.

The current gap is not just:

- Which trades made money?

The deeper gap is:

- Which trades should have been taken?
- Which trades were skipped correctly?
- Which trades were skipped incorrectly?

That means trade acceptance is partly about:

- risk preference
- instrument familiarity
- policy
- bias correction

Some examples may become explicit features or policy flags:

- `is_leveraged_etf`
- `is_crypto_related`
- `is_index_etf`
- `sector`
- `industry`
- `is_familiar_name`
- `is_high-volatility-theme`

Not all of these should necessarily be hard filters.
Some should remain features or soft penalties.

## Role Of Sector And Industry

Sector and industry are not absolute deal breakers, but they matter.

Examples:

- some crypto exposure may be acceptable
- unfamiliar or unstable crypto-adjacent names may not be
- unknown themes may create discomfort even when the setup looks mathematically acceptable

The system should treat sector and industry as:

- meaningful context
- not universal disqualifiers
- useful inputs for later trade-acceptance modeling

## Why Executed-Trade ML Alone Is Not Enough

Executed trades are useful, but they are not the whole truth.

They are influenced by:

- current screener output
- human review
- discretion
- comfort level
- capital limits

That means executed-trade history is inherently selection-biased.

This does not make it bad.
It just means:

- outcome modeling alone will not solve the whole problem
- some future labels need to come from skipped trades and rejected opportunities too

## Long-Term Data We Need To Capture Better

### For Trade Quality

- entry-time features
- selector context
- alignment context
- realized outcomes

### For Trade Acceptance

- whether an opportunity was taken or skipped
- explicit skip reason when available
- comfort flags like leveraged ETF / unfamiliar instrument

### For Fillability

- submitted price
- filled price
- did not fill
- time to fill
- price improvement or slippage

### For Rejected Recovery

- final rejection reason
- whether similar rejected setups later would have worked
- whether filters are too strict in specific buckets

### For Always-Review Symbols

- whether the symbol belongs to the always-review universe
- whether it produced a valid put setup, call setup, both, or neither
- why it failed if it did not produce a setup
- how often always-review symbols result in near-miss setups versus selected trades
- whether always-review symbols perform differently from the broader screened universe

## Guiding Principles

- Keep building toward trust, not just complexity.
- Do not expect one model to solve every part of the decision process.
- Treat discretionary judgment as data, not as a nuisance.
- Capital constraints are real and should shape the system.
- Prefer explicit policy where appropriate rather than forcing everything into ML.
- Build enough instrumentation that skipped trades and unfilled trades become learnable.

## Practical Long-Term Milestones

### Stage 1

- strong heuristic alignment score
- selector scores
- trade quality baseline modeling

### Stage 2

- capture skipped-trade reasons
- capture fill attempts and fill outcomes
- add acceptance and fillability features

### Stage 3

- build trade-acceptance model
- build fillability model
- analyze rejected-opportunity recovery
- add always-review handling for strategic symbols like `SPY`, `QQQ`, and `IWM`

### Stage 4

- combine into a trusted `trade_score`
- validate score bands against real outcomes

### Stage 5

- paper-trade or tightly constrained automation
- max `1` automated trade per day
- minimum `50%` option buying power requirement
- all hard risk gates enforced

## Final Framing

This is a long-term system-building effort.

The goal is not:

- perfect prediction

The goal is:

- better trade selection
- fewer avoidable mistakes
- higher trust in decisions
- better use of limited capital
- eventually, safe automation with strong guardrails

If the system can reliably help separate:

- good trades from weak ones
- acceptable trades from uncomfortable but statistically valid ones
- fillable trades from impractical ones
- truly bad rejects from accidentally missed opportunities
- and make sure strategically important symbols are consistently analyzed

then it will be doing exactly what it is supposed to do.
