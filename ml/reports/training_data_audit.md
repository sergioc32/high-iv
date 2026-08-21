# Training Data Audit

- Dataset: `C:\Users\sergi\development\highIV\ml\training_dataset.csv`
- Total rows: `110`
- Total issues: `29`
- Severity breakdown: `{'error': 5, 'warning': 24}`
- Category breakdown: `{'missingness': 29}`
- Readiness verdict: `ready_for_baseline_weighted_experiments`

## Dataset shape

- Entry date range: `2026-01-16` to `2026-08-07`
- Close date range: `2026-01-27` to `2026-08-18`
- Wins: `82`
- Losses: `28`
- Actual exits: `108`
- Estimated exits: `2`

## Match status mix

- `exact_match`: `95`
- `adjusted_match`: `15`

## Feature provenance mix

- `daily_opportunity_exact`: `62`
- `candidate_log_exact`: `33`
- `daily_opportunity_shifted`: `13`
- `candidate_log_adjusted`: `2`

## Exit price source mix

- `order_history`: `108`
- `(blank)`: `2`

## Time split mix

- `train`: `77`
- `test`: `17`
- `validation`: `16`

## Readiness gates

- `matched_closed_trades_minimum`: `pass` (value=`110`, target=`>= 50`) - Exact and adjusted matched rows only.
- `matched_closed_trades_preferred`: `pass` (value=`110`, target=`>= 75`) - Preferred scale before serious supervised modeling.
- `losing_matched_trades`: `pass` (value=`28`, target=`>= 20`) - Loss coverage matters for balanced learning.
- `unique_symbols_in_matched_history`: `pass` (value=`37`, target=`>= 20`) - Unique symbols among exact and adjusted matches.
- `actual_exit_rate`: `pass` (value=`98.2%`, target=`>= 80.0%`) - 108 of 110 training rows have actual exits.
- `low_confidence_rows_downweighted`: `pass` (value=`max_weight=0.00`, target=`<= 0.20`) - 0 rows have feature_provenance=none.
- `no_critical_integrity_or_leakage_errors`: `pass` (value=`0`, target=`0`) - Excludes missingness-only findings from the critical-error count.
- `time_aware_validation_split`: `pass` (value=`entry_date_chronological_70_15_15`, target=`implemented`) - Chronological split policy verified: entry_date_chronological_70_15_15.

## Highest-missing features

- `technical_theme_tags`: `100` missing (`90.9%`, status=`error`)
- `industry`: `87` missing (`79.1%`, status=`error`)
- `sector`: `87` missing (`79.1%`, status=`error`)
- `risk_theme_tags`: `84` missing (`76.4%`, status=`error`)
- `theme_tags`: `84` missing (`76.4%`, status=`error`)
- `theme_taxonomy_version`: `82` missing (`74.5%`, status=`warning`)
- `earnings_within_dte`: `73` missing (`66.4%`, status=`warning`)
- `alignment_score_version`: `63` missing (`57.3%`, status=`warning`)
- `call_selector_score`: `63` missing (`57.3%`, status=`warning`)
- `market_regime_summary`: `63` missing (`57.3%`, status=`warning`)
- `put_selector_score`: `63` missing (`57.3%`, status=`warning`)
- `selector_confidence`: `63` missing (`57.3%`, status=`warning`)
- `selector_earnings_penalty`: `63` missing (`57.3%`, status=`warning`)
- `selector_earnings_stage`: `63` missing (`57.3%`, status=`warning`)
- `selector_preferred_strategy`: `63` missing (`57.3%`, status=`warning`)

## Sample issues

- `error` `missingness` `dataset`: technical_theme_tags missingness is 90.9% (missing_count=100)
- `error` `missingness` `dataset`: industry missingness is 79.1% (missing_count=87)
- `error` `missingness` `dataset`: sector missingness is 79.1% (missing_count=87)
- `error` `missingness` `dataset`: risk_theme_tags missingness is 76.4% (missing_count=84)
- `error` `missingness` `dataset`: theme_tags missingness is 76.4% (missing_count=84)
- `warning` `missingness` `dataset`: theme_taxonomy_version missingness is 74.5% (missing_count=82)
- `warning` `missingness` `dataset`: earnings_within_dte missingness is 66.4% (missing_count=73)
- `warning` `missingness` `dataset`: alignment_score_version missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: call_selector_score missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: market_regime_summary missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: put_selector_score missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: selector_confidence missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: selector_earnings_penalty missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: selector_earnings_stage missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: selector_preferred_strategy missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: selector_version missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: symbol_extension_bucket missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: total_rank_score missingness is 57.3% (missing_count=63)
- `warning` `missingness` `dataset`: directional_bias missingness is 34.5% (missing_count=38)
- `warning` `missingness` `dataset`: distance_to_52w_high_pct missingness is 30.9% (missing_count=34)
- ... `9` more issues not shown
