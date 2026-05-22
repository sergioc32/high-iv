# Training Data Audit

- Dataset: `C:\Users\sergi\development\highIV\ml\training_dataset.csv`
- Total rows: `33`
- Total issues: `26`
- Severity breakdown: `{'error': 19, 'warning': 7}`
- Category breakdown: `{'missingness': 26}`
- Readiness verdict: `data_foundation_ok_but_sample_limited`

## Dataset shape

- Entry date range: `2026-01-13` to `2026-04-13`
- Close date range: `2026-01-27` to `2026-04-17`
- Wins: `25`
- Losses: `8`
- Actual exits: `31`
- Estimated exits: `2`

## Match status mix

- `trade_only`: `24`
- `exact_match`: `8`
- `adjusted_match`: `1`

## Feature provenance mix

- `daily_opportunity_exact`: `11`
- `candidate_log_exact`: `8`
- `daily_opportunity_shifted`: `7`
- `none`: `6`
- `candidate_log_adjusted`: `1`

## Exit price source mix

- `order_history`: `31`
- `(blank)`: `2`

## Time split mix

- `train`: `23`
- `test`: `6`
- `validation`: `4`

## Readiness gates

- `matched_closed_trades_minimum`: `fail` (value=`9`, target=`>= 50`) - Exact and adjusted matched rows only.
- `matched_closed_trades_preferred`: `fail` (value=`9`, target=`>= 75`) - Preferred scale before serious supervised modeling.
- `losing_matched_trades`: `fail` (value=`1`, target=`>= 20`) - Loss coverage matters for balanced learning.
- `unique_symbols_in_matched_history`: `fail` (value=`7`, target=`>= 20`) - Unique symbols among exact and adjusted matches.
- `actual_exit_rate`: `pass` (value=`93.9%`, target=`>= 80.0%`) - 31 of 33 training rows have actual exits.
- `low_confidence_rows_downweighted`: `pass` (value=`max_weight=0.20`, target=`<= 0.20`) - 6 rows have feature_provenance=none.
- `no_critical_integrity_or_leakage_errors`: `pass` (value=`0`, target=`0`) - Excludes missingness-only findings from the critical-error count.
- `time_aware_validation_split`: `pass` (value=`entry_date_chronological_70_15_15`, target=`implemented`) - Chronological split policy verified: entry_date_chronological_70_15_15.

## Highest-missing features

- `anchor_vs_shift_status`: `33` missing (`100.0%`, status=`error`)
- `distance_to_52w_high_pct`: `33` missing (`100.0%`, status=`error`)
- `distance_to_52w_low_pct`: `33` missing (`100.0%`, status=`error`)
- `fill_edge`: `33` missing (`100.0%`, status=`error`)
- `fill_edge_pct`: `33` missing (`100.0%`, status=`error`)
- `fill_quality_score`: `33` missing (`100.0%`, status=`error`)
- `mid_capture_pct`: `33` missing (`100.0%`, status=`error`)
- `range_position_52w`: `33` missing (`100.0%`, status=`error`)
- `range_position_bucket`: `33` missing (`100.0%`, status=`error`)
- `shift_steps_from_anchor`: `33` missing (`100.0%`, status=`error`)
- `year_high_price`: `33` missing (`100.0%`, status=`error`)
- `year_low_price`: `33` missing (`100.0%`, status=`error`)
- `avg_width_pct`: `32` missing (`97.0%`, status=`error`)
- `fill_quality`: `32` missing (`97.0%`, status=`error`)
- `mid_weight`: `32` missing (`97.0%`, status=`error`)

## Sample issues

- `error` `missingness` `dataset`: anchor_vs_shift_status missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: distance_to_52w_high_pct missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: distance_to_52w_low_pct missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: fill_edge missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: fill_edge_pct missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: fill_quality_score missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: mid_capture_pct missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: range_position_52w missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: range_position_bucket missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: shift_steps_from_anchor missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: year_high_price missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: year_low_price missingness is 100.0% (missing_count=33)
- `error` `missingness` `dataset`: avg_width_pct missingness is 97.0% (missing_count=32)
- `error` `missingness` `dataset`: fill_quality missingness is 97.0% (missing_count=32)
- `error` `missingness` `dataset`: mid_weight missingness is 97.0% (missing_count=32)
- `error` `missingness` `dataset`: credit_expected missingness is 93.9% (missing_count=31)
- `error` `missingness` `dataset`: credit_mid missingness is 93.9% (missing_count=31)
- `error` `missingness` `dataset`: credit_natural missingness is 93.9% (missing_count=31)
- `error` `missingness` `dataset`: earnings_within_dte missingness is 78.8% (missing_count=26)
- `warning` `missingness` `dataset`: premium_per_width missingness is 72.7% (missing_count=24)
- ... `6` more issues not shown
