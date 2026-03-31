"""
Tastytrade API wrapper for options screening
"""

import requests
import os
import base64
import json
from typing import List, Dict, Optional, Any
import time
from datetime import datetime
from urllib.parse import quote
from utils import cache
import config


# Fallback S&P 500 symbols (top liquid names) if watchlist fails
SP500_FALLBACK = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "BRK.B",
    "UNH",
    "JNJ",
    "V",
    "WMT",
    "XOM",
    "LLY",
    "JPM",
    "MA",
    "PG",
    "AVGO",
    "HD",
    "CVX",
    "MRK",
    "ABBV",
    "COST",
    "PEP",
    "KO",
    "ADBE",
    "MCD",
    "CSCO",
    "TMO",
    "ACN",
    "ABT",
    "CRM",
    "NFLX",
    "VZ",
    "DHR",
    "NKE",
    "WFC",
    "DIS",
    "TXN",
    "CMCSA",
    "PM",
    "ORCL",
    "INTC",
    "AMD",
    "QCOM",
    "UNP",
    "BMY",
    "INTU",
    "UPS",
    "RTX",
    "COP",
    "MS",
    "GE",
    "IBM",
    "BA",
    "CAT",
    "GS",
    "HON",
    "LOW",
    "T",
    "AMGN",
    "SPGI",
    "ELV",
    "SBUX",
    "BLK",
    "DE",
    "LMT",
    "AXP",
    "BKNG",
    "GILD",
    "PLD",
    "MDLZ",
    "ADI",
    "TJX",
    "SYK",
    "MMC",
    "VRTX",
    "ADP",
    "CVS",
    "CB",
    "CI",
    "C",
    "REGN",
    "AMT",
    "ZTS",
    "SO",
    "ISRG",
    "MO",
    "BDX",
    "DUK",
    "ITW",
    "SCHW",
    "TGT",
    "NOC",
    "PNC",
    "USB",
    "MMM",
    "CL",
    "EOG",
    "BSX",
]


class TastytradeAPI:
    BASE_URL = "https://api.tastytrade.com"

    def __init__(self):
        self.session_token = None
        self.account_id = None
        self.session = requests.Session()
        self.debug = False  # Set to True to see raw API responses
        self.session.headers.update(self._build_default_headers())

    def _build_default_headers(self) -> Dict[str, str]:
        accept_version = os.getenv(
            "TASTYTRADE_ACCEPT_VERSION"
        ) or datetime.now().strftime("%Y%m%d")
        return {
            "User-Agent": os.getenv("TASTYTRADE_USER_AGENT", "highIV/1.0"),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Version": accept_version,
        }

    @staticmethod
    def _decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload_b64 + padding)
            return json.loads(decoded.decode("utf-8"))
        except Exception:
            return None

    def _print_postman_setup(self, authorization_value: str) -> None:
        """Print Postman Authorization header details for manual API testing."""
        print("=" * 80)
        print("📋 POSTMAN SETUP - Copy this token for Authorization header:")
        print("=" * 80)
        print("Header Name:  Authorization")
        print(f"Header Value: {authorization_value}")
        print("=" * 80)
        print()

    def _is_token_expired(self, token: str, leeway_seconds: int = 60) -> bool:
        payload = self._decode_jwt_payload(token)
        if not payload:
            return False

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return False

        return time.time() >= (float(exp) - leeway_seconds)

    def authenticate(self) -> bool:
        """
        Authenticate with Tastytrade API and get session token
        Returns True if successful
        """
        try:
            # Try cached session token first
            client_id = os.getenv("TASTYTRADE_CLIENT_ID")
            client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
            refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")

            cache_key = f"session_token:{client_id}"
            if not client_id:
                print("✗ TASTYTRADE_CLIENT_ID not set in environment")
                return False
            cached_token = cache.get(
                cache_key,
                ttl_seconds=config.CACHE_TTL_SESSION,
                cache_dir=config.CACHE_DIR,
            )
            if cached_token:
                raw_token = str(cached_token).split()[-1]
                if self._is_token_expired(raw_token):
                    print("✗ Cached session token is expired; re-authenticating")
                else:
                    self.session_token = cached_token
                    auth_value = (
                        cached_token
                        if str(cached_token).lower().startswith("bearer ")
                        else f"Bearer {cached_token}"
                    )
                    self.session.headers.update({"Authorization": auth_value})
                    print()
                    print("✓ Using cached session token")
                    print()
                    self._print_postman_setup(auth_value)
                    return True

            if client_id and client_secret and refresh_token:
                return self._authenticate_oauth(
                    client_id, client_secret, refresh_token, cache_key
                )

            print(
                "✗ OAuth credentials not found. Set TASTYTRADE_CLIENT_ID, TASTYTRADE_CLIENT_SECRET, and TASTYTRADE_REFRESH_TOKEN."
            )
            return False

        except requests.exceptions.RequestException as e:
            print(f"✗ Authentication failed: {e}")
            response = getattr(e, "response", None)
            if response is not None:
                try:
                    print(f"✗ Auth response status: {response.status_code}")
                    print(f"✗ Auth response body: {response.text}")
                except Exception:
                    pass
            return False

    def _authenticate_oauth(
        self, client_id: str, client_secret: str, refresh_token: str, cache_key: str
    ) -> bool:
        url = f"{self.BASE_URL}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        token = (
            data.get("access_token")
            or data.get("data", {}).get("access_token")
            or data.get("data", {}).get("access-token")
        )
        token_type = (
            data.get("token_type") or data.get("data", {}).get("token_type") or "Bearer"
        )

        if not token:
            raise requests.exceptions.RequestException(
                "Missing access token in OAuth response"
            )

        self.session_token = token
        auth_value = (
            token if str(token_type).lower().startswith("bearer") else f"Bearer {token}"
        )
        if not auth_value.lower().startswith("bearer "):
            auth_value = f"Bearer {token}"
        self.session.headers.update({"Authorization": auth_value})

        # Cache token for a short window; access tokens are short-lived
        cache.set(cache_key, token, cache_dir=config.CACHE_DIR)

        print()
        print("✓ Successfully authenticated with Tastytrade (OAuth)")
        print()
        self._print_postman_setup(auth_value)
        return True

    def list_watchlists(
        self, include_public: bool = True, include_private: bool = True
    ) -> List[Dict]:
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
                for item in data["data"]["items"]:
                    watchlists.append(
                        {
                            "name": item.get("name"),
                            "watchlist_id": item.get("id"),
                            "order_index": item.get("order-index"),
                            "scope": "public"
                            if endpoint == "public-watchlists"
                            else "private",
                        }
                    )
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
                cached = cache.get(
                    cache_key,
                    ttl_seconds=config.CACHE_TTL_WATCHLIST,
                    cache_dir=config.CACHE_DIR,
                )
                if cached:
                    print(
                        f"✓ Retrieved {len(cached)} symbols from cache for {endpoint} '{watchlist_name}'"
                    )
                    return cached

                url = f"{self.BASE_URL}/{endpoint}/{encoded}"
                response = self.session.get(url)
                response.raise_for_status()

                data = response.json()
                symbols = [item["symbol"] for item in data["data"]["watchlist-entries"]]
                print(
                    f"✓ Retrieved {len(symbols)} symbols from {endpoint} '{watchlist_name}'"
                )
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

            print(f"\n{'=' * 80}")
            print(f"DEBUG: {label}")
            print(f"{'=' * 80}")
            print(json.dumps(data, indent=2))
            print(f"{'=' * 80}\n")

    def get_market_metrics(self, symbols: List[str]) -> Dict:
        """
        Get market metrics (IV Rank, IV Percentile, etc.) for a list of symbols
        Returns dictionary with symbol as key and metrics as value
        """
        try:
            metrics_by_symbol = {}
            symbols_to_fetch = []
            for sym in symbols:
                cached = cache.get(
                    f"metrics:{sym}",
                    ttl_seconds=config.CACHE_TTL_MARKET_METRICS,
                    cache_dir=config.CACHE_DIR,
                )
                if cached:
                    # Refresh stale cache entries that predate added fields.
                    if "earnings_date" not in cached or "market_cap" not in cached:
                        symbols_to_fetch.append(sym)
                    else:
                        metrics_by_symbol[sym] = cached
                else:
                    symbols_to_fetch.append(sym)

            if symbols_to_fetch:
                symbols_str = ",".join(symbols_to_fetch)
                url = f"{self.BASE_URL}/market-metrics"
                params = {"symbols": symbols_str}
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                self._debug_print(f"Market Metrics Response for {symbols_str}", data)
                for item in data["data"]["items"]:
                    symbol = item["symbol"]
                    iv_rank_raw = item.get("implied-volatility-index-rank")
                    iv_percentile_raw = item.get("implied-volatility-percentile")
                    market_cap_raw = (
                        item.get("market-cap")
                        or item.get("market_cap")
                        or item.get("marketCapitalization")
                    )
                    earnings = item.get("earnings") or {}
                    earnings_date = earnings.get("expected-report-date")
                    iv_rank = float(iv_rank_raw) * 100 if iv_rank_raw else None
                    iv_percentile = (
                        float(iv_percentile_raw) * 100 if iv_percentile_raw else None
                    )
                    record = {
                        "symbol": symbol,
                        "iv_rank": iv_rank,
                        "iv_percentile": iv_percentile,
                        "iv_index": item.get("implied-volatility-index"),
                        "liquidity_rating": item.get("liquidity-rating"),
                        "liquidity_value": item.get("liquidity-value"),
                        "market_cap": float(market_cap_raw)
                        if market_cap_raw is not None
                        else None,
                        "earnings_date": earnings_date,
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
            params = {"equity": symbol}
            response = self.session.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            items = data["data"]["items"]

            if not items:
                print(f"✗ No quote data found for {symbol}")
                return None

            quote = items[0]

            return {
                "symbol": symbol,
                "last_price": float(quote.get("last")) if quote.get("last") else None,
                "bid": float(quote.get("bid")) if quote.get("bid") else None,
                "ask": float(quote.get("ask")) if quote.get("ask") else None,
                "volume": float(quote.get("volume")) if quote.get("volume") else None,
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
                cached = cache.get(
                    f"quote:{sym}",
                    ttl_seconds=config.CACHE_TTL_QUOTES,
                    cache_dir=config.CACHE_DIR,
                )
                if cached:
                    quotes_by_symbol[sym] = cached
                else:
                    symbols_to_fetch.append(sym)

            if symbols_to_fetch:
                batch_size = config.EQUITY_QUOTE_BATCH_SIZE
                for i in range(0, len(symbols_to_fetch), batch_size):
                    batch = symbols_to_fetch[i : i + batch_size]
                    batch_quotes = self._fetch_equity_quotes_resilient(batch)
                    for symbol, record in batch_quotes.items():
                        quotes_by_symbol[symbol] = record
                        cache.set(f"quote:{symbol}", record, cache_dir=config.CACHE_DIR)

                # Fallback: fetch any still-missing symbols one-by-one so a failed batch
                # does not silently drop valid candidates from downstream analysis.
                missing_symbols = [
                    sym for sym in symbols_to_fetch if sym not in quotes_by_symbol
                ]
                if missing_symbols:
                    print(
                        f"⚠ {len(missing_symbols)} symbols missing from batch quotes; retrying individually"
                    )
                    for sym in missing_symbols:
                        single_quote = self.get_quote(sym)
                        if single_quote:
                            quotes_by_symbol[sym] = single_quote
                            cache.set(
                                f"quote:{sym}", single_quote, cache_dir=config.CACHE_DIR
                            )

            # print(f"✓ Retrieved quotes for {len(quotes_by_symbol)} symbols (API fetched {len(symbols_to_fetch)})")
            return quotes_by_symbol
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get batch quotes: {e}")
            return {}

    def _parse_equity_quote_item(self, requested_symbol: str, quote_item: Dict) -> Dict:
        """Parse one equity quote item into the canonical quote record format."""
        market_cap_raw = (
            quote_item.get("market-cap")
            or quote_item.get("market_cap")
            or quote_item.get("market-capitalization")
            or quote_item.get("marketCapitalization")
        )
        return {
            "symbol": requested_symbol,
            "last_price": float(quote_item.get("last"))
            if quote_item.get("last")
            else None,
            "bid": float(quote_item.get("bid")) if quote_item.get("bid") else None,
            "ask": float(quote_item.get("ask")) if quote_item.get("ask") else None,
            "volume": float(quote_item.get("volume"))
            if quote_item.get("volume")
            else None,
            "market_cap": float(market_cap_raw) if market_cap_raw else None,
            "is_trading_halted": quote_item.get("is-trading-halted", False),
        }

    def _fetch_equity_quotes_resilient(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch equity quotes for a symbol list.
        If a batch fails with HTTP 400, recursively split to isolate problematic symbols.
        """
        if not symbols:
            return {}

        symbols_str = ",".join(symbols)
        url = f"{self.BASE_URL}/market-data/by-type"
        params = {"equity": symbols_str}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            items = data["data"].get("items", [])

            requested_map = {sym.upper(): sym for sym in symbols}
            normalized_map = {sym.replace("/", ".").upper(): sym for sym in symbols}

            parsed_quotes: Dict[str, Dict] = {}
            for item in items:
                response_symbol = str(item.get("symbol") or "")
                key_upper = response_symbol.upper()
                requested_symbol = (
                    requested_map.get(key_upper)
                    or normalized_map.get(key_upper)
                    or response_symbol
                )
                parsed_quotes[requested_symbol] = self._parse_equity_quote_item(
                    requested_symbol, item
                )

            return parsed_quotes

        except requests.exceptions.RequestException as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code == 400 and len(symbols) > 1:
                mid = len(symbols) // 2
                left = self._fetch_equity_quotes_resilient(symbols[:mid])
                right = self._fetch_equity_quotes_resilient(symbols[mid:])
                combined = {}
                combined.update(left)
                combined.update(right)
                return combined

            if len(symbols) == 1:
                print(f"⚠ Failed to get equity quote for {symbols[0]}: {error}")
            else:
                print(
                    f"⚠ Failed to get equity quote batch ({len(symbols)} symbols): {error}"
                )
            return {}

    def get_option_expirations(self, symbol: str) -> List[Dict]:
        """
        Get available option expiration dates for a symbol
        Returns list of expiration info with DTE
        """
        try:
            cache_key = f"expirations:{symbol}"
            # Use same_day=True so morning runs always refresh DTE
            cached = cache.get(
                cache_key,
                ttl_seconds=config.CACHE_TTL_EXPIRATIONS,
                cache_dir=config.CACHE_DIR,
                same_day=True,
            )
            if cached:
                return cached

            url = f"{self.BASE_URL}/option-chains/{symbol}/nested"
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            self._debug_print(f"Option Expirations Response for {symbol}", data)

            # Debug: check response structure
            if (
                "data" not in data
                or "items" not in data["data"]
                or not data["data"]["items"]
            ):
                print(f"✗ Unexpected response structure for {symbol}: {data}")
                return []

            expirations = []

            # Expirations are nested in items[0].expirations
            for exp in data["data"]["items"][0]["expirations"]:
                expirations.append(
                    {
                        "expiration_date": exp["expiration-date"],
                        "days_to_expiration": exp["days-to-expiration"],
                        "expiration_type": exp["expiration-type"],
                    }
                )

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
            cached = cache.get(
                cache_key,
                ttl_seconds=config.CACHE_TTL_OPTION_CHAIN,
                cache_dir=config.CACHE_DIR,
            )
            if cached:
                # Normalize strike keys back to float (JSON stores keys as strings)
                if "strikes" in cached:
                    cached["strikes"] = {
                        float(k): v for k, v in cached["strikes"].items()
                    }
                return cached

            url = f"{self.BASE_URL}/option-chains/{symbol}/nested"
            response = self.session.get(url)
            response.raise_for_status()

            data = response.json()

            # Debug: check response structure
            if (
                "data" not in data
                or "items" not in data["data"]
                or not data["data"]["items"]
            ):
                print(f"✗ Unexpected response structure for {symbol}")
                return {}

            items = data["data"]["items"][0]

            # Find the matching expiration
            target_expiration = None
            for exp in items.get("expirations", []):
                if exp["expiration-date"] == expiration_date:
                    target_expiration = exp
                    break

            if not target_expiration:
                print(f"✗ Expiration {expiration_date} not found for {symbol}")
                return {}

            # Check if strikes key exists
            if "strikes" not in target_expiration:
                print(f"✗ No 'strikes' key in expiration for {symbol}")
                return {}

            # Organize options by strike
            chain = {"symbol": symbol, "expiration": expiration_date, "strikes": {}}

            # Parse the strikes - note these only contain option symbols, not full quotes
            for strike_data in target_expiration["strikes"]:
                strike = float(strike_data["strike-price"])

                chain["strikes"][strike] = {
                    "put_symbol": strike_data.get("put"),
                    "call_symbol": strike_data.get("call"),
                    "strike_price": strike,
                }

            print(
                f"✓ Retrieved {len(chain['strikes'])} strikes for {symbol} exp {expiration_date}"
            )
            # Cache as-is (keys will serialize to strings); normalize on read
            cache.set(cache_key, chain, cache_dir=config.CACHE_DIR)
            return chain

        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get option chain for {symbol}: {e}")
            return {}
        except (KeyError, IndexError) as e:
            print(f"✗ Error parsing option chain for {symbol}: {e}")
            return {}

    def get_option_quotes(
        self, option_symbols: List[str], batch_size: int = 50
    ) -> Dict[str, Dict]:
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
            cached = cache.get(
                f"optquote:{sym}",
                ttl_seconds=config.CACHE_TTL_OPTION_QUOTES,
                cache_dir=config.CACHE_DIR,
            )
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
            batch = to_fetch[i : i + batch_size]
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
            symbols_encoded = ",".join([quote(sym, safe="") for sym in option_symbols])
            url = f"{self.BASE_URL}/market-data/by-type?equity-option={symbols_encoded}"
            response = self.session.get(url)
            response.raise_for_status()

            data = response.json()
            items = data["data"]["items"]

            quotes_by_symbol = {}
            for opt in items:
                symbol = opt.get("symbol")
                quotes_by_symbol[symbol] = {
                    "symbol": symbol,
                    "bid": float(opt.get("bid")) if opt.get("bid") else None,
                    "ask": float(opt.get("ask")) if opt.get("ask") else None,
                    "last": float(opt.get("last")) if opt.get("last") else None,
                    "delta": float(opt.get("delta")) if opt.get("delta") else None,
                    "implied_volatility": float(opt.get("volatility"))
                    if opt.get("volatility")
                    else None,
                    "theta": float(opt.get("theta")) if opt.get("theta") else None,
                    "gamma": float(opt.get("gamma")) if opt.get("gamma") else None,
                    "vega": float(opt.get("vega")) if opt.get("vega") else None,
                    "open_interest": int(float(opt.get("open-interest")))
                    if opt.get("open-interest")
                    else None,
                    "volume": int(float(opt.get("volume")))
                    if opt.get("volume")
                    else None,
                    # Some feeds may include trading status; capture if present
                    "is_trading_halted": opt.get("is-trading-halted", False),
                }

            return quotes_by_symbol

        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get option quotes: {e}")
            return {}

    def batch_request_with_delay(
        self, symbols: List[str], batch_size: int = 100, delay: float = 0.5
    ):
        """
        Helper method to batch large requests with delays to respect rate limits
        """
        results = {}

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            batch_results = self.get_market_metrics(batch)
            results.update(batch_results)

            # Add delay between batches if not the last batch
            if i + batch_size < len(symbols):
                time.sleep(delay)

        return results

    def get_account_positions(self, account_number: Optional[str] = None) -> List[Dict]:
        """
        Get all current positions from account
        Returns list of position dictionaries
        """
        if account_number is None:
            account_number = config.TASTYTRADE_ACCOUNT_NUMBER

        try:
            url = f"{self.BASE_URL}/accounts/{account_number}/positions"
            response = self.session.get(url)
            response.raise_for_status()

            data = response.json()
            positions = data.get("data", {}).get("items", [])

            print(
                f"✓ Retrieved {len(positions)} positions from account {account_number}"
            )
            return positions

        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to get account positions: {e}")
            return []

    def parse_option_spreads(self, positions: List[Dict]) -> List[Dict]:
        """
        Parse individual option positions into spread pairs
        Groups short + long puts by underlying symbol and expiration
        Returns list of spread dictionaries with entry/current data
        """
        from datetime import datetime, date
        import re

        # Filter to only option positions
        option_positions = [
            p for p in positions if p.get("instrument-type") == "Equity Option"
        ]

        # Group by underlying + expiration
        spreads_map = {}

        for pos in option_positions:
            symbol = pos.get("underlying-symbol")
            expiration_str = pos.get(
                "expires-at", ""
            )  # "2026-02-27T21:00:00.000+00:00"
            quantity_direction = pos.get("quantity-direction")
            option_symbol = pos.get("symbol")  # "STX   260227P00265000"

            # Parse expiration date
            try:
                expiration_date = datetime.fromisoformat(
                    expiration_str.replace("+00:00", "")
                ).date()
            except Exception:
                continue

            # Extract strike from option symbol (last 8 chars before decimals)
            # Format: "STX   260227P00265000" -> strike 265
            match = re.search(r"P(\d{8})$", option_symbol.replace(" ", ""))
            if not match:
                continue
            strike = int(match.group(1)) / 1000  # 00265000 -> 265.0

            # Create spread key
            spread_key = f"{symbol}_{expiration_date}"

            if spread_key not in spreads_map:
                spreads_map[spread_key] = {
                    "symbol": symbol,
                    "expiration": expiration_date,
                    "short_legs": [],
                    "long_legs": [],
                }

            # Read quantity and store one leg entry per contract so that
            # multi-contract positions (e.g. 2x ASTS 75/70) produce the correct
            # number of spread pairs instead of collapsing to one.
            # NOTE: trades opened and closed between consecutive syncs will never
            # appear here; they are an inherent limitation of position-diff tracking.
            try:
                quantity = int(float(pos.get("quantity") or 1))
            except (TypeError, ValueError):
                quantity = 1
            quantity = max(quantity, 1)

            leg_data = {
                "strike": strike,
                "option_symbol": option_symbol,
                "avg_open_price": float(pos.get("average-open-price", 0)),
                "close_price": float(pos.get("close-price", 0)),
                "created_at": pos.get("created-at"),
            }

            if quantity_direction == "Short":
                for _ in range(quantity):
                    spreads_map[spread_key]["short_legs"].append(dict(leg_data))
            elif quantity_direction == "Long":
                for _ in range(quantity):
                    spreads_map[spread_key]["long_legs"].append(dict(leg_data))

        # Build spread records
        spreads = []
        today = date.today()

        for spread_key, spread_data in spreads_map.items():
            short_legs = spread_data.get("short_legs", [])
            long_legs = spread_data.get("long_legs", [])

            if not short_legs or not long_legs:
                continue

            # Sort strikes descending to pair nearest strikes together
            short_legs_sorted = sorted(
                short_legs, key=lambda x: x["strike"], reverse=True
            )
            long_legs_sorted = sorted(
                long_legs, key=lambda x: x["strike"], reverse=True
            )

            pair_count = min(len(short_legs_sorted), len(long_legs_sorted))

            for i in range(pair_count):
                short_leg = short_legs_sorted[i]
                long_leg = long_legs_sorted[i]

                # Calculate metrics
                entry_credit = (
                    short_leg["avg_open_price"] - long_leg["avg_open_price"]
                ) * 100
                current_mark = (
                    short_leg["close_price"] - long_leg["close_price"]
                ) * 100
                current_pnl = entry_credit - current_mark
                current_pnl_pct = (
                    (current_pnl / entry_credit * 100) if entry_credit > 0 else 0
                )

                width = short_leg["strike"] - long_leg["strike"]
                dte_remaining = (spread_data["expiration"] - today).days

                # Parse entry date from created_at
                try:
                    entry_date_str = short_leg["created_at"]
                    entry_date = datetime.fromisoformat(
                        entry_date_str.replace("+00:00", "")
                    ).date()
                    days_held = (today - entry_date).days
                except Exception:
                    entry_date = None
                    days_held = None

                # Generate trade_id: YYYY-MM-DD_SYMBOL_EXP_STRIKE_WIDTH
                # Includes expiration and width for uniqueness (handles multiple spreads same day/strike)
                exp_str = spread_data["expiration"].isoformat()
                width_int = int(width)
                if entry_date:
                    trade_id = f"{entry_date}_{spread_data['symbol']}_{exp_str}_{int(short_leg['strike'])}_{width_int}"
                else:
                    trade_id = f"{spread_data['symbol']}_{exp_str}_{int(short_leg['strike'])}_{width_int}"

                spread_record = {
                    "trade_id": trade_id,
                    "symbol": spread_data["symbol"],
                    "entry_date": entry_date,
                    "expiration": spread_data["expiration"],
                    "short_strike": short_leg["strike"],
                    "long_strike": long_leg["strike"],
                    "width": width,
                    "entry_credit": round(entry_credit, 2),
                    "buying_power_used": round((width * 100) - entry_credit, 2),
                    "current_mark": round(current_mark, 2),
                    "current_pnl": round(current_pnl, 2),
                    "current_pnl_pct": round(current_pnl_pct, 1),
                    "dte_remaining": dte_remaining,
                    "days_held": days_held,
                    "short_option_symbol": short_leg["option_symbol"],
                    "long_option_symbol": long_leg["option_symbol"],
                }

                spreads.append(spread_record)

        return spreads
