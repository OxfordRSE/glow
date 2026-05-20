import io
from decimal import Decimal, InvalidOperation

import pandas as pd

from glow_api.models import (
    Filter,
    FilterOp,
    FrequencyQuery,
    FrequencyResult,
    FrequencyResultForWave,
    MeansQuery,
    MeansResult,
    MeansResultForWave,
    UserScope,
    WaveChangeQuery,
    WaveChangeResult,
)
from glow_api.suppression import suppress_frequency_table, suppress_means_table

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
# (glow-dummies examples/beewell_model.toml).
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


def _df_to_csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


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


def validate_frequency_query(query: FrequencyQuery, df_columns: set[str]) -> None:
    """Raise ValueError if the query references disallowed or missing columns."""
    for col in query.group_by:
        if col not in CATEGORICAL_WHITELIST:
            raise ValueError(
                f"Column '{col}' is not allowed in group_by. "
                f"Allowed: {sorted(CATEGORICAL_WHITELIST)}"
            )
        if col not in df_columns:
            raise ValueError(f"Column '{col}' does not exist in the dataset.")

    if query.value_column is not None:
        if query.value_column not in CATEGORICAL_WHITELIST:
            raise ValueError(
                f"value_column '{query.value_column}' is not in the allowed categorical columns. "
                f"Allowed: {sorted(CATEGORICAL_WHITELIST)}"
            )
        if query.value_column not in df_columns:
            raise ValueError(
                f"value_column '{query.value_column}' does not exist in the dataset."
            )

    for f in query.filters:
        if f.column not in df_columns:
            raise ValueError(f"Filter column '{f.column}' does not exist in the dataset.")


def validate_means_query(query: MeansQuery, df_columns: set[str]) -> None:
    """Raise ValueError if the query references disallowed or missing columns."""
    for col in query.group_by:
        if col not in CATEGORICAL_WHITELIST:
            raise ValueError(
                f"Column '{col}' is not allowed in group_by. "
                f"Allowed: {sorted(CATEGORICAL_WHITELIST)}"
            )
        if col not in df_columns:
            raise ValueError(f"Column '{col}' does not exist in the dataset.")

    for col in query.value_columns:
        if col not in NUMERIC_WHITELIST:
            raise ValueError(
                f"Column '{col}' is not allowed in value_columns. "
                f"Allowed: {sorted(NUMERIC_WHITELIST)}"
            )
        if col not in df_columns:
            raise ValueError(f"Column '{col}' does not exist in the dataset.")

    for f in query.filters:
        if f.column not in df_columns:
            raise ValueError(f"Filter column '{f.column}' does not exist in the dataset.")


def apply_user_scope(df: pd.DataFrame, scope: UserScope) -> pd.DataFrame:
    """Apply the user's pre-filters to the DataFrame."""
    for col, allowed_values in scope.filters.items():
        if col not in df.columns:
            continue
        series = _series_as_strings(df, col)
        df = df[series.isin(_filter_values_as_strings(col, list(allowed_values)))]
    return df


def _apply_single_filter(df: pd.DataFrame, f: Filter) -> pd.DataFrame:
    col = f.column
    val = f.value
    op = f.op
    str_series = _series_as_strings(df, col)

    if op == FilterOp.EQ:
        return df[str_series == _filter_values_as_strings(col, [val])[0]]
    if op == FilterOp.NE:
        return df[str_series != _filter_values_as_strings(col, [val])[0]]
    if op == FilterOp.IN:
        values = val if isinstance(val, list) else [val]
        return df[str_series.isin(_filter_values_as_strings(col, list(values)))]
    if op == FilterOp.GT:
        return df[pd.to_numeric(df[col], errors="coerce") > float(val)]  # type: ignore[arg-type]
    if op == FilterOp.LT:
        return df[pd.to_numeric(df[col], errors="coerce") < float(val)]  # type: ignore[arg-type]
    if op == FilterOp.GTE:
        return df[pd.to_numeric(df[col], errors="coerce") >= float(val)]  # type: ignore[arg-type]
    if op == FilterOp.LTE:
        return df[pd.to_numeric(df[col], errors="coerce") <= float(val)]  # type: ignore[arg-type]
    return df


def apply_filters(df: pd.DataFrame, filters: list[Filter]) -> pd.DataFrame:
    for f in filters:
        df = _apply_single_filter(df, f)
    return df


def execute_frequency_query(
    df: pd.DataFrame,
    query: FrequencyQuery,
    scope: UserScope,
    min_n: int,
) -> FrequencyResult:
    """Execute a frequency query for each specified wave.
    
    Returns a wave-indexed dictionary of results.
    """
    results = {}
    
    for wave in query.waves:
        # Apply user scope
        wave_df = apply_user_scope(df, scope)
        
        # Apply wave filter
        wave_filter = Filter(column="wave", op=FilterOp.EQ, value=wave)
        wave_df = _apply_single_filter(wave_df, wave_filter)
        
        # Apply other filters
        wave_df = apply_filters(wave_df, query.filters)

        result_df, suppressions = suppress_frequency_table(
            df=wave_df,
            group_cols=query.group_by,
            value_col=query.value_column,
            min_n=min_n,
        )

        # Convert SuppressionCode values to serialisable form
        serialisable: dict[str, dict[int, str]] = {
            col: {idx: code.value for idx, code in codes.items()}
            for col, codes in suppressions.items()
        }

        results[wave] = FrequencyResultForWave(
            csv=_df_to_csv(result_df),
            suppressions=serialisable,  # type: ignore[arg-type]
        )

    return FrequencyResult(results=results)


def execute_means_query(
    df: pd.DataFrame,
    query: MeansQuery,
    scope: UserScope,
    min_n: int,
) -> MeansResult:
    """Execute a means query for each specified wave.
    
    Returns a wave-indexed dictionary of results.
    """
    results = {}
    
    for wave in query.waves:
        # Apply user scope
        wave_df = apply_user_scope(df, scope)
        
        # Apply wave filter
        wave_filter = Filter(column="wave", op=FilterOp.EQ, value=wave)
        wave_df = _apply_single_filter(wave_df, wave_filter)
        
        # Apply other filters
        wave_df = apply_filters(wave_df, query.filters)

        means_df, counts_df, suppressions = suppress_means_table(
            df=wave_df,
            group_cols=query.group_by,
            value_cols=query.value_columns,
            min_n=min_n,
        )

        serialisable: dict[str, dict[int, str]] = {
            col: {idx: code.value for idx, code in codes.items()}
            for col, codes in suppressions.items()
        }

        results[wave] = MeansResultForWave(
            csv=_df_to_csv(means_df),
            count_csv=_df_to_csv(counts_df),
            suppressions=serialisable,  # type: ignore[arg-type]
        )

    return MeansResult(results=results)


def validate_wave_change_query(query: WaveChangeQuery, df_columns: set[str]) -> None:
    """Raise ValueError if the wave-change query references disallowed or missing columns."""
    if "wave" not in df_columns:
        raise ValueError("Dataset does not contain a 'wave' column required for wave-change queries.")

    for col in query.group_by:
        if col not in CATEGORICAL_WHITELIST:
            raise ValueError(
                f"Column '{col}' is not allowed in group_by. "
                f"Allowed: {sorted(CATEGORICAL_WHITELIST)}"
            )
        if col not in df_columns:
            raise ValueError(f"Column '{col}' does not exist in the dataset.")

    if not query.value_columns:
        raise ValueError("value_columns must not be empty.")

    for col in query.value_columns:
        if col not in NUMERIC_WHITELIST:
            raise ValueError(
                f"Column '{col}' is not allowed in value_columns. "
                f"Allowed: {sorted(NUMERIC_WHITELIST)}"
            )
        if col not in df_columns:
            raise ValueError(f"Column '{col}' does not exist in the dataset.")

    for f in query.filters:
        if f.column not in df_columns:
            raise ValueError(f"Filter column '{f.column}' does not exist in the dataset.")


def execute_wave_change_query(
    df: pd.DataFrame,
    query: WaveChangeQuery,
    scope: UserScope,
    min_n: int,
) -> WaveChangeResult:
    """Compute per-student within-person change between two waves.

    For each student (uid) that has observations in both from_wave and to_wave,
    the change in each value_column is computed as:
        change = value_at_to_wave - value_at_from_wave

    Those per-student differences are then optionally grouped by group_by columns
    (taken from the from_wave observation) and averaged. Suppression is applied
    based on the count of matched students per group.
    """
    df = apply_user_scope(df, scope)
    df = apply_filters(df, query.filters)

    wave_col = "wave"
    uid_col = "uid"

    # Split into baseline and comparison waves
    wave_series = _series_as_strings(df, wave_col)
    baseline = df[wave_series == _normalize_comparable_value(query.from_wave)].copy()
    comparison = df[wave_series == _normalize_comparable_value(query.to_wave)].copy()

    if baseline.empty or comparison.empty:
        # No matched data → return empty result
        empty_cols = (query.group_by + query.value_columns) if query.group_by else query.value_columns
        empty_df = pd.DataFrame(columns=empty_cols)
        return WaveChangeResult(
            csv=_df_to_csv(empty_df),
            count_csv=_df_to_csv(empty_df),
            suppressions={},
        )

    # Merge on uid to find students present in both waves
    merge_cols = [uid_col] + query.value_columns
    # Only keep columns we need from each wave to avoid name collisions
    baseline_cols = [uid_col] + query.value_columns + query.group_by
    comparison_cols = [uid_col] + query.value_columns

    # Keep only available columns
    baseline_cols = [c for c in baseline_cols if c in baseline.columns]
    comparison_cols = [c for c in comparison_cols if c in comparison.columns]

    merged = baseline[baseline_cols].merge(
        comparison[comparison_cols],
        on=uid_col,
        suffixes=("_from", "_to"),
    )

    if merged.empty:
        empty_cols = (query.group_by + query.value_columns) if query.group_by else query.value_columns
        empty_df = pd.DataFrame(columns=empty_cols)
        return WaveChangeResult(
            csv=_df_to_csv(empty_df),
            count_csv=_df_to_csv(empty_df),
            suppressions={},
        )

    # Compute per-student changes
    for col in query.value_columns:
        from_col = f"{col}_from" if f"{col}_from" in merged.columns else col
        to_col = f"{col}_to" if f"{col}_to" in merged.columns else col
        if from_col in merged.columns and to_col in merged.columns:
            merged[col] = pd.to_numeric(merged[to_col], errors="coerce") - pd.to_numeric(
                merged[from_col], errors="coerce"
            )
        else:
            merged[col] = float("nan")

    # Build working dataframe with uid, group_by cols, and change cols
    keep_cols = [uid_col] + query.group_by + query.value_columns
    keep_cols = [c for c in keep_cols if c in merged.columns]
    changes_df = merged[keep_cols].copy()

    # Apply suppression via suppress_means_table (reuses the same logic)
    from glow_api.suppression import suppress_means_table

    means_df, counts_df, suppressions = suppress_means_table(
        df=changes_df,
        group_cols=query.group_by,
        value_cols=query.value_columns,
        min_n=min_n,
    )

    serialisable: dict[str, dict[int, str]] = {
        col: {idx: code.value for idx, code in codes.items()}
        for col, codes in suppressions.items()
    }

    return WaveChangeResult(
        csv=_df_to_csv(means_df),
        count_csv=_df_to_csv(counts_df),
        suppressions=serialisable,  # type: ignore[arg-type]
    )
