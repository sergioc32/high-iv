"""
Put spread analyzer entry point.

This module gives the put strategy a dedicated import path while the legacy
``screener.spread_analyzer`` module remains available as a compatibility layer.
"""

from screener.spread_analyzer import PutSpreadAnalyzer

__all__ = ["PutSpreadAnalyzer"]
