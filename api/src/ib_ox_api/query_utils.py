"""Query utility functions for data catalog and filtering."""

from decimal import Decimal, InvalidOperation

import pandas as pd

from ib_ox_api.models import QueryCatalog

# Columns allowed in group_by (categorical)
CATEGORICAL_WHITELIST: set[str] = {
    "school",
    "yearGroup",
    "class",
    "sex",
    "ethnicity",
    "wave",
    "d_city",
    "d_country",
}

# Questionnaire item columns from the #BeeWell GM Survey model
# (ib-ox-dummies examples/beewell_model.toml).
# Each tuple is (column_prefix, number_of_items).
_BW_QUESTIONNAIRES: list[tuple[str, int]] = [
    ("bw_migration", 3),
    ("bw_arrival", 1),
    ("bw_life_sat", 1),
    ("bw_wbeing", 7),
    ("bw_selfest", 5),
    ("bw_emoreg", 3),
    ("bw_appear", 1),
    ("bw_stress", 2),
    ("bw_coping", 2),
    ("bw_emodies", 10),
    ("bw_behav", 6),
    ("bw_physh", 1),
    ("bw_sleep", 1),
    ("bw_physact", 1),
    ("bw_physdur", 1),
    ("bw_fruitveg", 1),
    ("bw_unhealthy", 4),
    ("bw_freetime", 1),
    ("bw_socmedia", 1),
    ("bw_socmtype", 2),
    ("bw_volunteer", 1),
    ("bw_activ", 11),
    ("bw_schoolconn", 1),
    ("bw_attain", 1),
    ("bw_staffrel", 4),
    ("bw_iso", 1),
    ("bw_isodays", 1),
    ("bw_isodur", 1),
    ("bw_schpress", 1),
    ("bw_homeenv", 1),
    ("bw_safety", 1),
    ("bw_localenv", 4),
    ("bw_beinheard", 1),
    ("bw_foodsec", 1),
    ("bw_material", 1),
    ("bw_future", 7),
    ("bw_careersed", 1),
    ("bw_careershlp", 1),
    ("bw_plans", 8),
    ("bw_gmacs", 2),
    ("bw_parentsrel", 4),
    ("bw_friends", 4),
    ("bw_lonely", 1),
    ("bw_discrim", 5),
    ("bw_discloc", 7),
    ("bw_bullying", 3),
    ("bw_support", 1),
    ("bw_mhcontact", 6),
    ("bw_kooth", 1),
]

# Columns allowed in value_columns for means (numeric)
# All individual questionnaire items
NUMERIC_WHITELIST: set[str] = {
    f"{prefix}_{i}"
    for prefix, n_items in _BW_QUESTIONNAIRES
    for i in range(1, n_items + 1)
} | {"d_age"}

# Add derived subscale and scale totals
_DERIVED_TOTALS = {
    "bw_migration_total",
    "bw_wbeing_total",
    "bw_selfest_total",
    "bw_emoreg_total",
    "bw_stress_total",
    "bw_coping_total",
    "bw_emodies_total",
    "bw_behav_total",
    "bw_unhealthy_total",
    "bw_socmtype_total",
    "bw_activ_total",
    "bw_staffrel_total",
    "bw_localenv_total",
    "bw_future_total",
    "bw_plans_total",
    "bw_gmacs_total",
    "bw_parentsrel_total",
    "bw_friends_total",
    "bw_discrim_total",
    "bw_discloc_total",
    "bw_bullying_total",
    "bw_mhcontact_total",
}

NUMERIC_WHITELIST = NUMERIC_WHITELIST | _DERIVED_TOTALS

# All subscale and scale total scores computed during data ingestion
DERIVED_SCORE_NAMES = _DERIVED_TOTALS


def _normalize_comparable_value(value: object) -> str:
    """Normalize numeric-like values so "1" and "1.0" compare identically."""
    if pd.isna(value):
        return ""

    if isinstance(value, str):
        stripped = value.strip()
        try:
            decimal_value = Decimal(stripped)
        except InvalidOperation:
            return stripped
    elif isinstance(value, (int, float)):
        try:
            decimal_value = Decimal(str(value))
        except InvalidOperation:
            return str(value)
    else:
        return str(value)

    normalized = decimal_value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))

    as_text = format(normalized, "f")
    return as_text.rstrip("0").rstrip(".")


def _series_as_strings(df: pd.DataFrame, column: str) -> pd.Series:
    if column == "wave":
        return df[column].map(_normalize_comparable_value)
    return df[column].astype(str)


def _filter_values_as_strings(column: str, values: list[object]) -> list[str]:
    if column == "wave":
        return [_normalize_comparable_value(v) for v in values]
    return [str(v) for v in values]


def apply_user_scope(df: pd.DataFrame, scope) -> pd.DataFrame:
    """Apply the user's pre-filters to the DataFrame."""
    for col, allowed_values in scope.filters.items():
        if col not in df.columns:
            continue
        series = _series_as_strings(df, col)
        df = df[series.isin(_filter_values_as_strings(col, list(allowed_values)))]
    return df


def build_query_catalog(df: pd.DataFrame) -> QueryCatalog:
    """Build a catalog of available dimensions, measures, and values from the dataframe.
    
    This is used by the /data/describe endpoint to provide metadata about available
    variables, aggregation options, and filter options to the frontend.
    """
    value_suggestions: dict[str, list[str]] = {}
    for column in sorted(CATEGORICAL_WHITELIST):
        if column not in df.columns:
            continue
        series = _series_as_strings(df.dropna(subset=[column]), column)
        value_suggestions[column] = sorted(series.dropna().astype(str).unique().tolist())[:50]

    waves = value_suggestions.get("wave", [])

    return QueryCatalog(
        dimensions=sorted(col for col in CATEGORICAL_WHITELIST if col in df.columns),
        measures=sorted(col for col in NUMERIC_WHITELIST if col in df.columns),
        scores=sorted(DERIVED_SCORE_NAMES),
        waves=waves,
        value_suggestions=value_suggestions,
        step_types=[],  # No longer used - kept for API compatibility
    )
