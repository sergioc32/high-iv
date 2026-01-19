"""
Tastytrade API wrapper for options screening
"""
import requests
import os
from typing import List, Dict, Optional, Any
import time
from urllib.parse import quote
from utils import cache
import config


# Fallback S&P 500 symbols (top liquid names) if watchlist fails
SP500_FALLBACK = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B', 'UNH', 'JNJ',
    'V', 'WMT', 'XOM', 'LLY', 'JPM', 'MA', 'PG', 'AVGO', 'HD', 'CVX',
    'MRK', 'ABBV', 'COST', 'PEP', 'KO', 'ADBE', 'MCD', 'CSCO', 'TMO', 'ACN',
    'ABT', 'CRM', 'NFLX', 'VZ', 'DHR', 'NKE', 'WFC', 'DIS', 'TXN', 'CMCSA',
    'PM', 'ORCL', 'INTC', 'AMD', 'QCOM', 'UNP', 'BMY', 'INTU', 'UPS', 'RTX',
    'COP', 'MS', 'GE', 'IBM', 'BA', 'CAT', 'GS', 'HON', 'LOW', 'T',
    'AMGN', 'SPGI', 'ELV', 'SBUX', 'BLK', 'DE', 'LMT', 'AXP', 'BKNG', 'GILD',
    'PLD', 'MDLZ', 'ADI', 'TJX', 'SYK', 'MMC', 'VRTX', 'ADP', 'CVS', 'CB',
    'CI', 'C', 'REGN', 'AMT', 'ZTS', 'SO', 'ISRG', 'MO', 'BDX', 'DUK',
    'ITW', 'SCHW', 'TGT', 'NOC', 'PNC', 'USB', 'MMM', 'CL', 'EOG', 'BSX'
]


class TastytradeAPI:
    BASE_URL = "https://api.tastytrade.com"
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session_token = None
        self.account_id = None
        self.session = requests.Session()
        self.debug = False  # Set to True to see raw API responses
        
    def authenticate(self) -> bool:
        """
        Authenticate with Tastytrade API and get session token
        Returns True if successful
        """
        try:
            # Try cached session token first
            cache_key = f"session_token:{self.username}"
            cached_token = cache.get(cache_key, ttl_seconds=config.CACHE_TTL_SESSION, cache_dir=config.CACHE_DIR)
            if cached_token:
                self.session_token = cached_token
                self.session.headers.update({'Authorization': self.session_token})
                print()
                print("✓ Using cached session token")
                print()
                print("=" * 80)
                print("📋 POSTMAN SETUP - Copy this token for Authorization header:")
                print("=" * 80)
                print(f"Header Name:  Authorization")
                print(f"Header Value: {self.session_token}")
                print("=" * 80)
                print()
                return True

            url = f"{self.BASE_URL}/sessions"
            payload = {
                "login": self.username,
                "password": self.password
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            self.session_token = data['data']['session-token']
            
            # Set auth header for future requests
            self.session.headers.update({
                'Authorization': self.session_token
            })
            # Cache the session token
            cache.set(cache_key, self.session_token, cache_dir=config.CACHE_DIR)
            
            print()
            print("✓ Successfully authenticated with Tastytrade")
            print()
            print("=" * 80)
            print("📋 POSTMAN SETUP - Copy this token for Authorization header:")
            print("=" * 80)
            print(f"Header Name:  Authorization")
            print(f"Header Value: {self.session_token}")
            print("=" * 80)
            print()
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Authentication failed: {e}")
            return False
    
    def list_watchlists(self, include_public: bool = True, include_private: bool = True) -> List[Dict]:
        """
        List available watchlists. Public watchlists are platform-provided; private are user-created.
        Returns list of watchlist info with names and IDs.
        """
        watchlists: List[Dict] = []
        endpoints = []
        if include_private:
            endpoints.append("watchlists")
        if include_public:
            endpoints.append("public-watchlists")

        for endpoint in endpoints:
            try:
                url = f"{self.BASE_URL}/{endpoint}"
                response = self.session.get(url)
                response.raise_for_status()

                data = response.json()
                for item in data['data']['items']:
                    watchlists.append({
                        'name': item.get('name'),
                        'watchlist_id': item.get('id'),
                        'order_index': item.get('order-index'),
                        'scope': 'public' if endpoint == 'public-watchlists' else 'private'
                    })
            except requests.exceptions.RequestException as e:
                print(f"✗ Failed to list {endpoint}: {e}")

        if watchlists:
            print(f"✓ Found {len(watchlists)} watchlists:")
            # for wl in watchlists:
            #     print(f"   - {wl['name']} ({wl['scope']})")
        else:
            print("✗ No watchlists found")

        return watchlists

    def get_watchlist(self, watchlist_name: str, public: bool = False) -> List[str]:
        """
        Get symbols from a watchlist by name or ID.
        - Set public=True to force the public-watchlists endpoint.
        - If public=False, will try private first and then public as a fallback.
        """
        encoded = quote(str(watchlist_name), safe="")
        endpoints = []
        if public:
            endpoints.append("public-watchlists")
        endpoints.append("watchlists")
        if not public:
            endpoints.append("public-watchlists")

        for endpoint in endpoints:
            try:
                # Check cache first
                cache_key = f"watchlist:{endpoint}:{watchlist_name}"
                cached = cache.get(cache_key, ttl_seconds=config.CACHE_TTL_WATCHLIST, cache_dir=config.CACHE_DIR)
                if cached:
                    print(f"✓ Retrieved {len(cached)} symbols from cache for {endpoint} '{watchlist_name}'")
                    return cached

                url = f"{self.BASE_URL}/{endpoint}/{encoded}"
                response = self.session.get(url)
                response.raise_for_status()

                data = response.json()
                symbols = [item['symbol'] for item in data['data']['watchlist-entries']]
                print(f"✓ Retrieved {len(symbols)} symbols from {endpoint} '{watchlist_name}'")
                cache.set(cache_key, symbols, cache_dir=config.CACHE_DIR)
                return symbols
            except requests.exceptions.HTTPError as http_err:
                if response.status_code == 404:
                    # Try next endpoint
                    continue
                print(f"✗ Failed to get {endpoint} '{watchlist_name}': {http_err}")
            except requests.exceptions.RequestException as e:
                print(f"✗ Failed to get {endpoint} '{watchlist_name}': {e}")

        print(f"✗ Watchlist '{watchlist_name}' not found in private or public scope")
        return []
    
    def _debug_print(self, label: str, data: Any) -> None:
        """Print debug info if debug mode is enabled"""
        if self.debug:
            import json
            print(f"\n{'='*80}")
            print(f"DEBUG: {label}")
            print(f"{'='*80}")
            print(json.dumps(data, indent=2))
            print(f"{'='*80}\n")
    
    def get_market_metrics(self, symbols: List[str]) -> Dict:
        """
        Get market metrics (IV Rank, IV Percentile, etc.) for a list of symbols
        Returns dictionary with symbol as key and metrics as value
        """
        try:
            metrics_by_symbol = {}
            symbols_to_fetch = []
            for sym in symbols:
                cached = cache.get(f"metrics:{sym}", ttl_seconds=config.CACHE_TTL_MARKET_METRICS, cache_dir=config.CACHE_DIR)
                if cached:
                    metrics_by_symbol[sym] = cached
                else:
                    symbols_to_fetch.append(sym)

            if symbols_to_fetch:
                symbols_str = ','.join(symbols_to_fetch)
                url = f"{self.BASE_URL}/market-metrics"
                params = {'symbols': symbols_str}
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                self._debug_print(f"Market Metrics Response for {symbols_str}", data)
                for item in data['data']['items']:
                    symbol = item['symbol']
                    iv_rank_raw = item.get('implied-volatility-index-rank')
                    iv_percentile_raw = item.get('implied-volatility-percentile')
                    iv_rank = float(iv_rank_raw) * 100 if iv_rank_raw else None
                    iv_percentile = float(iv_percentile_raw) * 100 if iv_percentile_raw else None
                    record = {
                        'symbol': symbol,
                        'iv_rank': iv_rank,
                        'iv_percentile': iv_percentile,
                        'iv_index': item.get('implied-volatility-index'),
                        'liquidity_rating': item.get('liquidity-rating'),
                        'liquidity_value': item.get('liquidity-value')
                    }
                    metrics_by_symbol[symbol] = record
                    cache.set(f"metrics:{symbol}", record, cache_dir=config.CACHE_DIR)

            # print(f"✓ Retrieved market metrics for {len(metrics_by_symbol)} symbols (API fetched {len(symbols_to_fetch)})")
            return metrics_by_symbol
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get market metrics: {e}")
            return {}
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        Get current quote for a symbol using market-data endpoint
        """
        try:
            url = f"{self.BASE_URL}/market-data/by-type"
            params = {'equity': symbol}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            items = data['data']['items']
            
            if not items:
                print(f"✗ No quote data found for {symbol}")
                return None
            
            quote = items[0]
            
            return {
                'symbol': symbol,
                'last_price': float(quote.get('last')) if quote.get('last') else None,
                'bid': float(quote.get('bid')) if quote.get('bid') else None,
                'ask': float(quote.get('ask')) if quote.get('ask') else None,
                'volume': float(quote.get('volume')) if quote.get('volume') else None
            }
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get quote for {symbol}: {e}")
            return None
    
    def get_quotes_batch(self, symbols: List[str]) -> Dict[str, Optional[Dict]]:
        """
        Get quotes for multiple symbols in a single batch call
        Returns dictionary with symbol as key and quote data as value
        """
        if not symbols:
            return {}
        
        try:
            quotes_by_symbol = {}
            symbols_to_fetch = []
            for sym in symbols:
                cached = cache.get(f"quote:{sym}", ttl_seconds=config.CACHE_TTL_QUOTES, cache_dir=config.CACHE_DIR)
                if cached:
                    quotes_by_symbol[sym] = cached
                else:
                    symbols_to_fetch.append(sym)

            if symbols_to_fetch:
                symbols_str = ','.join(symbols_to_fetch)
                url = f"{self.BASE_URL}/market-data/by-type"
                params = {'equity': symbols_str}
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                self._debug_print(f"Equity Quotes Response for {symbols_str}", data)
                items = data['data']['items']
                for q in items:
                    symbol = q.get('symbol')
                    record = {
                        'symbol': symbol,
                        'last_price': float(q.get('last')) if q.get('last') else None,
                        'bid': float(q.get('bid')) if q.get('bid') else None,
                        'ask': float(q.get('ask')) if q.get('ask') else None,
                        'volume': float(q.get('volume')) if q.get('volume') else None,
                        'is_trading_halted': q.get('is-trading-halted', False)
                    }
                    quotes_by_symbol[symbol] = record
                    cache.set(f"quote:{symbol}", record, cache_dir=config.CACHE_DIR)

            # print(f"✓ Retrieved quotes for {len(quotes_by_symbol)} symbols (API fetched {len(symbols_to_fetch)})")
            return quotes_by_symbol
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get batch quotes: {e}")
            return {}
    
    def get_option_expirations(self, symbol: str) -> List[Dict]:
        """
        Get available option expiration dates for a symbol
        Returns list of expiration info with DTE
        """
        try:
            cache_key = f"expirations:{symbol}"
            # Use same_day=True so morning runs always refresh DTE
            cached = cache.get(cache_key, ttl_seconds=config.CACHE_TTL_EXPIRATIONS, cache_dir=config.CACHE_DIR, same_day=True)
            if cached:
                return cached

            url = f"{self.BASE_URL}/option-chains/{symbol}/nested"
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            self._debug_print(f"Option Expirations Response for {symbol}", data)
            
            # Debug: check response structure
            if 'data' not in data or 'items' not in data['data'] or not data['data']['items']:
                print(f"✗ Unexpected response structure for {symbol}: {data}")
                return []
            
            expirations = []
            
            # Expirations are nested in items[0].expirations
            for exp in data['data']['items'][0]['expirations']:
                expirations.append({
                    'expiration_date': exp['expiration-date'],
                    'days_to_expiration': exp['days-to-expiration'],
                    'expiration_type': exp['expiration-type']
                })
            
            cache.set(cache_key, expirations, cache_dir=config.CACHE_DIR)
            return expirations
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get expirations for {symbol}: {e}")
            return []
        except (KeyError, IndexError) as e:
            print(f"✗ Error parsing expirations for {symbol}: {e}")
            return []
    
    def get_option_chain(self, symbol: str, expiration_date: str) -> Dict:
        """
        Get option chain strikes for a specific symbol and expiration.
        Note: This returns option symbols only. To get quotes/greeks, use get_option_quotes.
        Returns dictionary with puts and calls organized by strike
        """
        try:
            cache_key = f"chain:{symbol}:{expiration_date}"
            cached = cache.get(cache_key, ttl_seconds=config.CACHE_TTL_OPTION_CHAIN, cache_dir=config.CACHE_DIR)
            if cached:
                # Normalize strike keys back to float (JSON stores keys as strings)
                if 'strikes' in cached:
                    cached['strikes'] = {float(k): v for k, v in cached['strikes'].items()}
                return cached

            url = f"{self.BASE_URL}/option-chains/{symbol}/nested"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Debug: check response structure
            if 'data' not in data or 'items' not in data['data'] or not data['data']['items']:
                print(f"✗ Unexpected response structure for {symbol}")
                return {}
            
            items = data['data']['items'][0]
            
            # Find the matching expiration
            target_expiration = None
            for exp in items.get('expirations', []):
                if exp['expiration-date'] == expiration_date:
                    target_expiration = exp
                    break
            
            if not target_expiration:
                print(f"✗ Expiration {expiration_date} not found for {symbol}")
                return {}
            
            # Check if strikes key exists
            if 'strikes' not in target_expiration:
                print(f"✗ No 'strikes' key in expiration for {symbol}")
                return {}
            
            # Organize options by strike
            chain = {
                'symbol': symbol,
                'expiration': expiration_date,
                'strikes': {}
            }
            
            # Parse the strikes - note these only contain option symbols, not full quotes
            for strike_data in target_expiration['strikes']:
                strike = float(strike_data['strike-price'])
                
                chain['strikes'][strike] = {
                    'put_symbol': strike_data.get('put'),
                    'call_symbol': strike_data.get('call'),
                    'strike_price': strike
                }
            
            print(f"✓ Retrieved {len(chain['strikes'])} strikes for {symbol} exp {expiration_date}")
            # Cache as-is (keys will serialize to strings); normalize on read
            cache.set(cache_key, chain, cache_dir=config.CACHE_DIR)
            return chain
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get option chain for {symbol}: {e}")
            return {}
        except (KeyError, IndexError) as e:
            print(f"✗ Error parsing option chain for {symbol}: {e}")
            return {}
    
    def get_option_quotes(self, option_symbols: List[str], batch_size: int = 50) -> Dict[str, Dict]:
        """
        Get quotes for option symbols including bid/ask/greeks
        Uses batching to avoid URL length limits for symbols with many strikes
        Returns dictionary with option symbol as key
        """
        if not option_symbols:
            return {}
        
        # Build from cache, fetch only missing symbols
        all_quotes = {}
        to_fetch = []
        for sym in option_symbols:
            cached = cache.get(f"optquote:{sym}", ttl_seconds=config.CACHE_TTL_OPTION_QUOTES, cache_dir=config.CACHE_DIR)
            if cached:
                all_quotes[sym] = cached
            else:
                to_fetch.append(sym)

        if not to_fetch:
            return all_quotes

        # If few symbols, do single request; else batch
        if len(to_fetch) <= batch_size:
            fetched = self._fetch_option_quotes_batch(to_fetch)
            for k, v in fetched.items():
                all_quotes[k] = v
                cache.set(f"optquote:{k}", v, cache_dir=config.CACHE_DIR)
            return all_quotes

        for i in range(0, len(to_fetch), batch_size):
            batch = to_fetch[i:i + batch_size]
            batch_quotes = self._fetch_option_quotes_batch(batch)
            for k, v in batch_quotes.items():
                all_quotes[k] = v
                cache.set(f"optquote:{k}", v, cache_dir=config.CACHE_DIR)
            if i + batch_size < len(to_fetch):
                time.sleep(0.2)
        
        return all_quotes
    
    def _fetch_option_quotes_batch(self, option_symbols: List[str]) -> Dict[str, Dict]:
        """
        Internal method to fetch a single batch of option quotes
        """
        try:
            # Option symbols include spaces; encode each symbol to preserve spaces as %20
            symbols_encoded = ','.join([quote(sym, safe='') for sym in option_symbols])
            url = f"{self.BASE_URL}/market-data/by-type?equity-option={symbols_encoded}"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            items = data['data']['items']
            
            quotes_by_symbol = {}
            for opt in items:
                symbol = opt.get('symbol')
                quotes_by_symbol[symbol] = {
                    'symbol': symbol,
                    'bid': float(opt.get('bid')) if opt.get('bid') else None,
                    'ask': float(opt.get('ask')) if opt.get('ask') else None,
                    'last': float(opt.get('last')) if opt.get('last') else None,
                    'delta': float(opt.get('delta')) if opt.get('delta') else None,
                    'theta': float(opt.get('theta')) if opt.get('theta') else None,
                    'gamma': float(opt.get('gamma')) if opt.get('gamma') else None,
                    'vega': float(opt.get('vega')) if opt.get('vega') else None,
                    'open_interest': int(float(opt.get('open-interest'))) if opt.get('open-interest') else None,
                    'volume': int(float(opt.get('volume'))) if opt.get('volume') else None,
                    # Some feeds may include trading status; capture if present
                    'is_trading_halted': opt.get('is-trading-halted', False)
                }
            
            return quotes_by_symbol
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get option quotes: {e}")
            return {}
    
    def batch_request_with_delay(self, symbols: List[str], batch_size: int = 100, delay: float = 0.5):
        """
        Helper method to batch large requests with delays to respect rate limits
        """
        results = {}
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_results = self.get_market_metrics(batch)
            results.update(batch_results)
            
            # Add delay between batches if not the last batch
            if i + batch_size < len(symbols):
                time.sleep(delay)
        
        return results
