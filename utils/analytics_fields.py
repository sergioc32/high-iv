"""Shared analytics field groups used across CSV schemas."""

MARKET_CLASSIFICATION_FIELDS = [
    "sector",
    "industry",
]

THEME_FIELD_NAMES = [
    "risk_theme_tags",
    "technical_theme_tags",
    "theme_tags",
    "theme_taxonomy_version",
]

MARKET_CONTEXT_FIELDS = MARKET_CLASSIFICATION_FIELDS + THEME_FIELD_NAMES
