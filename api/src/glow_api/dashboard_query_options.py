"""
Canonical query options builder for dashboard queries.

This module provides a single source of truth for what query capabilities
are available, used for both metadata delivery and request validation.
"""

import logging
from typing import Dict, Optional


from glow_api.data import DataFrameWithWhitelists
from glow_api.models import QueryOptions, QueryOptionItem, VariableMetadata

logger = logging.getLogger(__name__)


def build_query_options(
    dfwl: DataFrameWithWhitelists,
    school_name: Optional[str] = None,
) -> QueryOptions:
    """
    Build query options from datastore, optionally scoped to a specific school.

    Args:
        dfwl: DataFrame with whitelists
        school_name: Optional school name to scope the data to

    Returns:
        QueryOptions with variables, waves, aggregations, and filters
    """
    df = dfwl.df

    # Optionally scope to school
    if school_name:
        df = df[df["school"] == school_name]

    # Build variables list (all numeric measures including derived totals)
    variables = sorted([col for col in dfwl.numerical_whitelist if col in df.columns])

    # Get waves from data
    waves = []
    if "wave" in df.columns:
        waves = sorted(df["wave"].dropna().astype(str).unique().tolist())

    # Build aggregations with scope markers
    # "class" is focus_only, others are shared
    aggregation_items = []
    for dim in sorted(dfwl.categorical_whitelist):
        if dim in df.columns and dim not in ["school", "wave"]:
            scope = "focus_only" if dim == "class" else "shared"
            aggregation_items.append(
                QueryOptionItem(
                    value=dim,
                    scope=scope,
                )
            )

    # Build filters with scope markers and possible values
    filter_items = []
    for dim in sorted(dfwl.categorical_whitelist):
        if dim in df.columns and dim not in ["school"]:
            # Get unique values for this dimension (limit to 50 to avoid huge lists)
            values = sorted(df[dim].dropna().astype(str).unique().tolist())[:50]
            scope = "focus_only" if dim == "class" else "shared"
            filter_items.append(
                QueryOptionItem(
                    value=dim,
                    values=values,
                    scope=scope,
                )
            )
    
    # Build metadata dict from dfwl.metadata
    # Convert to VariableMetadata objects
    metadata_dict: Dict[str, VariableMetadata] = {}
    for var_name, var_meta in dfwl.metadata.items():
        # Only include metadata for variables that are in our variables list
        if var_name in variables:
            metadata_dict[var_name] = VariableMetadata(
                min=var_meta.get("min"),
                max=var_meta.get("max"),
            )
    
    # Also compute metadata for derived totals (sum of constituent items)
    for var in variables:
        if var.endswith("_total") and var not in metadata_dict:
            # Extract constituent items (e.g., bw_wbeing_total -> bw_wbeing_1, bw_wbeing_2, etc.)
            # Parse the variable name to get the prefix (e.g., bw_wbeing)
            parts = var.split("_")
            if len(parts) >= 3 and parts[-1] == "total":
                prefix = "_".join(parts[:-1])  # e.g., "bw_wbeing"
                
                # Find all constituent items
                constituent_items = [v for v in dfwl.metadata.keys() if v.startswith(prefix + "_") and not v.endswith("_total")]
                
                # Sum min/max values
                if constituent_items:
                    total_min = sum(dfwl.metadata.get(item, {}).get("min", 0) or 0 for item in constituent_items)
                    total_max = sum(dfwl.metadata.get(item, {}).get("max", 0) or 0 for item in constituent_items)
                    
                    # Only set if we have at least one min or max
                    if total_min > 0 or total_max > 0:
                        metadata_dict[var] = VariableMetadata(
                            min=total_min if total_min > 0 else None,
                            max=total_max if total_max > 0 else None,
                        )

    return QueryOptions(
        variables=variables,
        waves=waves,
        aggregations=aggregation_items,
        filters=filter_items,
        metadata=metadata_dict,
    )


def validate_query_request(
    variable: str,
    waves: list[str],
    aggregations: list[str],
    filters: dict[str, list],
    query_options: QueryOptions,
    include_neighbors: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Validate a query request against query options.

    Args:
        variable: Variable to query
        waves: Waves to query
        aggregations: Aggregations to apply
        filters: Filters to apply
        query_options: Query options to validate against
        include_neighbors: Whether neighbors are included

    Returns:
        Tuple of (valid, error_message)
    """
    # Validate variable
    if variable not in query_options.variables:
        return (
            False,
            f"Variable '{variable}' is not allowed. Allowed: {query_options.variables}",
        )

    # Validate waves
    for wave in waves:
        if wave not in query_options.waves:
            return (
                False,
                f"Wave '{wave}' is not allowed. Allowed: {query_options.waves}",
            )

    # Validate aggregations
    allowed_aggs = {item.value: item.scope for item in query_options.aggregations}
    for agg in aggregations:
        if agg not in allowed_aggs:
            return (
                False,
                f"Aggregation '{agg}' is not allowed. Allowed: {list(allowed_aggs.keys())}",
            )

        # Check scope: focus_only aggregations not allowed with neighbors
        if allowed_aggs[agg] == "focus_only" and include_neighbors:
            return (
                False,
                f"Aggregation '{agg}' is only allowed for focus school (not with neighbors)",
            )

    # Validate filters
    allowed_filters = {item.value: item.scope for item in query_options.filters}
    for filter_col in filters.keys():
        if filter_col not in allowed_filters:
            return (
                False,
                f"Filter '{filter_col}' is not allowed. Allowed: {list(allowed_filters.keys())}",
            )

        # Check scope: focus_only filters not allowed with neighbors
        if allowed_filters[filter_col] == "focus_only" and include_neighbors:
            return (
                False,
                f"Filter '{filter_col}' is only allowed for focus school (not with neighbors)",
            )

    return True, None
