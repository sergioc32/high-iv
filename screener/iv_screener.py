"""
IV Screening logic - filters stocks by IV Rank and other criteria
"""
import pandas as pd
from typing import List, Dict
import config


class IVScreener:
    def __init__(self, iv_rank_threshold: float = config.IV_RANK_THRESHOLD):
        self.iv_rank_threshold = iv_rank_threshold
    
    def filter_by_iv_rank(self, metrics_data: Dict) -> pd.DataFrame:
        """
        Filter stocks by IV Rank threshold and trading status
        Returns DataFrame sorted by IV Rank descending
        """
        if not metrics_data:
            return pd.DataFrame()

        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame.from_dict(metrics_data, orient='index')

        # Ensure numeric types (API may return strings)
        for col in ['iv_rank', 'iv_percentile', 'iv_index']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Filter out rows with missing IV Rank
        df = df[df['iv_rank'].notna()]

        # Filter by IV Rank threshold
        df = df[df['iv_rank'] >= self.iv_rank_threshold]
        
        # Filter out trading halts (if field is present)
        if 'is_trading_halted' in df.columns:
            halted_count = df[df['is_trading_halted'] == True].shape[0]
            df = df[df['is_trading_halted'] != True]
            if halted_count > 0:
                print(f"⚠ Filtered out {halted_count} halted securities")

        # Sort by IV Rank descending
        df = df.sort_values('iv_rank', ascending=False)

        print(f"✓ Found {len(df)} stocks with IV Rank >= {self.iv_rank_threshold}%")

        return df
    
    def get_top_candidates(self, df: pd.DataFrame, max_results: int = config.MAX_SCREENING_RESULTS) -> List[str]:
        """
        Get top N candidates from filtered DataFrame
        Returns list of symbols
        """
        top_df = df.head(max_results)
        
        return top_df['symbol'].tolist()
    
    def display_screening_results(self, df: pd.DataFrame, max_display: int = 20):
        """
        Display IV screening results in a formatted table
        """
        if len(df) == 0:
            print("\n✗ No stocks found matching IV criteria")
            return
        
        display_df = df.head(max_display).copy()
        
        # Select and rename columns for display
        display_cols = ['symbol', 'iv_rank', 'iv_percentile', 'iv_index']
        display_df = display_df[display_cols]
        
        # Round numeric values
        display_df['iv_rank'] = display_df['iv_rank'].round(1)
        display_df['iv_percentile'] = display_df['iv_percentile'].round(1)
        display_df['iv_index'] = display_df['iv_index'].round(2)
        
        print(f"\n{'='*60}")
        print(f"Top {len(display_df)} High IV Stocks")
        print(f"{'='*60}")
        print(display_df.to_string(index=False))
        print(f"{'='*60}\n")