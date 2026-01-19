"""
Main entry point for options put spread screener
"""
import os
import sys
import time
import argparse
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.tastytrade import TastytradeAPI, SP500_FALLBACK
from screener.iv_screener import IVScreener
from screener.spread_analyzer import SpreadAnalyzer
from utils.display import (
    display_opportunities, display_summary, 
    print_header, print_progress
)
from utils import cache
import config


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Options Put Spread Screener')
    parser.add_argument('--clear-cache-all', action='store_true', 
                       help='Clear all cached data and exit')
    parser.add_argument('--fresh-day', action='store_true',
                       help='Clear cache entries from previous days (recommended for morning runs)')
    args = parser.parse_args()
    
    # Handle cache clearing
    if args.clear_cache_all:
        count = cache.clear_all(cache_dir=config.CACHE_DIR)
        print(f"✓ Cleared {count} cache files from {config.CACHE_DIR}")
        return
    
    if args.fresh_day:
        count = cache.clear_stale_daily(cache_dir=config.CACHE_DIR)
        print(f"✓ Cleared {count} stale cache files from previous days")
        print()
    
    start_time = time.time()
    
    # Load environment variables
    load_dotenv()
    
    print_header()
    
    # Get credentials
    username = os.getenv('TASTYTRADE_USERNAME')
    password = os.getenv('TASTYTRADE_PASSWORD')
    
    print(f"Using Tastytrade username: {username}")
    print(f"Using Tastytrade password: {password}")
    if not username or not password:
        print("✗ Error: Tastytrade credentials not found in .env file")
        print("Please create a .env file with TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD")
        return
    
    # Initialize API client
    print_progress("Authenticating with Tastytrade")
    api = TastytradeAPI(username, password)
    
    # api.debug = True

    if not api.authenticate():
        print("✗ Authentication failed. Please check your credentials.")
        return
    
    # Discover available watchlists
    print_progress("Discovering available watchlists")
    watchlists = api.list_watchlists()
    
    # Step 1: Get watchlist symbols
    print_progress("Fetching watchlist symbols")
    
    all_symbols = []
    
    # Get S&P 500 watchlist (public) with fallback
    sp500_symbols = api.get_watchlist(config.WATCHLISTS['sp500'], public=True)
    if not sp500_symbols:
        print(f"⚠ S&P 500 watchlist not found, using fallback list of {len(SP500_FALLBACK)} liquid stocks")
        sp500_symbols = SP500_FALLBACK
    all_symbols.extend(sp500_symbols)

    # Get Liquid ETFs watchlist (public) with fallback
    etf_symbols = api.get_watchlist(config.WATCHLISTS['etfs'], public=True)
    if not etf_symbols:
        print(f"⚠ ETFs watchlist '{config.WATCHLISTS['etfs']}' not found, using fallback list of {len(config.ETF_FALLBACK)} ETFs")
        etf_symbols = config.ETF_FALLBACK
    all_symbols.extend(etf_symbols)

    # Get Tasty Default watchlist (public) with fallback
    # tasty_default_symbols = api.get_watchlist('tasty default', public=True)
    # if not tasty_default_symbols:
    #     print(f"⚠ Tasty Default watchlist not found, skipping")
    # else:
    #     all_symbols.extend(tasty_default_symbols)

    # Get High Options Volume watchlist (public) with fallback
    hov_symbols = api.get_watchlist('High Options Volume', public=True)
    if not hov_symbols:
        print(f"⚠ High Options Volume watchlist not found, skipping")
    else:
        all_symbols.extend(hov_symbols)

    print(f"✓ Retrieved {len(all_symbols)} symbols from watchlists before de-duplication")
    
    # Remove duplicates
    all_symbols = list(set(all_symbols))
    # Remove manually excluded symbols
    # if config.EXCLUDE_SYMBOLS:
    #     before = len(all_symbols)
    #     all_symbols = [s for s in all_symbols if s not in config.EXCLUDE_SYMBOLS]
    #     removed = before - len(all_symbols)
    #     if removed:
    #         print(f"⚠ Excluded {removed} symbols via EXCLUDE_SYMBOLS: {config.EXCLUDE_SYMBOLS}")
    
    print(f"✓ Total symbols to screen: {len(all_symbols)}")
    
    if not all_symbols:
        print("✗ No symbols found in watchlists")
        return
    
    # Step 2: Get market metrics and screen by IV Rank
    print_progress("Fetching market metrics (IV Rank, IV Percentile)")
    
    # Batch request with rate limiting
    metrics_data = api.batch_request_with_delay(all_symbols, batch_size=100, delay=1.0)
    
    if not metrics_data:
        print("✗ Failed to retrieve market metrics")
        return
    
    # Screen by IV Rank
    print_progress("Screening by IV Rank")
    screener = IVScreener()
    high_iv_df = screener.filter_by_iv_rank(metrics_data)
    # high_iv_df = []
    if len(high_iv_df) == 0:
        print(f"✗ No stocks found with IV Rank >= {config.IV_RANK_THRESHOLD}%")
        return
    
    # Display screening results
    screener.display_screening_results(high_iv_df, max_display=20)
    
    # Get top candidates for options analysis
    top_candidates = screener.get_top_candidates(high_iv_df)
    
    print(f"\n⟳ Analyzing options chains for top {len(top_candidates)} candidates...")
    print("   (This may take a few minutes)\n")
    
    # Step 3: Analyze options chains for each candidate
    analyzer = SpreadAnalyzer()
    opportunities = []
    
    # Fetch all quotes in one batch call for efficiency
    print_progress("Fetching quotes for candidates")
    quotes_data = api.get_quotes_batch(top_candidates)
    
    # Merge trading halt info into metrics data for filtering
    for symbol, quote in quotes_data.items():
        if symbol in metrics_data:
            metrics_data[symbol]['is_trading_halted'] = quote.get('is_trading_halted', False)
    
    # Re-filter after getting trading halt info
    high_iv_df = screener.filter_by_iv_rank(metrics_data)
    top_candidates = screener.get_top_candidates(high_iv_df)
    
    if len(top_candidates) == 0:
        print("✗ No candidates remain after filtering halted securities")
        return
    
    print(f"⟳ Analyzing options chains for {len(top_candidates)} remaining candidates...\n")
    
    # Step 3: Analyze options chains for each candidate
    analyzer = SpreadAnalyzer()
    opportunities = []
    
    for i, symbol in enumerate(top_candidates, 1):
        print(f"   [{i}/{len(top_candidates)}] Analyzing {symbol}...", end='\r')
        
        try:
            # Get current stock price from batch data
            quote = quotes_data.get(symbol)
            if not quote or not quote['last_price']:
                continue
            
            stock_price = quote['last_price']
            
            # Get option expirations
            expirations = api.get_option_expirations(symbol)
            if not expirations:
                continue
            
            # Find target expiration
            target_exp = analyzer.find_target_expiration(expirations)
            if not target_exp:
                continue
            
            # Get options chain for target expiration (returns option symbols)
            chain = api.get_option_chain(symbol, target_exp['expiration_date'])
            if not chain or not chain.get('strikes'):
                continue
            
            # Extract all put symbols from the chain
            put_symbols = [data['put_symbol'] for data in chain['strikes'].values() if data.get('put_symbol')]
            if not put_symbols:
                continue
            
            # Fetch option quotes with greeks for all puts
            option_quotes = api.get_option_quotes(put_symbols)
            if not option_quotes:
                continue
            
            # Merge option quotes back into chain structure
            for strike, data in chain['strikes'].items():
                put_symbol = data.get('put_symbol')
                if put_symbol and put_symbol in option_quotes:
                    data['put'] = option_quotes[put_symbol]
            
            # Evaluate put spread opportunity
            opportunity = analyzer.evaluate_spread(
                symbol, stock_price, chain, target_exp
            )
            
            if opportunity:
                opportunities.append(opportunity)
            
            # Small delay to avoid rate limiting
            time.sleep(0.3)
            
        except Exception as e:
            print(f"\n   ✗ Error analyzing {symbol}: {e}")
            continue
    
    print(f"\n✓ Completed options analysis")
    
    # Step 4: Filter and rank opportunities
    if opportunities:
        print_progress("Filtering and ranking opportunities")
        final_opportunities = analyzer.filter_opportunities(opportunities)
        
        # Display results
        display_opportunities(final_opportunities)
        
        # Auto-save to CSV if enabled
        if config.AUTO_SAVE_CSV:
            import pandas as pd
            df = pd.DataFrame(final_opportunities)
            filename = f"opportunities_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False)
            print(f"✓ Saved to {filename}")
    else:
        print("\n✗ No trade opportunities found matching all criteria")
    
    # Display summary
    execution_time = time.time() - start_time
    display_summary(
        len(all_symbols),
        len(high_iv_df),
        len(opportunities),
        execution_time
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Screening interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)