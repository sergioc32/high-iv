# General
Daily trading profile

```bash
MIN_CREDIT_PER_WIDTH = 0.12

MAX_SHORT_LEG_BID_ASK_WIDTH = 1.25 
MAX_SHORT_LEG_BID_ASK_WIDTH_PCT = 0.30
MAX_LONG_LEG_BID_ASK_WIDTH = 3.00
MAX_LONG_LEG_BID_ASK_WIDTH_PCT = 0.40
```
# High Volitility
Volitility is at or above 20
```bash
MIN_CREDIT_PER_WIDTH = 0.12

MAX_SHORT_LEG_BID_ASK_WIDTH = 1.25 
MAX_SHORT_LEG_BID_ASK_WIDTH_PCT = 0.30
MAX_LONG_LEG_BID_ASK_WIDTH = 3.00
MAX_LONG_LEG_BID_ASK_WIDTH_PCT = 0.40
```
# Whitelist
Whitelist watchlist stocks we have hand selected
```bash
MIN_CREDIT_PER_WIDTH = 0.08

MAX_SHORT_LEG_BID_ASK_WIDTH = 1.25 
MAX_SHORT_LEG_BID_ASK_WIDTH_PCT = 0.30
MAX_LONG_LEG_BID_ASK_WIDTH = 5.00
MAX_LONG_LEG_BID_ASK_WIDTH_PCT = 0.50
```

## Priority Watchlist
Create a priority list:
- NVDA
- COIN
- META
- AMD
- IWM
- XBI

## 
Simple Vol Regime Checklist (manual or coded later)

If any 2–3 of these are true → High Vol Regime

Market-Based

VIX ≥ 20

VIX up ≥ 25% in 5 trading days

SPX down ≥ 2% in one session

Options-Based

Median IV Rank of your universe ≥ 60

IV Rank expanding while price is falling

Put skew steepening

Behavioral

Big red day followed by unstable bounce

News-driven selling (macro, rates, geopolitical)

Correlations ↑ across sectors

🔄 Regime Outcomes
Regime	Expectation
Low vol	0–2 trades/week
Normal	2–5 trades/week
High vol	5–10 trades/week
Crisis	Size down, widen rules carefully