# High IV Phase 1 Playbook

This playbook is the operator workflow for running the system day to day.

It is written for the way the product is actually used now:
- the terminal output is the primary interface
- the CSV files are supporting records
- the analytics layer is for weekly review and strategy improvement, not automatic trading

## Purpose
Use this document as the day-to-day and week-to-week checklist for:
- Finding new spread opportunities
- Managing open positions
- Closing trades based on alerts and risk rules
- Producing weekly analytics for tuning decisions
- Giving another user a clear operating routine even if they are not highly technical

## Daily Workflow

### 1. Morning Start (run once per day)
Checklist:
- [ ] Activate virtual environment
- [ ] Run fresh-day workflow
- [ ] Review open position alerts
- [ ] Review top new opportunities
- [ ] Execute planned opens and closes

Command:
```bash
python main.py --fresh-day
```

What this does:
- Clears stale cache for a clean daily run
- Syncs account positions into open-trade tracking
- Prints open position monitoring section with alerts
- Runs screener and prints `Top Put Spread Opportunities`
- Writes daily opportunity CSV output

Expected outputs:
- Open positions snapshot in trades/trades_open.csv
- New opportunities file in opportunities/
- New review queue file in opportunities_review/ when the market is open and the run is not a test run
- Candidate evaluation log updated in opportunities/opportunity_candidates.csv
- Rejection counters updated in rejections/rejections_tracking.csv

How to use it:
- In `SYNCING OPEN POSITIONS`, review alerts first. That section is for trade management.
- In `Top Put Spread Opportunities`, review only the best current setups. That section is for potential new entries.
- Use the terminal table as the main decision surface.
- Open the CSV only if you need to inspect more rows or verify a detail not shown in the CLI.
- If you plan to record manual accept/skip decisions, update the newest file in `opportunities_review/`.

What the CLI opportunity table is meant to tell you:
- `Premium`: the current expected premium captured by the spread
- `Exp Credit`: the model's expected fill credit
- `Fill %`: how much of the mid-to-natural range the expected fill is capturing
- `Fill Score`: a compact execution-quality score
- `To 52W Hi %`: how close the stock is to its 52-week high
- `52W Pos %`: where the stock sits within its 52-week range
- `EV Score`: the current economics/ranking signal
- `Align Score`: the broader setup-alignment signal

Practical reading guide:
- Higher `Exp Credit`, `Fill %`, and `Fill Score` generally mean better expected execution
- A very low `To 52W Hi %` means price is close to the 52-week high, which can matter for extension risk
- A very high `52W Pos %` means the stock is trading near the top of its yearly range
- `EV Score` and `Align Score` are helpful summaries, but they should not replace judgment
- If a setup looks statistically good but price looks extended, slow down and review it carefully

### 2. Intraday Re-check (optional, can run multiple times)
Checklist:
- [ ] Re-run screener for updated opportunities
- [ ] Re-check alerts if market moved
- [ ] Execute any additional approved actions

Command:
```bash
python main.py
```

What this does:
- Runs screener without the fresh-day cache reset flow
- Shows updated opportunity list and summary

Expected outputs:
- New opportunities output in opportunities/
- Additional candidate rows appended to opportunities/opportunity_candidates.csv

How to use it:
- Use this as a lightweight intraday refresh to see whether better setups appeared

### Review Queue Capture

The review queue is the lightweight file used to record whether you actually wanted to take a surfaced trade.

Location:
- `opportunities_review/review_queue_YYYYMMDD_HHMMSS.csv`

When it is created:
- market must be open
- run must not use `--test-run`

What to edit:
- `decision`
- `decision_reason`
- `decision_note`

Leave all other columns unchanged.

Allowed `decision` values:
- `accepted`
- `skipped`
- `submitted_not_filled`
- `deferred`

Allowed `decision_reason` values:
- `leveraged_etf`
- `unfamiliar_symbol`
- `sector_theme_discomfort`
- `capital_constraint`
- `too_many_similar_positions`
- `fill_concern`
- `earnings_event_concern`
- `delta_concern`
- `manual_risk_override`
- `extended_too_fast`
- `other`

Suggested meaning for `too_many_similar_positions`:
- Use when you already have enough exposure to a similar setup, sector theme, or the same underlying.
- Example: you already have several `ORCL` spreads on and do not want to add more.

Suggested meaning for `delta_concern`:
- Use when the trade technically qualifies, but the short strike feels too close for comfort.
- Example: the delta or strike proximity is tighter than you prefer, even if the spread still passes the screener.

Suggested meaning for `extended_too_fast`:
- Use when the setup technically qualifies, but the underlying has already run too far too quickly for comfort.
- Example: the stock is already up about `10%` and you do not want to initiate a fresh trade there.

Usage rules:
- If `decision = accepted`, `decision_reason` is usually blank.
- If `decision = skipped`, `decision_reason` should usually be filled in.
- If `decision = submitted_not_filled`, `decision_reason` is optional but helpful.
- If `decision = deferred`, `decision_reason` is optional.
- `decision_note` is always optional.

Suggested meaning for `extended_too_fast`:
- Use when the setup technically qualifies, but the underlying has already run too far too quickly for comfort.
- Example: the stock is already up about `10%` and you do not want to initiate a fresh trade there.

### Test Run Mode

If you are only experimenting or validating output and do not want a review queue:

```bash
python main.py --test-run
```

What this does:
- runs the screener normally
- suppresses review-queue creation
- keeps test or exploratory runs from polluting manual decision data

### 3. Position-only Check (when you do not need a full screener run)
Checklist:
- [ ] Sync current open positions
- [ ] Review close candidates and risk alerts

Command:
```bash
python main.py --sync-positions
```

Expected outputs:
- Updated trades/trades_open.csv
- Open-position alert summary in terminal

How to use it:
- Use this for quick position management checks during volatile sessions

## Practical Operator Workflow

If you are using the product the intended simple way, this is the routine:

### Every trading morning
1. Run:
```bash
python main.py --fresh-day
```
2. Read the open-position section first
3. Read the opportunity table second
4. Make manual trade decisions

### During the day if needed
1. Run:
```bash
python main.py
```
2. Compare the updated opportunity list to what you saw earlier
3. Only act if the setup still makes sense after your manual review

### If you only want to manage open trades
1. Run:
```bash
python main.py --sync-positions
```
2. Ignore the screener and focus only on risk, exits, and current positions

## When To Use CSV Files

Most users should not need CSV files during normal daily use.

Use CSV files only when:
- you want more rows than the terminal shows
- you want to compare runs from different times in the day
- you want to inspect analytics or historical trade details
- you want to debug why a trade did or did not appear

The most important CSVs are:
- `opportunities/opportunities_*.csv`: the saved opportunity snapshot for a run
- `opportunities/opportunity_candidates.csv`: the detailed candidate log
- `trades/trades_open.csv`: current open-trade tracking
- `trades/trades_closed.csv`: closed-trade history
- `analysis/analysis_dataset.csv`: joined reporting dataset
- `ml/training_dataset.csv`: model-prep dataset, mainly for analytics and experimentation

## Weekly Workflow

Run this after market close on Friday or over the weekend.

### Recommended One-Command Weekly Closeout
Checklist:
- [ ] Run full closeout command
- [ ] Confirm latest week report generated
- [ ] Confirm catch-up ran only if previous week was missing

Command:
```bash
python analysis/run_weekly_closeout.py
```

What this does:
- Rebuilds `analysis/analysis_dataset.csv`
- Runs `analysis/data_quality_audit.py`
- Rebuilds `ml/training_dataset.csv`
- Runs `ml/training_data_audit.py`
- Runs weekly pipeline for latest completed week (Monday-Sunday)
- Checks if previous week's report exists; if missing, runs previous week too

Expected outputs:
- `analysis/analysis_dataset.csv`
- `ml/training_dataset.csv`
- Latest week report artifacts in `analysis/reports/`
- ML audit artifacts in `ml/reports/`
- Optional catch-up report artifacts for previous week when needed

How to use it:
- Treat this as your default weekly command
- Use the manual steps below only when you want finer control
- This is the best way to review what worked, what failed, and what may need tuning

### 1. Build fresh analysis dataset
Checklist:
- [ ] Rebuild analysis dataset from candidates plus trade outcomes

Command:
```bash
python analysis/build_analysis_dataset.py
```

Expected output:
- analysis/analysis_dataset.csv

How to use it:
- This is the canonical joined dataset used by weekly reporting

How to read the terminal summary from `build_analysis_dataset.py`:
- `Selected candidate direct-match diagnostic (narrow)` starts from `opportunities/opportunity_candidates.csv`
- It compares only selected candidate-log rows against `trades/trades_open.csv` and `trades/trades_closed.csv`
- `exact_match` there means the selected candidate row directly matched the executed trade on symbol, expiration, short strike, and long strike
- `adjusted_match` there means the selected candidate row matched a nearby executed spread instead of the exact logged strikes
- `missing_match` there means the selected candidate row did not directly reconcile in that narrow candidate-to-trade pass
- This narrow section is useful for workflow diagnostics, but it is not the main answer to "did my trades come from opportunities?"

- `Final trade-row reconciliation stats (primary)` is the main answer for actual executed trades
- It reflects the final trade rows written into `analysis/analysis_dataset.csv` after recovery from direct candidate matches, daily opportunity snapshots, and fallback reconciliation
- If this section says `exact_match=37`, `adjusted_match=11`, and `trade_only=8`, that means `48` trades were recovered from stored opportunity context and `8` were not
- For manual trade review, prefer `analysis/executed_trade_dataset.csv` over `analysis/analysis_dataset.csv` because it is one row per trade and easier to inspect

### 2. Optional data quality check
Checklist:
- [ ] Run audit to detect schema drift or bad values

Command:
```bash
python analysis/data_quality_audit.py
```

Expected output:
- Terminal audit summary (no file overwrite required)

How to use it:
- Fix data issues before trusting weekly insights

### 3. Run weekly diagnostics plus report (recommended single command)
Checklist:
- [ ] Run weekly pipeline for your target window
- [ ] Review markdown report and CSV metrics

Command (explicit week window):
```bash
python analysis/run_weekly_pipeline.py --start-date 2026-03-30 --end-date 2026-04-03 --prefix weekly_2026_04_03 --output-prefix weekly_report
```

Command (auto latest completed Monday-Sunday week):
```bash
python analysis/run_weekly_pipeline.py
```

Expected outputs:
- analysis/reports/<prefix>_reason_summary.csv
- analysis/reports/<prefix>_bucket_summary.csv
- analysis/reports/weekly_report_<date>.md
- analysis/reports/weekly_report_<date>.csv

How to use it:
- Use rejection summaries to identify bottlenecks (delta, liquidity, pricing, structure)
- Use weekly_report markdown for decision review (performance, execution alignment, ranking backtest, sensitivity, recommendations)
- Apply changes only through manual approval

## Analytics And ML Workflow

The analytics and ML files are decision-support tools.
They are not part of the required daily trading loop.

### What they are for
- reviewing rejected trades
- reviewing successful and unsuccessful trades
- checking data quality
- preparing for future model work
- monitoring whether the training dataset is becoming large enough and clean enough for experiments

### What they are not for
- automatic trade execution
- automatic strategy changes
- full supervised learning right now

Current state:
- the data foundation is useful
- the analytics are useful right now
- the training dataset is not yet large enough for serious model training

Use the ML split fields like this:
- `train`: oldest data, used to explore ideas and draft scoring changes
- `validation`: middle data, used to see if the idea still holds on newer trades
- `test`: newest data, used as the final untouched check

Important:
- Do not tune ideas on `test`
- Use `test` last
- Right now the split is best used for disciplined analysis, not full model training

### When to run ML commands directly
Most of the time, you do not need to run ML commands separately because the weekly closeout now does that for you.

Run them directly only when:
- you want to refresh `ml/training_dataset.csv` without running the full weekly report flow
- you changed ML dataset logic and want to regenerate the ML outputs only
- you want to rerun the training audit after reviewing or editing the ML dataset

Commands:
```bash
python ml/build_training_dataset.py
python ml/training_data_audit.py
```

## Decision Rules (Operating Discipline)

Daily:
- Close trades flagged by your approved exit policy from open-position sync output
- Open only opportunities you explicitly approve from TOP PUT SPREAD OPPORTUNITIES
- If you re-run intraday, treat results as incremental refreshes, not automatic actions

Weekly:
- Use the report to decide whether to adjust thresholds or keep settings stable
- Prioritize changes supported by:
  - Ranking quality backtest
  - Rejection trend concentration
  - Sensitivity unlock potential
- When entry logic changes materially, bump `STRATEGY_VERSION` in config so new rows are tagged distinctly from historical data
- Keep all strategy changes human-in-the-loop

## File and Data Flow (Phase 1)

Runtime sources:
- opportunities/opportunities_*.csv
- opportunities/opportunity_candidates.csv
- rejections/rejections_tracking.csv
- trades/trades_open.csv
- trades/trades_closed.csv

Weekly analytics products:
- analysis/analysis_dataset.csv
- analysis/reports/*_reason_summary.csv
- analysis/reports/*_bucket_summary.csv
- analysis/reports/weekly_report_<date>.md
- analysis/reports/weekly_report_<date>.csv

ML products:
- ml/training_dataset.csv
- ml/reports/training_data_audit.md
- ml/reports/training_data_audit.csv

## Minimum Cadence Before Phase 2

To keep Phase 1 reliable before moving on:
- [ ] Run morning fresh-day workflow each trading day
- [ ] Keep trades_open.csv synced and acted on daily
- [ ] Keep trades_closed.csv current as trades are exited
- [ ] Produce one weekly report package every week
- [ ] Make only manually approved strategy changes

## Operator Summary

If you only remember one workflow, use this:

### Daily
```bash
python main.py --fresh-day
```

### Weekly
```bash
python analysis/run_weekly_closeout.py
```

The first two commands are the real operating loop.
The weekly closeout command now refreshes both analytics and ML reporting in one pass.
