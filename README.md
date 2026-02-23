# High IV Options Screener

An automated options screening tool that identifies high implied volatility (IV) stocks and analyzes profitable put spread opportunities using the Tastytrade API.

## Features

- **IV Rank Screening**: Filters stocks by implied volatility rank to find elevated IV environments
- **Watchlist Integration**: Pulls symbols from Tastytrade public watchlists (S&P 500, Liquid ETFs)
- **Options Analysis**: Evaluates put credit spreads based on delta, days to expiration, and risk/reward ratios
- **Batch Processing**: Efficient API calls with rate limiting and batch requests
- **Smart Caching**: File-based cache to avoid redundant API calls (watchlists, expirations, chains, metrics, quotes)
- **CSV Export**: Automatically saves trade opportunities to timestamped CSV files

## Prerequisites

- Python 3.10 or higher
- Tastytrade account with API access
- Virtual environment (recommended)

## Installation

1. **Clone or download the repository**
   ```bash
   cd c:\Users\sergi\development\highIV
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**
   ```bash
   # Windows
   venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```
   TASTYTRADE_USERNAME=your_username
   TASTYTRADE_PASSWORD=your_password
   ```

## Configuration

Edit `config.py` to customize screening parameters:

### Screening Criteria
- `IV_RANK_THRESHOLD`: Minimum IV Rank % (default: 60)
- `MIN_LIQUIDITY_VOLUME`: Minimum daily volume filter

### Options Criteria
- `TARGET_DTE`: Target days to expiration (default: 45)
- `TARGET_DELTA`: Target delta for short put (default: 0.16)
- `LONG_PUT_DELTA`: Delta for long put protection (default: 0.10)

### Spread Configuration
- `PREFERRED_SPREAD_WIDTH`: Preferred spread width in dollars (default: 3)
- `FALLBACK_SPREAD_WIDTH`: Fallback width if preferred not available (default: 5)
- `MAX_STRIKE_INCREMENT`: Largest strike increment to accept when adapting widths (default: 10)
- `MAX_RISK_REWARD_RATIO`: Maximum risk/reward ratio (default: 4.0)

### Display Settings
### Caching
- `CACHE_DIR`: Directory for cached JSON files (default: cache)
- `CACHE_TTL_SESSION`: Session token reuse window
- `CACHE_TTL_WATCHLIST`: Cache duration for watchlist symbols
- `CACHE_TTL_EXPIRATIONS`: Cache duration for expirations per symbol
- `CACHE_TTL_OPTION_CHAIN`: Cache duration for option chains per expiration
- `CACHE_TTL_MARKET_METRICS`: Cache duration for per-symbol metrics
- `CACHE_TTL_QUOTES`: Cache duration for equity quotes
- `CACHE_TTL_OPTION_QUOTES`: Cache duration for option quotes

### Exclusions
- `EXCLUDE_SYMBOLS`: List of symbols to temporarily skip; defaults to empty
- `MAX_SCREENING_RESULTS`: Max stocks to show after IV screening (default: 30)
- `MAX_FINAL_RESULTS`: Max trade opportunities to display (default: 15)
- `AUTO_SAVE_CSV`: Automatically save results to CSV (default: True)

## Usage

Run the screener:
```bash
python main.py
```

### Command Line Options

**Clear all cached data:**
```bash
python main.py --clear-cache-all
```
Clears all cached API responses (watchlists, expirations, option chains, market metrics, quotes) from the `cache/` directory and exits.

**Fresh day run (recommended for morning runs):**
```bash
python main.py --fresh-day
```
Clears stale cache entries from previous days, syncs current open positions from your account, displays P/L with alerts for profit targets (≥50%) and approaching expiration (≤21 DTE), then continues to opportunity screener. Best for morning routine to get full picture of current positions and new opportunities.

**Market Status**: Automatically detected based on US Eastern Time (9:30 AM - 4:00 PM ET, weekdays). After-hours results include `_indicative` filename suffix and status banner: "🔕 MARKET STATUS: CLOSED ⚠ Results are indicative only - bid/ask spreads may be stale"

**Rejection Tracking**: All rejection counters (delta bounds, bid/ask width, premium, risk/reward, etc.) are automatically logged to `rejections/rejections_tracking.csv` for analysis of filter bottlenecks.

**Sync positions only (skip screener):**
```bash
python main.py --sync-positions
```
Fetches current account positions, parses option spreads, displays P/L summary with alerts, and saves to `trades/trades_open.csv`. Use this for quick position checks without running the full screener.

The screener will:
1. Authenticate with Tastytrade API
2. Fetch symbols from configured watchlists
3. Screen stocks by IV Rank threshold
4. Analyze options chains for top candidates
5. Identify and rank put spread opportunities
6. Display results and save to CSV (if enabled)

## Output

### Console Output
- Authentication status and session token (for Postman testing)
- Available watchlists
- Screening progress and results
- Top high IV stocks with metrics
- Trade opportunities with strike prices, premiums, and risk/reward ratios
- Execution summary

### CSV Export
When opportunities are found, results are saved to:
```
opportunities_YYYYMMDD_HHMMSS.csv
```

## Project Structure

```
highIV/
├── api/
│   ├── __init__.py
│   └── tastytrade.py          # Tastytrade API wrapper
├── screener/
│   ├── __init__.py
│   ├── iv_screener.py         # IV rank filtering logic
│   └── spread_analyzer.py     # Options spread analysis
├── utils/
│   ├── __init__.py
│   └── display.py             # Console output formatting
├── config.py                  # Configuration parameters
├── main.py                    # Main application entry point
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (create this)
└── README.md                  # This file
```

## API Endpoints Used

- `/sessions` - Authentication
- `/public-watchlists/{name}` - Watchlist symbols
- `/market-metrics` - IV rank and percentile data
- `/market-data/by-type?equity=` - Stock quotes
- `/option-chains/{symbol}/nested` - Option expirations and strikes
- `/market-data/by-type?equity-option=` - Option quotes with greeks

## Testing with Postman

After authentication, the session token is displayed in the console. Use it to test API endpoints:

**Headers:**
```
Authorization: <your-session-token>
```

**Example Requests:**
```
GET https://api.tastytrade.com/market-metrics?symbols=AAPL,MSFT
GET https://api.tastytrade.com/market-data/by-type?equity=AAPL
GET https://api.tastytrade.com/option-chains/AAPL/nested
```

## Troubleshooting

**Import Errors:**
- Ensure you've activated the virtual environment
- Verify all `__init__.py` files exist in package directories

**Authentication Failed:**
- Check credentials in `.env` file
- Verify Tastytrade account has API access enabled

**No Opportunities Found:**
- Lower `IV_RANK_THRESHOLD` in config.py
- Increase `MAX_RISK_REWARD_RATIO` to be less restrictive
- Adjust `TARGET_DTE` or `DTE_TOLERANCE` for more flexibility

**Empty Watchlist:**
- Watchlist names must match exactly (case-sensitive)
- Falls back to hardcoded S&P 500 and ETF lists if watchlists fail

## Notes

- Session tokens expire after ~24 hours of inactivity
- Rate limiting: Built-in delays between batch requests
- The screener focuses on PUT credit spreads (selling premium in high IV)
- All prices and strikes are in USD

## License

This project is for personal use. Ensure compliance with Tastytrade's API terms of service.

## Support

For issues or questions, refer to the Tastytrade API documentation:
https://developer.tastytrade.com/
