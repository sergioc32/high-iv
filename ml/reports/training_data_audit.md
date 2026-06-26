# Training Data Audit

- Dataset: `C:\Users\sergi\development\highIV\ml\training_dataset.csv`
- Total rows: `76`
- Total issues: `37`
- Severity breakdown: `{'error': 17, 'warning': 20}`
- Category breakdown: `{'missingness': 37}`
- Readiness verdict: `data_foundation_ok_but_sample_limited`

## Dataset shape

- Entry date range: `2026-01-16` to `2026-06-05`
- Close date range: `2026-01-27` to `2026-06-18`
- Wins: `64`
- Losses: `12`
- Actual exits: `74`
- Estimated exits: `2`

## Match status mix

- `exact_match`: `63`
- `adjusted_match`: `13`

## Feature provenance mix

- `daily_opportunity_exact`: `56`
- `daily_opportunity_shifted`: `13`
- `candidate_log_exact`: `7`

## Exit price source mix

- `order_history`: `74`
- `(blank)`: `2`

## Time split mix

- `train`: `53`
- `test`: `12`
- `validation`: `11`

## Readiness gates

- `matched_closed_trades_minimum`: `pass` (value=`76`, target=`>= 50`) - Exact and adjusted matched rows only.
- `matched_closed_trades_preferred`: `pass` (value=`76`, target=`>= 75`) - Preferred scale before serious supervised modeling.
- `losing_matched_trades`: `fail` (value=`12`, target=`>= 20`) - Loss coverage matters for balanced learning.
- `unique_symbols_in_matched_history`: `pass` (value=`29`, target=`>= 20`) - Unique symbols among exact and adjusted matches.
- `actual_exit_rate`: `pass` (value=`97.4%`, target=`>= 80.0%`) - 74 of 76 training rows have actual exits.
- `low_confidence_rows_downweighted`: `pass` (value=`max_weight=0.00`, target=`<= 0.20`) - 0 rows have feature_provenance=none.
- `no_critical_integrity_or_leakage_errors`: `pass` (value=`0`, target=`0`) - Excludes missingness-only findings from the critical-error count.
- `time_aware_validation_split`: `pass` (value=`entry_date_chronological_70_15_15`, target=`implemented`) - Chronological split policy verified: entry_date_chronological_70_15_15.

## Highest-missing features

- `industry`: `76` missing (`100.0%`, status=`error`)
- `risk_theme_tags`: `76` missing (`100.0%`, status=`error`)
- `sector`: `76` missing (`100.0%`, status=`error`)
- `technical_theme_tags`: `76` missing (`100.0%`, status=`error`)
- `theme_tags`: `76` missing (`100.0%`, status=`error`)
- `theme_taxonomy_version`: `76` missing (`100.0%`, status=`error`)
- `alignment_score_version`: `62` missing (`81.6%`, status=`error`)
- `call_selector_score`: `62` missing (`81.6%`, status=`error`)
- `market_regime_summary`: `62` missing (`81.6%`, status=`error`)
- `put_selector_score`: `62` missing (`81.6%`, status=`error`)
- `selector_confidence`: `62` missing (`81.6%`, status=`error`)
- `selector_earnings_penalty`: `62` missing (`81.6%`, status=`error`)
- `selector_earnings_stage`: `62` missing (`81.6%`, status=`error`)
- `selector_preferred_strategy`: `62` missing (`81.6%`, status=`error`)
- `selector_version`: `62` missing (`81.6%`, status=`error`)

## Sample issues

- `error` `missingness` `dataset`: industry missingness is 100.0% (missing_count=76)
- `error` `missingness` `dataset`: risk_theme_tags missingness is 100.0% (missing_count=76)
- `error` `missingness` `dataset`: sector missingness is 100.0% (missing_count=76)
- `error` `missingness` `dataset`: technical_theme_tags missingness is 100.0% (missing_count=76)
- `error` `missingness` `dataset`: theme_tags missingness is 100.0% (missing_count=76)
- `error` `missingness` `dataset`: theme_taxonomy_version missingness is 100.0% (missing_count=76)
- `error` `missingness` `dataset`: alignment_score_version missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: call_selector_score missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: market_regime_summary missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: put_selector_score missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: selector_confidence missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: selector_earnings_penalty missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: selector_earnings_stage missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: selector_preferred_strategy missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: selector_version missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: symbol_extension_bucket missingness is 81.6% (missing_count=62)
- `error` `missingness` `dataset`: total_rank_score missingness is 81.6% (missing_count=62)
- `warning` `missingness` `dataset`: earnings_within_dte missingness is 67.1% (missing_count=51)
- `warning` `missingness` `dataset`: directional_bias missingness is 50.0% (missing_count=38)
- `warning` `missingness` `dataset`: option_side missingness is 50.0% (missing_count=38)
- ... `17` more issues not shown
