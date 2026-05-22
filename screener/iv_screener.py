"""
IV Screening logic - filters stocks by IV Rank and other criteria
"""

import pandas as pd

import config


class IVScreener:
    def __init__(self, iv_rank_threshold: float = config.IV_RANK_THRESHOLD):
        self.iv_rank_threshold = iv_rank_threshold
        self.min_stock_price = getattr(config, "MIN_STOCK_PRICE", 10.0)
        self.min_underlying_volume = config.MIN_UNDERLYING_VOLUME
        self.min_tasty_liquidity_rating = getattr(
            config, "MIN_TASTY_LIQUIDITY_RATING", 2
        )
        self.min_market_cap = config.MIN_MARKET_CAP

    def filter_by_iv_rank(self, metrics_data: dict) -> pd.DataFrame:
        """
        Filter stocks by IV Rank threshold and trading status
        Returns DataFrame sorted by IV Rank descending
        """
        if not metrics_data:
            return pd.DataFrame()

        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame.from_dict(metrics_data, orient="index")

        # Ensure numeric types (API may return strings)
        for col in [
            "iv_rank",
            "iv_percentile",
            "iv_index",
            "volume",
            "volume_for_filter",
            "liquidity_rating",
            "liquidity_value",
            "liquidity_rank",
            "market_cap",
            "last",
            "last_price",
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Filter out rows with missing IV Rank
        df = df[df["iv_rank"].notna()]

        # Filter by IV Rank threshold
        df = df[df["iv_rank"] >= self.iv_rank_threshold]

        # Require minimum stock price (filters penny stocks)
        price_col = "last_price" if "last_price" in df.columns else "last"
        if price_col in df.columns:
            before_price = len(df)
            missing_price = int(df[price_col].isna().sum())
            price_mask = df[price_col].isna() | (df[price_col] >= self.min_stock_price)
            df = df[price_mask]
            filtered_price = before_price - len(df)
            if filtered_price > 0:
                print(
                    f"⚠ Filtered out {filtered_price} penny stocks (< ${self.min_stock_price})"
                )
            if missing_price > 0:
                print(
                    f"⚠ {missing_price} symbols missing stock price; price filter skipped for them"
                )
        else:
            print(
                "⚠ No stock price column found ('last_price'/'last'); price filter skipped"
            )

        # Prefer Tasty's options-liquidity score; fall back to underlying share volume.
        volume_col = (
            "volume_for_filter" if "volume_for_filter" in df.columns else "volume"
        )
        if "liquidity_rating" in df.columns:
            before_liquidity = len(df)
            missing_liquidity = int(df["liquidity_rating"].isna().sum())
            liquidity_mask = df["liquidity_rating"].isna() | (
                df["liquidity_rating"] >= self.min_tasty_liquidity_rating
            )
            df = df[liquidity_mask]
            filtered_liquidity = before_liquidity - len(df)
            if filtered_liquidity > 0:
                print(
                    f"⚠ Filtered out {filtered_liquidity} low Tasty-liquidity names "
                    f"(< rating {self.min_tasty_liquidity_rating})"
                )
            if missing_liquidity > 0:
                print(
                    f"⚠ {missing_liquidity} symbols missing Tasty liquidity rating; "
                    "falling back to volume for them"
                )

        if volume_col in df.columns:
            volume_fallback_mask = (
                df["liquidity_rating"].isna()
                if "liquidity_rating" in df.columns
                else pd.Series(True, index=df.index)
            )
            before_volume = len(df)
            missing_volume = int(df.loc[volume_fallback_mask, volume_col].isna().sum())
            volume_mask = (
                (~volume_fallback_mask)
                | df[volume_col].isna()
                | (df[volume_col] >= self.min_underlying_volume)
            )
            df = df[volume_mask]
            filtered_volume = before_volume - len(df)
            if filtered_volume > 0:
                volume_label = (
                    "projected full-day volume"
                    if volume_col == "volume_for_filter"
                    else "underlying volume"
                )
                print(
                    f"⚠ Filtered out {filtered_volume} low-volume names by {volume_label} (< {self.min_underlying_volume:,})"
                )
            if missing_volume > 0:
                print(
                    f"⚠ {missing_volume} symbols missing underlying volume; volume fallback skipped for them"
                )

        # Require minimum market cap
        if "market_cap" in df.columns:
            before_market_cap = len(df)
            market_cap_not_applicable = df["market_cap"].isna() | (
                df["market_cap"] <= 0
            )
            missing_market_cap = int(market_cap_not_applicable.sum())
            market_cap_mask = market_cap_not_applicable | (
                df["market_cap"] >= self.min_market_cap
            )
            df = df[market_cap_mask]
            filtered_market_cap = before_market_cap - len(df)
            if filtered_market_cap > 0:
                print(
                    f"⚠ Filtered out {filtered_market_cap} small-cap names (< ${self.min_market_cap:,})"
                )
            if missing_market_cap > 0:
                missing_cap_df = df[market_cap_not_applicable.loc[df.index]]
                if "symbol" in missing_cap_df.columns:
                    missing_cap_symbols = (
                        missing_cap_df["symbol"].dropna().astype(str).tolist()
                    )
                else:
                    missing_cap_symbols = [
                        str(idx) for idx in missing_cap_df.index.tolist()
                    ]
                preview_count = min(20, len(missing_cap_symbols))
                preview = ", ".join(missing_cap_symbols[:preview_count])
                print(
                    f"⚠ {missing_market_cap} symbols missing/non-applicable market cap; allowed through market-cap filter"
                )
                if preview:
                    print(
                        f"   Market-cap not applicable ({preview_count}/{len(missing_cap_symbols)}): {preview}"
                    )
                    if len(missing_cap_symbols) > preview_count:
                        print("   ...and more")

        # Filter out trading halts (if field is present)
        if "is_trading_halted" in df.columns:
            # Coerce to strict bool to avoid NA masks from partial quote coverage.
            halted_mask = (
                df["is_trading_halted"]
                .map(lambda v: str(v).strip().lower() in {"true", "1", "yes", "y"})
                .fillna(False)
                .astype(bool)
            )
            halted_count = halted_mask.sum()
            df = df[~halted_mask]
            if halted_count > 0:
                print(f"⚠ Filtered out {halted_count} halted securities")

        # Sort by IV Rank descending
        df = df.sort_values("iv_rank", ascending=False)

        print(
            f"✓ Found {len(df)} symbols after IV Rank, liquidity, market-cap, and halt filters"
        )

        return df

    def get_top_candidates(
        self, df: pd.DataFrame, max_results: int = config.MAX_SCREENING_RESULTS
    ) -> list[str]:
        """
        Get top N candidates from filtered DataFrame
        Returns list of symbols
        """
        top_df = df.head(max_results)
        if len(df) > max_results:
            print(
                f"⚠ Analyzing top {max_results} of {len(df)} screened symbols by IV Rank"
            )

        return top_df["symbol"].tolist()

    def display_screening_results(self, df: pd.DataFrame, max_display: int = 20):
        """
        Display IV screening results in a formatted table
        """
        if len(df) == 0:
            print("\n✗ No stocks found matching IV criteria")
            return

        display_df = df.head(max_display).copy()

        # Select and rename columns for display
        display_cols = ["symbol", "iv_rank", "iv_percentile", "iv_index"]
        display_df = display_df[display_cols]

        # Round numeric values
        display_df["iv_rank"] = display_df["iv_rank"].round(1)
        display_df["iv_percentile"] = display_df["iv_percentile"].round(1)
        display_df["iv_index"] = display_df["iv_index"].round(2)

        print(f"\n{'=' * 60}")
        print(f"Top {len(display_df)} High IV Stocks")
        print(f"{'=' * 60}")
        print(display_df.to_string(index=False))
        print(f"{'=' * 60}\n")
