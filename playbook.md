# High IV Phase 1 Playbook

This playbook is the operational workflow for running the current system end-to-end before Phase 2.

## Purpose
Use this document as the day-to-day and week-to-week checklist for:
- Finding new spread opportunities
- Managing open positions
- Closing trades based on alerts and risk rules
- Producing weekly analytics for tuning decisions

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
- Runs screener and prints TOP PUT SPREAD OPPORTUNITIES
- Writes daily opportunity CSV output

Expected outputs:
- Open positions snapshot in trades/trades_open.csv
- New opportunities file in opportunities/
- Candidate evaluation log updated in opportunities/opportunity_candidates.csv
- Rejection counters updated in rejections/rejections_tracking.csv

How to use it:
- In SYNCING OPEN POSITIONS, close trades that meet your exit rules (for example target profit, time-based exit, or risk defense)
- In TOP PUT SPREAD OPPORTUNITIES, open only trades you approve

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
