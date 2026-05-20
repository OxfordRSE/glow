"""Query utility functions for data catalog and filtering."""
import io
from decimal import Decimal, InvalidOperation

import pandas as pd

from glow_api.models import QueryCatalog, UserScope, Filter, FilterOp


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
