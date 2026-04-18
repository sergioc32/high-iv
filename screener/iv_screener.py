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

        # Require minimum underlying share volume
        if "volume" in df.columns:
            before_volume = len(df)
            missing_volume = int(df["volume"].isna().sum())
            volume_mask = df["volume"].isna() | (
                df["volume"] >= self.min_underlying_volume
            )
            df = df[volume_mask]
            filtered_volume = before_volume - len(df)
            if filtered_volume > 0:
                print(
                    f"⚠ Filtered out {filtered_volume} low-volume names (< {self.min_underlying_volume:,})"
                )
            if missing_volume > 0:
                print(
                    f"⚠ {missing_volume} symbols missing underlying volume; volume filter skipped for them"
                )

        # Require minimum market cap
        if "market_cap" in df.columns:
            before_market_cap = len(df)
            missing_market_cap = int(df["market_cap"].isna().sum())
            market_cap_mask = df["market_cap"].isna() | (
                df["market_cap"] >= self.min_market_cap
            )
            df = df[market_cap_mask]
            filtered_market_cap = before_market_cap - len(df)
            if filtered_market_cap > 0:
                print(
                    f"⚠ Filtered out {filtered_market_cap} small-cap names (< ${self.min_market_cap:,})"
                )
            if missing_market_cap > 0:
                missing_cap_df = df[df["market_cap"].isna()]
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
                    f"⚠ {missing_market_cap} symbols missing market cap; market-cap filter skipped for them"
                )
                if preview:
                    print(
                        f"   Missing market-cap symbols ({preview_count}/{len(missing_cap_symbols)}): {preview}"
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
            f"✓ Found {len(df)} stocks after IV Rank, volume, market-cap, and halt filters"
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
