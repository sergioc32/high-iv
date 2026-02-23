# Architecture Overview

This document outlines the design and architecture of the High IV Options Screener application.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                   (Application Entry Point)                  │
└──────────────┬──────────────────────────────────────────────┘
               │
               ├──────────────┬──────────────┬─────────────────┐
               │              │              │                 │
        ┌──────▼──────┐  ┌───▼────┐  ┌─────▼──────┐  ┌──────▼──────┐
        │   API Layer │  │Screener│  │  Utilities │  │Configuration│
        │             │  │ Layer  │  │            │  │             │
        └─────────────┘  └────────┘  └────────────┘  └─────────────┘
               │
        ┌──────▼───────────────────────────────────┐
        │      Tastytrade REST API                 │
        │   (External Data Source)                 │
        └──────────────────────────────────────────┘
```

## Components

### 1. Main Application (`main.py`)

**Responsibility**: Orchestrates the entire screening workflow

**Key Functions**:
- Loads environment configuration
- Manages authentication flow
- Coordinates screening pipeline stages
- Handles error recovery and logging
- Controls output and CSV export

**Workflow**:
1. Authentication
2. Watchlist discovery and symbol fetching
3. Market metrics batch retrieval
4. IV rank filtering
5. Options chain analysis
6. Spread evaluation and ranking
7. Results display and export

### 2. API Layer (`api/tastytrade.py`)

**Responsibility**: Encapsulates all Tastytrade API interactions

**Design Pattern**: Wrapper/Facade pattern for clean API abstraction

**Key Classes**:
- `TastytradeAPI`: Main API client with session management

**Key Methods**:
- `authenticate()`: Session creation and token management
- `list_watchlists()`: Discover available watchlists (public/private)
- `get_watchlist()`: Fetch symbols from named watchlists
- `get_market_metrics()`: Batch retrieve IV rank/percentile
- `get_quotes_batch()`: Batch equity quotes with pricing
- `get_option_expirations()`: Available expiration dates per symbol
- `get_option_chain()`: Strike prices and option symbols
- `get_option_quotes()`: Option pricing and greeks
- `batch_request_with_delay()`: Rate-limited batch processing

**Features**:
- Session token caching
- Automatic retry logic (via requests library)
- URL encoding for special characters
- Response parsing and normalization
- Error handling with descriptive messages

### 3. Screener Layer (`screener/`)

#### 3.1 IV Screener (`iv_screener.py`)

**Responsibility**: Filters stocks by implied volatility metrics

**Key Class**: `IVScreener`

**Methods**:
- `filter_by_iv_rank()`: Applies IV rank threshold filter
- `get_top_candidates()`: Limits candidates for deeper analysis
- `display_screening_results()`: Formatted console output

**Data Processing**:
- Converts API data to pandas DataFrame
- Handles missing/invalid values (coercion to numeric)
- Sorts by IV rank descending

#### 3.2 Spread Analyzer (`spread_analyzer.py`)

**Responsibility**: Evaluates put credit spread opportunities

**Key Class**: `SpreadAnalyzer`

**Methods**:
- `find_target_expiration()`: Selects expiration closest to target DTE
- `find_strike_by_delta()`: Identifies strikes matching target delta
- `find_spread_strikes()`: Constructs optimal spread pairs
- `evaluate_spread()`: Calculates premium, risk, and R/R ratio
- `filter_opportunities()`: Applies final criteria filters
- Strike increment detection: adapts to $1/$5/$10 ladders within a configurable max increment

**Strategy**:
- Sell put at ~0.16 delta (1 standard deviation out-of-the-money)
- Buy put 3-5 strikes lower for defined risk
- Target 45 DTE with ±7 day tolerance
- Risk/reward ratio evaluation

### 4. Utilities (`utils/display.py`)

**Responsibility**: Console output formatting and user feedback

**Key Functions**:
- `print_header()`: Application banner
- `print_progress()`: Stage indicators
- `display_opportunities()`: Formatted trade table
- `display_summary()`: Execution statistics

**Design**: Separation of presentation from business logic

### 5. Configuration (`config.py`)

**Responsibility**: Centralized parameter management

**Categories**:
- Screening criteria (IV thresholds, liquidity)
- Options parameters (DTE, delta targets)
- Spread configuration (width, risk limits)
- Display settings (result limits, auto-save)
- Watchlist definitions

**Design**: Single source of truth for tuneable parameters

### 4. Utilities Layer (`utils/`)

#### 4.1 Display Module (`display.py`)

**Responsibility**: Formatted console output and result presentation

**Key Functions**:
- `print_header()`: Section dividers and status messages
- `display_opportunities()`: Formatted table of trade opportunities
- `display_summary()`: Execution summary statistics
- `print_progress()`: Progress indicators with spinner

#### 4.2 Market Hours Module (`market_hours.py`)

**Responsibility**: Detect market status for data quality flagging

**Key Functions**:
- `is_market_open()`: Returns True if US market currently open (9:30 AM - 4:00 PM ET, weekdays)
- `get_market_status_display()`: Returns 'OPEN' or 'CLOSED' for banner display

**Integration**:
- Called at screener start to set market context
- After-hours results saved with `_indicative` filename suffix
- Banner displayed: "🔕 MARKET STATUS: CLOSED ⚠ Results are indicative only"

#### 4.3 Cache Module (`cache.py`)

**Responsibility**: Lightweight file-based cache for API responses

**Key Concepts**:
- Per-key TTLs tuned by data volatility
- SHA1-hashed filenames for safe storage
- Best-effort writes (cache never blocks execution)
- Endpoint-aware keys: `session_token:<user>`, `watchlist:<scope>:<name>`, `metrics:<symbol>`, `quote:<symbol>`, `expirations:<symbol>`, `chain:<symbol>:<exp>`, `optquote:<optionSymbol>`

## Data Flow

### Phase 1: Symbol Collection
```
Environment (.env) → Authentication → Watchlists API
                                           ↓
                               Symbol List Aggregation
                                           ↓
                                    Deduplication
```

### Phase 2: IV Screening
```
Symbol List → Market Metrics API (batch) → IV Rank Data
                                                ↓
                                    DataFrame Processing
                                                ↓
                                    Filtering & Sorting
                                                ↓
                                    Top N Candidates
```

### Phase 3: Options Analysis
```
Candidates → Batch Stock Quotes → Current Prices
     ↓
Option Expirations API → Expiration Selection
     ↓
Option Chains API → Strike Symbols
     ↓
Option Quotes API (batch) → Greeks & Pricing
     ↓
Spread Evaluation → Risk/Reward Calculation
     ↓
Filtering → Final Opportunities
     ↓
Rejection Tracking → CSV log (rejections_tracking.csv)
```

### Phase 4: Output
```
Opportunities → Console Display + Market Status Banner
                     ↓
              CSV Export (with _indicative suffix if after-hours)
              
Rejections → Append to rejections/rejections_tracking.csv
```

## Rejection Tracking System

**Purpose**: Diagnose filter bottlenecks and calibrate constraints

**Location**: `rejections/rejections_tracking.csv`

**Columns**:
- `timestamp`: When rejection occurred
- `symbol`: Stock symbol analyzed
- `delta_bounds`: Count rejected for delta outside [MIN_DELTA, MAX_DELTA]
- `short_bid_ask_width`: Count rejected for short leg bid/ask too wide
- `long_bid_ask_width`: Count rejected for long leg bid/ask too wide
- `premium_zero_or_negative`: Count rejected for invalid premium
- `risk_reward`: Count rejected for risk/reward > MAX_RISK_REWARD_RATIO
- `no_long_strike`: Count rejected for unavailable long strike
- `total_rejections`: Sum of all rejection categories

**Data Interpretation**:
- With `SKEW_WINDOW=1`: Max 3 candidates per filter
- With `SKEW_WINDOW=2`: Max 5 candidates per filter
- High `short_bid_ask_width` + `long_bid_ask_width` on choppy days → liquidity filter too strict
- High `delta_bounds` → delta window too narrow
- Cascading counts show filter pipeline effectiveness

## Design Patterns

### 1. Facade Pattern
`TastytradeAPI` provides a simplified interface to complex API interactions, hiding:
- HTTP request details
- Response parsing complexity
- Error handling nuances
- URL encoding logic

### 2. Strategy Pattern
`SpreadAnalyzer` encapsulates the put spread evaluation algorithm, allowing:
- Easy swapping of different spread strategies
- Configuration-driven parameter tuning
- Testable business logic

### 3. Data Pipeline Pattern
`main.py` implements a clear ETL (Extract-Transform-Load) pipeline:
- Extract: API data retrieval
- Transform: Filtering, calculations, enrichment
- Load: Display and CSV export

## Error Handling Strategy

### Levels:
1. **API Level**: HTTP errors, timeouts, malformed responses
2. **Data Level**: Missing values, type conversions, empty results
3. **Application Level**: Invalid configuration, missing credentials

### Approach:
- Graceful degradation (fallback to hardcoded symbols)
- Descriptive error messages with context
- Continue processing on individual failures
- Summary reporting of errors

## Performance Considerations

### Optimization Techniques:
1. **Batch API Requests**: Reduces round-trips
2. **Rate Limiting**: Respects API constraints
3. **Early Filtering**: Limits downstream processing
4. **Lazy Loading**: Fetches greeks only for viable candidates

### Current Bottlenecks:
- Sequential options analysis (could be parallelized)
- API rate limits on option quotes
- No caching (every run fetches fresh data)

## Future Enhancements

### Scalability:
- Parallel options analysis (threading/async)
- Local caching with TTL
- Database storage for historical tracking

### Features:
- Multiple spread strategies (iron condors, calendars)
- Backtesting framework
- Real-time monitoring mode
- Web dashboard

### Architecture:
- Separate data layer (repository pattern)
- Event-driven architecture for real-time updates
- Microservices for different screener strategies

## Dependencies

### External:
- `requests`: HTTP client for API calls
- `pandas`: Data manipulation and analysis
- `python-dotenv`: Environment variable management
- `tabulate`: Table formatting (via pandas)

### Python Standard Library:
- `os`, `sys`: System operations
- `time`: Delays and timestamps
- `typing`: Type hints
- `urllib.parse`: URL encoding

## Testing Strategy (Future)

### Unit Tests:
- API response parsing
- IV rank filtering logic
- Spread calculation accuracy
- Delta matching algorithm

### Integration Tests:
- End-to-end screening workflow
- API error handling
- CSV export validation

### Mocking:
- Tastytrade API responses
- File system operations
- Time-dependent logic

## Security Considerations

- **Credentials**: Stored in `.env` (not version controlled)
- **Session Tokens**: Memory-only, printed for debugging (consider removing in production)
- **API Keys**: No hardcoded secrets in codebase
- **Input Validation**: URL encoding, parameter sanitization

## Logging (Future Enhancement)

Proposed logging levels:
- **DEBUG**: API request/response details
- **INFO**: Stage completion, counts
- **WARNING**: Fallbacks activated, missing data
- **ERROR**: API failures, parsing errors
- **CRITICAL**: Authentication failures, fatal errors

---

**Last Updated**: January 11, 2026  
**Version**: 1.0
