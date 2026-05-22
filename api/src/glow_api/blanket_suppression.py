"""
Blanket suppression logic for protecting student privacy.

Blanket suppression prevents differencing attacks by suppressing the entire
result if ANY group has a count in the range (0, MIN_N).

Key principles:
- If any observed group has 0 < n < MIN_N, suppress the ENTIRE result
- Empty groups (n=0) are safe and don't trigger suppression
- Each school is checked independently
- Applies to all dimensions used in filters and aggregations
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def sanitize_for_json(value):
    """
    Convert numpy types and NaN values to JSON-serializable Python types.

    Args:
        value: Any value that might be a numpy type or NaN

    Returns:
        JSON-serializable Python value (None for NaN/inf)
    """
    # Handle NaN and inf values
    if pd.isna(value) or (isinstance(value, float) and not np.isfinite(value)):
        return None

    # Convert numpy types to Python types
    if isinstance(value, (np.integer, np.floating)):
        return value.item()

    # Handle numpy bool
    if isinstance(value, np.bool_):
        return bool(value)

    # Return as-is if already a native Python type
    return value


def sanitize_data_for_json(data: list[dict]) -> list[dict]:
    """
    Sanitize a list of dictionaries for JSON serialization.

    Converts numpy types to Python types and NaN/inf to None.

    Args:
        data: List of dictionaries from pandas operations

    Returns:
        List of dictionaries with JSON-serializable values
    """
    return [
        {key: sanitize_for_json(value) for key, value in row.items()} for row in data
    ]


def check_blanket_suppression(
    df: pd.DataFrame,
    school: str,
    group_by: list[str],
    min_n: int,
    variable: str | None = None,
) -> bool:
    """
    Check if a query result should be blanket suppressed.

    Args:
        df: DataFrame filtered to the relevant cohort (after filters applied)
        school: School name to check
        group_by: List of columns to group by (dimensions)
        min_n: Minimum group size threshold (typically 5)
        variable: Variable being aggregated (for mean calculations).
                  If provided, NA values in this variable are excluded from counts.

    Returns:
        True if the result should be suppressed, False if safe to show
    """
    # MIN_N of 0 disables suppression
    if min_n == 0:
        return False

    # Filter to the specific school
    school_df = df[df["school"] == school] if "school" in df.columns else df

    # If no data for this school, it's safe (nothing to suppress)
    if len(school_df) == 0:
        return False

    # For mean calculations, drop NA values in the variable column
    # since they don't contribute to the mean or count
    if variable and variable in school_df.columns:
        school_df = school_df.dropna(subset=[variable])
        # After dropping NAs, check again if we have data
        if len(school_df) == 0:
            return False

    # If no grouping, check overall count
    if not group_by:
        n = len(school_df)
        if 0 < n < min_n:
            logger.info(
                f"Blanket suppression triggered for {school}: "
                f"overall count n={n} < MIN_N={min_n}"
            )
            return True
        return False

    # Group by the specified dimensions and count
    # We use the 'uid' column to count unique students if it exists,
    # otherwise count rows
    count_col = "uid" if "uid" in school_df.columns else school_df.columns[0]

    try:
        counts = school_df.groupby(group_by, dropna=False)[count_col].nunique()
    except KeyError:
        # If grouping columns don't exist, treat as safe
        logger.warning(
            f"Grouping columns {group_by} not found in DataFrame. Treating as safe."
        )
        return False

    # Check if any observed group has 0 < n < MIN_N
    unsafe_groups = counts[(counts > 0) & (counts < min_n)]

    if len(unsafe_groups) > 0:
        logger.info(
            f"Blanket suppression triggered for {school}: "
            f"{len(unsafe_groups)} group(s) with n < MIN_N={min_n}"
        )
        logger.debug(f"Unsafe groups:\n{unsafe_groups}")
        return True

    return False


def execute_query(
    df: pd.DataFrame,
    query_params: dict[str, Any],
    min_n: int,
) -> dict[str, dict[str, Any]]:
    """
    Execute a query with blanket suppression for each wave.

    Args:
        df: Full DataFrame
        query_params: Query parameters including:
            - school: School name
            - variable: Variable to aggregate (e.g., "bw_wbeing_1")
            - waves: List of wave values to query (required)
            - group_by: List of dimensions to group by
            - filters: Dict of column -> value filters to apply (excluding wave)
        min_n: Minimum group size threshold

    Returns:
        Dict keyed by wave value, each containing:
            - suppressed: bool
            - data: list of results (if not suppressed)
            - message: str (if suppressed)
    """
    school = query_params["school"]
    variable = query_params["variable"]
    waves = query_params.get("waves", [])
    group_by = query_params.get("group_by", [])
    filters = query_params.get("filters", {})

    if not waves:
        raise ValueError("At least one wave must be specified")

    results = {}

    for wave in waves:
        # Apply base filters
        filtered_df = df.copy()
        for col, value in filters.items():
            if col in filtered_df.columns:
                t = filtered_df[col].dtype
                if isinstance(value, list):
                    filtered_df = filtered_df[
                        filtered_df[col].isin([t.type(v) for v in value])
                    ]
                else:
                    filtered_df = filtered_df[filtered_df[col] == t.type(value)]

        # Apply wave filter
        if "wave" in filtered_df.columns:
            t = filtered_df["wave"].dtype
            filtered_df = filtered_df[filtered_df["wave"] == t.type(wave)]

        # Filter to the specific school
        if "school" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["school"] == school]

        # Check blanket suppression
        is_suppressed = check_blanket_suppression(
            df=filtered_df,
            school=school,
            group_by=group_by,
            min_n=min_n,
            variable=variable,
        )

        if is_suppressed:
            results[wave] = {
                "suppressed": True,
                "message": (
                    "Results cannot be displayed due to small group sizes. "
                    "This protects individual student privacy."
                ),
            }
            continue

        # Compute aggregates
        if not group_by:
            # Overall mean - filter out NA values for the variable
            if variable in filtered_df.columns:
                filtered_for_mean = filtered_df.dropna(subset=[variable])
                mean_val = filtered_for_mean[variable].mean()
                count = (
                    filtered_for_mean["uid"].nunique()
                    if "uid" in filtered_for_mean.columns
                    else len(filtered_for_mean)
                )
            else:
                mean_val = None
                count = 0
            data = [{"mean": sanitize_for_json(mean_val), "student_n": count}]
        else:
            # Grouped means
            if variable not in filtered_df.columns:
                data = []
            else:
                # Filter out NA values for the variable before grouping
                filtered_for_mean = filtered_df.dropna(subset=[variable])
                grouped = (
                    filtered_for_mean.groupby(group_by, dropna=False)
                    .agg(
                        {
                            variable: "mean",
                            "uid": "nunique"
                            if "uid" in filtered_for_mean.columns
                            else "count",
                        }
                    )
                    .reset_index()
                )
                grouped.columns = list(group_by) + ["mean", "student_n"]
                data = sanitize_data_for_json(grouped.to_dict("records"))

        results[wave] = {
            "suppressed": False,
            "data": data,
        }

    return results


def execute_query_with_neighbors(
    df: pd.DataFrame,
    query_params: dict[str, Any],
    min_n: int,
) -> dict[str, Any]:
    """
    Execute a query for focus school and neighbor schools.

    Args:
        df: Full DataFrame
        query_params: Query parameters including:
            - school: Focus school name
            - variable: Variable to aggregate
            - waves: List of wave values to query (required)
            - group_by: List of dimensions to group by
            - filters: Dict of column -> value filters to apply (excluding wave)
            - neighbors: List of neighbor school names
        min_n: Minimum group size threshold

    Returns:
        Dict with:
            - focus: Wave-indexed results for focus school
            - neighbors: List of {school, results} where results are wave-indexed
    """
    neighbors = query_params.get("neighbors", [])

    # Execute query for focus school
    focus_params = query_params.copy()
    focus_result = execute_query(df, focus_params, min_n)

    # Execute queries for neighbors
    neighbor_results = []
    for neighbor_school in neighbors:
        neighbor_params = query_params.copy()
        neighbor_params["school"] = neighbor_school
        neighbor_result = execute_query(df, neighbor_params, min_n)

        # Always include neighbors, even if fully suppressed
        neighbor_results.append(
            {
                "school": neighbor_school,
                "results": neighbor_result,
            }
        )

    return {
        "focus": focus_result,
        "neighbors": neighbor_results,
    }
