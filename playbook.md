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
- Candidate evaluation log updated in opportunities/opportunity_candidates.csv
- Rejection counters updated in rejections/rejections_tracking.csv

How to use it:
- In `SYNCING OPEN POSITIONS`, review alerts first. That section is for trade management.
- In `Top Put Spread Opportunities`, review only the best current setups. That section is for potential new entries.
- Use the terminal table as the main decision surface.
- Open the CSV only if you need to inspect more rows or verify a detail not shown in the CLI.

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
- Runs weekly pipeline for latest completed week (Monday-Sunday)
- Checks if previous week's report exists; if missing, runs previous week too

Expected outputs:
- `analysis/analysis_dataset.csv`
- Latest week report artifacts in `analysis/reports/`
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

### Optional ML / training audit
```bash
python ml/build_training_dataset.py
python ml/training_data_audit.py
```

The first two commands are the real operating loop.
The ML commands are for strategy review and future model preparation.
