# High IV Options Trading Strategy - Multi-Phase Development Plan

## Overview

This document outlines the comprehensive roadmap for evolving the High IV Options Screener into a complete **trade execution, management, and strategy analysis platform**. 

**Core Philosophy**: Build data systematically → Analyze rigorously → Iterate intelligently (no curve-fitting)

The three-phase approach enables you to:
1. **Identify** opportunities consistently
2. **Execute & Monitor** positions with clear alerts
3. **Analyze & Optimize** strategy based on real performance

---

## Phase 1: Identify High IV Opportunities ✓ COMPLETE

**Status**: Fully implemented  
**Purpose**: Discover and rank potential put credit spread trades daily

### What Phase 1 Does
- Scans watchlists (S&P 500, Liquid ETFs, High Options Volume) for high IV rank stocks
- Filters by IV Rank threshold (currently 50%)
- Evaluates options chains for favorable put spreads
- Calculates optimal strike selection (delta-based, width-adapted)
- Ranks opportunities by risk/reward ratio
- Outputs daily CSV with proposed trades

### Configuration (in `config.py`)
```python
IV_RANK_THRESHOLD = 50          # Minimum IV Rank %
TARGET_DTE = 45                 # Target days to expiration
TARGET_DELTA = 0.16             # Delta for short put (1σ)
LONG_PUT_DELTA = 0.10           # Delta for long put protection
PREFERRED_SPREAD_WIDTH = 3      # Preferred $3 width
FALLBACK_SPREAD_WIDTH = 5       # Fallback to $5 if needed
MAX_RISK_REWARD_RATIO = 5.0     # Max loss / premium ratio
DTE_TOLERANCE = 7               # ±7 days acceptable
```

---

## Phase 2: Track Position Lifecycle ✓ COMPLETE

### 2A: Open Position Tracking (Daily) ✓

**Status**: Fully implemented  
**Purpose**: Maintain real-time view of ALL active trades for monitoring, profit-taking, and defensive closes

**Data Structure** (`trades_open.csv`):

| Field | Type | Purpose |
|-------|------|---------|
| `trade_id` | string | Unique ID: date + symbol (e.g., `20260115_STX`) |
| `symbol` | string | Stock symbol |
| `entry_date` | date | Date executed |
| `expiration` | date | Expiration date |
| `short_strike` | float | Sold put strike |
| `long_strike` | float | Bought put strike |
| `width` | float | Spread width ($) |
| `entry_credit` | float | Credit received |
| `buying_power_used` | float | Capital allocated |
| `current_mark` | float | Current market value |
| `current_pnl` | float | P&L in dollars |
| `current_pnl_pct` | float | P&L % of max profit |
| `theta_daily` | float | Daily decay ($) |
| `delta` | float | Current delta |
| `vega` | float | IV sensitivity |
| `gamma` | float | Delta acceleration |
| `dte_remaining` | int | Days to expiration |
| `days_held` | int | Days since entry |
| `notes` | text | Entry rationale, observations |

**Alert Thresholds** (action required):
- ✅ **HIT TARGET**: `current_pnl_pct >= 50%` → **CLOSE AT 50% PROFIT**
- ⏰ **APPROACHING EXIT**: `dte_remaining <= 21` → **PREPARE TO CLOSE**
- ⚠️ **MONITOR**: `delta > -0.30 (abs)` → **WATCH CLOSELY**
- 🔴 **DANGER**: `delta > -0.50 (abs)` → **CONSIDER CLOSING**

**Sample entry**:
```csv
trade_id,symbol,entry_date,expiration,short_strike,long_strike,width,entry_credit,buying_power_used,current_mark,current_pnl,current_pnl_pct,theta_daily,delta,vega,gamma,dte_remaining,days_held,notes
20260113_STX,STX,2026-01-13,2026-02-27,260,265,5,115,385,90,25,21.7,1.88,-0.020,1.575,0.000,43,2,High IV 77%, solid premium
20260115_SNDK,SNDK,2026-01-15,2026-02-27,280,275,5,140,360,120,20,14.3,2.10,0.85,-0.015,0.000,43,0,Wide $10 strikes, adapted
```

---

### 2B: Closed Position Tracking (Weekly or As-Closed) ✓

**Status**: Fully implemented (uses estimated close_debit; actual fills enhancement pending real-world test)  
**Purpose**: Build historical record for strategy analysis and performance measurement

**Data Structure** (`trades_closed.csv`):

| Field | Type | Purpose |
|-------|------|---------|
| `trade_id` | string | Links to open record |
| `symbol` | string | Stock symbol |
| `entry_date` | date | Original entry |
| `close_date` | date | Date closed |
| `short_strike` | float | Sold strike |
| `long_strike` | float | Bought strike |
| `width` | float | Spread width |
| `entry_credit` | float | Credit received |
| `close_price` | float | Debit paid to close |
| `expiration_date` | date | Original expiration |
| `dte_at_close` | int | Days remaining at close |
| `days_held` | int | Total days open |
| `profit_loss` | float | Entry credit - close debit |
| `profit_loss_pct` | float | (P&L / max profit) × 100 |
| `max_profit` | float | Entry credit |
| `max_loss` | float | Width - entry credit |
| `annualized_return` | float | (P&L / capital) × (365 / days_held) |
| `exit_type` | enum | `target_50`, `time_21dte`, `defensive`, `stop`, `assignment`, `other` |
| `exit_notes` | text | Reason & context for close |

**Sample entries**:
```csv
trade_id,symbol,entry_date,close_date,short_strike,long_strike,width,entry_credit,close_price,dte_at_close,days_held,profit_loss,profit_loss_pct,exit_type,exit_notes
20260110_XYZ,XYZ,2026-01-10,2026-01-22,150,145,5,120,60,33,12,60,50.0,target_50,Hit 50% on theta decay
20260108_ABC,ABC,2026-01-08,2026-02-01,200,195,5,95,45,14,24,50,52.6,time_21dte,Closed at 21 DTE per strategy
20260105_DEF,DEF,2026-01-05,2026-01-18,175,170,5,110,130,35,-20,-16.7,defensive,Stock -8%; defended position
```

---

## Phase 3: Analyze & Optimize Strategy (Month 2+)

**Purpose**: Extract actionable insights; iterate intelligently

### 3A: Trade-Level Metrics

Calculate for closed trades:
- **Win Rate**: % of profitable trades
- **Avg Profit**: Mean P&L per trade
- **Profit Factor**: Sum of winners / Sum of losers
- **Avg Holding Days**: Mean days held before close
- **Sharpe Ratio**: Return per unit of risk

### 3B: Strategy Parameter Analysis

**Real insights you'll uncover** (no curve-fitting):

```
✓ "Trades with credit < $30 had similar win rates but 15% worse capital efficiency."
✓ "Delta 0.18 performed better than 0.15 in high-vol environments (+8% win rate)."
✓ "Closing at 40% profit earlier improved annualized return by 12%."
✓ "Certain ETFs (IWM, XLF) underperform despite high IV rank; consider removing."
✓ "Defensive closes during earnings weeks had 80% success vs 65% overall."
✓ "Average days to 50% profit: 15 days; closing at 21 DTE costs ~$20-30 per spread."
✓ "Risk/reward ratio > 4.0 had lower win rate; tighten to 3.0 max."
```

### 3C: Monthly Iteration Cycle

1. **Gather**: Compile closed trades (Phase 2B)
2. **Analyze**: Run segmentation & correlation analysis
3. **Identify**: Find patterns and underperformers
4. **Adjust**: Modify `config.py` for next month
5. **Test**: Forward test; measure impact
6. **Document**: Update strategy notes

**Example**:
```
Month 1: IV_RANK_THRESHOLD = 50
  Result: 68% win rate, 22% avg profit %, $1200 net

Finding: Trades with credit < $30 had higher loss %

Month 2: Add MIN_CREDIT_FILTER = 40
  Result: 72% win rate, 25% avg profit %, $1400 net
  
Decision: Keep adjustment; improved both metrics
```

---

## Implementation Timeline

### Phase 2A: Open Position Tracker ✓ COMPLETE
- [x] Create `trades_open.csv` template
- [x] Set up daily sync process via API (`--sync-positions`)
- [x] Implement alert dashboard (50%, 21 DTE thresholds)
- [x] Enhanced trade_id for uniqueness (includes expiration + width)

### Phase 2B: Closed Position Tracker ✓ COMPLETE
- [x] Create `trades_closed.csv` template with enhanced schema
- [x] Auto-detect closed positions via API
- [x] Implement P&L & annualized return calculations
- [x] Add fees_estimated, is_estimated_exit flag
- [x] Link open → closed records via deterministic trade_id
- [ ] **Future**: Add actual fill price tracking via orders endpoint (pending real-world test)

### Phase 3A: Basic Analysis (NEXT - Month 2)
- [ ] Build monthly summary report
- [ ] Segment analysis by symbol, sector, credit bucket
- [ ] Calculate win rate, profit factor, avg holding days

### Phase 3B: Advanced Analysis (Month 3+)
- [ ] Correlation analysis: IV Rank → profitability
- [ ] Exit type performance comparison
- [ ] Parameter sensitivity testing
- [ ] Recommendations for next month's adjustments

---

## Success Metrics

**By Week 4**:
- 30+ trades in `trades_open.csv`
- Daily alerts working correctly
- 0 missed profit-taking opportunities

**By Month 2**:
- 20+ trades in `trades_closed.csv`
- Monthly analysis report complete
- 3-5 actionable insights identified

**Long-term (3-6 months)**:
- Win rate > 70%
- Profit factor > 2.0
- Consistent monthly P&L
- Clear parameter optimization path

---

## Storage Structure

```
highIV/
├── trades/
│   ├── trades_open.csv          # Active positions (daily)
│   ├── trades_closed.csv        # Historical (append-only)
│   ├── analysis_202601.md       # Monthly reports
│   └── analysis_202602.md
├── opportunities/               # Phase 1 outputs
├── config.py                    # Strategy parameters
└── TradingStrategyPlan.README.md  # This document
```

---

## Key Principles

1. **No curve-fitting**: Only adjust after 20+ trade sample
2. **Document decisions**: Every change needs data justification
3. **Reality-check**: Backtest insights against future performance
4. **Automate gradually**: Manual CSV → API sync → automated alerts
5. **Focus on process**: Build systems that reveal what works, not what looks good

**Remember**: You're building a feedback loop. Data → Analysis → Iteration → Better Results.

---

## Next Steps

6. **By end of Month 1**: Analyze your first 10-20 closed trades for patterns

This framework transforms the screener from **"what to trade"** → **"how to trade profitably and improve systematically"**.

---

## Future Enhancements (Phase 3+)

### Priority 1: Optimized Quote Fetching

**Objective**: Reduce API calls while maintaining market accuracy

**Current**: Fetches all chain quotes, then filters

**Proposed**: 
- After finding anchor strike and ±N window, build targeted list of option symbols for:
  - All candidate short strikes in window
  - All candidate long strikes in window  
- Make single batch quote call to TT for these symbols only
- Use real-time bid/ask from response for all filters

**Benefit**: "Real markets" accuracy with ~10-20% of current API usage

**Status**: Pending — implement after initial live trading data

---

### Priority 2: Asymmetric Liquidity Filters

**Objective**: Reflect real market dynamics (long legs less liquid, less critical)

**Current**: Both short & long legs require `<= $0.10 OR <= 3%`

**Proposed**:
- **Short leg** (strict): `<= $0.10 OR <= 3%` — controls fill quality
- **Long leg** (looser): `<= $0.20 OR <= 6%` — you're paying for it anyway

**Rationale**: Short leg bid/ask determines execution; long leg is protection layer

**Config Addition**:
```python
MAX_SHORT_LEG_BID_ASK_WIDTH = 0.10
MAX_SHORT_LEG_BID_ASK_WIDTH_PCT = 0.03
MAX_LONG_LEG_BID_ASK_WIDTH = 0.20
MAX_LONG_LEG_BID_ASK_WIDTH_PCT = 0.06
```

**Status**: Pending calibration — requires 5-10 real fills to validate

---

### Priority 3: Credit Fillability Model

**Objective**: Filter "looks good on midpoint but can't fill" spreads without discarding usable but slightly messy markets

**Implemented**: Uses a two-stage credit model

```python
credit_mid = mid(short) - mid(long)
credit_natural = bid(short) - ask(long)  # Worst-case fill
credit_expected = bounded_weighted_fill(credit_natural, credit_mid, avg_width_pct)

# Gate A: execution sanity
if credit_natural < -(width * MIN_NATURAL_CREDIT_PCT):
  reject spread

# Gate B: economics
if credit_expected < width * MIN_CREDIT_PER_WIDTH:
  reject spread
```

**Config Inputs**:
```python
MIN_NATURAL_CREDIT_PCT = 0.05
MIN_CREDIT_PER_WIDTH = 0.08
CREDIT_DYNAMIC_WIDTH_PCT_TIGHT = 0.10
CREDIT_DYNAMIC_WIDTH_PCT_OK = 0.20
CREDIT_DYNAMIC_WIDTH_PCT_WIDE = 0.35
CREDIT_DYNAMIC_MID_WEIGHT_TIGHT = 0.85
CREDIT_DYNAMIC_MID_WEIGHT_OK = 0.75
CREDIT_DYNAMIC_MID_WEIGHT_MODERATE = 0.65
CREDIT_DYNAMIC_MID_WEIGHT_VERY_WIDE = 0.55
```

**Benefit**: Separates fillability from economics and preserves a single modeled premium for ranking, metrics, and diagnostics

**Status**: Implemented