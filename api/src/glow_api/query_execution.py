"""Period-oriented query execution engine.

This module replaces the old wave-first, neighbor-oriented query engine
with a period-oriented multi-variable query engine.
"""

import hashlib
import logging
from typing import Optional

import pandas as pd

from glow_api.canonical_query import CanonicalQuery, canonical_query_to_etag_key
from glow_api.normalization import get_observed_periods

logger = logging.getLogger(__name__)


def compute_query_etag(
    query: CanonicalQuery,
    dataset_version: str,
    api_version: str,
) -> str:
    """Compute ETag for a query response.
    
    Args:
        query: Canonical query
        dataset_version: Dataset version marker (ODK ETag or timestamp)
        api_version: API version
    
    Returns:
        ETag string (quoted hexdigest)
    
    Rules:
        - ETag incorporates canonical query, dataset version, and API version
        - Same inputs always produce same ETag (deterministic)
        - Different queries or versions produce different ETags
    """
    # Build ETag seed from all components
    query_key = canonical_query_to_etag_key(query)
    etag_seed = f"{query_key}||{dataset_version}||{api_version}"
    
    # Hash to produce deterministic ETag
    etag_hash = hashlib.sha256(etag_seed.encode()).hexdigest()[:16]
    
    # Return quoted ETag per HTTP spec
    return f'"{etag_hash}"'


def deduplicate_submissions(
    df: pd.DataFrame,
    variable: str,
) -> pd.DataFrame:
    """Deduplicate submissions using latest-non-null rule.
    
    Args:
        df: DataFrame with submissions (must have uid, period_id, createdAt, and variable)
        variable: Variable name to deduplicate on
    
    Returns:
        Deduped DataFrame with one row per uid per period
    
    Rules:
        - For each uid in each period, keep only the latest non-null value
        - If all values are null for a uid in a period, keep the latest submission anyway
        - Deduplication happens independently per period
    """
    if df.empty:
        return df
    
    # Make sure we have required columns
    required_cols = ["uid", "period_id", "createdAt", variable]
    for col in required_cols:
        if col not in df.columns:
            logger.warning(f"Missing column {col} for deduplication")
            return df
    
    # Parse createdAt if it's a string
    df = df.copy()
    if df["createdAt"].dtype == object:
        df["createdAt"] = pd.to_datetime(df["createdAt"])
    
    # Sort by createdAt descending (latest first)
    df = df.sort_values("createdAt", ascending=False)
    
    # For each uid-period group, keep the first non-null value
    # or if all are null, keep the first (latest) row
    deduped_rows = []
    
    for (uid, period_id), group in df.groupby(["uid", "period_id"], sort=False):
        # Try to find first non-null value
        non_null = group[group[variable].notna()]
        
        if not non_null.empty:
            # Keep first non-null (which is latest due to sorting)
            deduped_rows.append(non_null.iloc[0])
        else:
            # All null - keep latest submission
            deduped_rows.append(group.iloc[0])
    
    if not deduped_rows:
        return pd.DataFrame(columns=df.columns)
    
    return pd.DataFrame(deduped_rows).reset_index(drop=True)


def execute_query(
    df: pd.DataFrame,
    query: CanonicalQuery,
    numerical_whitelist: Optional[list[str]] = None,
    min_n: int = 5,
    form_metadata: Optional[dict] = None,
) -> dict:
    """Execute a period-oriented multi-variable query.
    
    Args:
        df: Normalized DataFrame with period_id column
        query: Canonical query with variables, dimensions, and prefixes
        numerical_whitelist: List of valid numerical variable names
        min_n: Minimum N for suppression
        form_metadata: Optional form metadata for version compatibility
    
    Returns:
        Query response dict matching NewQueryResponse model
    
    Rules:
        - Variables are selected by exact match (v) or prefix (variable_prefix)
        - If both are omitted, all numerical variables are selected
        - Results are organized by period within each variable
        - Periods with no data for a variable are omitted from that variable's results
        - Suppression is evaluated independently per period
    """
    # Determine which variables to query
    selected_variables = _select_variables(df, query, numerical_whitelist)
    
    # Get observed periods
    if "school" in df.columns and query.school_id is not None:
        # School-scoped query - need to map school_id to school name
        # For now, assume df is already filtered to the school
        observed_periods = get_observed_periods(df)
    else:
        # Dataset-scoped query
        observed_periods = get_observed_periods(df)
    
    # Execute query for each variable
    variable_slices = []
    for variable in selected_variables:
        var_slice = _execute_variable_query(
            df=df,
            variable=variable,
            dimensions=query.dimensions,
            observed_periods=observed_periods,
            min_n=min_n,
            form_metadata=form_metadata,
        )
        variable_slices.append(var_slice)
    
    # Build response
    return {
        "query": query.model_dump(),
        "dimensions": query.dimensions,
        "periods": observed_periods,
        "variables": variable_slices,
    }


def _select_variables(
    df: pd.DataFrame,
    query: CanonicalQuery,
    numerical_whitelist: Optional[list[str]] = None,
) -> list[str]:
    """Select variables based on query parameters.
    
    Args:
        df: DataFrame with data
        query: Canonical query
        numerical_whitelist: List of valid numerical variables
    
    Returns:
        Sorted list of selected variable names
    
    Rules:
        - If both 'variables' and 'variable_prefixes' are empty, select all numerical variables
        - If 'variables' is specified, include those exact variables
        - If 'variable_prefixes' is specified, expand to matching variables
        - Union of both lists if both are specified
    """
    if numerical_whitelist is None:
        # Infer numerical columns from DataFrame
        numerical_whitelist = df.select_dtypes(include=['number']).columns.tolist()
        # Remove non-variable columns
        numerical_whitelist = [
            col for col in numerical_whitelist
            if col not in ['uid', 'wave', 'period_id', 'school_id']
        ]
    
    # If no variables or prefixes specified, return all numerical variables
    if not query.variables and not query.variable_prefixes:
        return sorted(numerical_whitelist)
    
    # Start with empty set
    selected = set()
    
    # Add exact variable matches
    for var in query.variables:
        if var in numerical_whitelist:
            selected.add(var)
    
    # Add prefix-matched variables
    for prefix in query.variable_prefixes:
        for var in numerical_whitelist:
            if var.startswith(prefix):
                selected.add(var)
    
    return sorted(list(selected))


def _execute_variable_query(
    df: pd.DataFrame,
    variable: str,
    dimensions: list[str],
    observed_periods: list[str],
    min_n: int,
    form_metadata: Optional[dict] = None,
) -> dict:
    """Execute query for a single variable across all periods.
    
    Args:
        df: Normalized DataFrame
        variable: Variable name to query
        dimensions: List of dimension columns to group by
        observed_periods: List of observed period IDs
        min_n: Minimum N for suppression
        form_metadata: Optional metadata for version compatibility checking
    
    Returns:
        Variable slice dict with periods
    """
    # Deduplicate submissions for this variable first
    df_deduped = deduplicate_submissions(df, variable)
    
    # Build period results
    period_results = {}
    
    for period_id in observed_periods:
        # Filter to this period
        period_df = df_deduped[df_deduped["period_id"] == period_id]
        
        # Check if variable exists and has data in this period
        if variable not in period_df.columns:
            # Variable not collected in this period - omit from results
            continue
        
        # Drop rows where variable is null
        period_df = period_df[period_df[variable].notna()]
        
        if period_df.empty:
            # No data for this variable in this period - omit
            continue
        
        # Check version compatibility if we have version metadata
        notes = []
        if form_metadata and "__version" in period_df.columns:
            # Check if multiple versions exist in this period
            versions = period_df["__version"].dropna().unique()
            
            if len(versions) > 1:
                # Multiple versions - check compatibility
                from glow_api.version_compatibility import check_version_compatibility, apply_rescaling
                
                # For simplicity, check compatibility between all pairs
                # In real implementation, might want to check against a reference version
                incompatible = False
                rescale_needed = False
                
                for i, v1 in enumerate(versions):
                    for v2 in versions[i+1:]:
                        # Get metadata for each version (simplified - would need actual version lookup)
                        v1_meta = form_metadata.get(str(v1), form_metadata)
                        v2_meta = form_metadata.get(str(v2), form_metadata)
                        
                        compat = check_version_compatibility(variable, v1_meta, v2_meta)
                        
                        if not compat["compatible"]:
                            incompatible = True
                            break
                        
                        if compat["rescale_needed"]:
                            rescale_needed = True
                    
                    if incompatible:
                        break
                
                if incompatible:
                    # Suppress this period due to incompatible versions
                    period_results[period_id] = {
                        "suppressed": True,
                        "suppression_reason": "incompatible-version",
                        "cells": None,
                    }
                    continue
                
                if rescale_needed:
                    notes.append("values-rescaled")
        
        # Compute aggregated results for this period
        period_slice = _compute_period_slice(
            period_df=period_df,
            variable=variable,
            dimensions=dimensions,
            min_n=min_n,
        )
        
        # Add notes if any
        if notes:
            period_slice["notes"] = notes
        
        period_results[period_id] = period_slice
    
    return {
        "variable": variable,
        "periods": period_results,
    }


def _compute_period_slice(
    period_df: pd.DataFrame,
    variable: str,
    dimensions: list[str],
    min_n: int,
) -> dict:
    """Compute aggregated results for a single variable in a single period.
    
    Args:
        period_df: DataFrame filtered to one period
        variable: Variable name
        dimensions: Dimensions to group by
        min_n: Minimum N for suppression
    
    Returns:
        Period slice dict with cells or suppression info
    """
    # If no dimensions, compute overall mean
    if not dimensions:
        n = len(period_df)
        if n < min_n:
            return {
                "suppressed": True,
                "suppression_reason": "small-n",
                "cells": None,
            }
        
        mean_value = period_df[variable].mean()
        return {
            "suppressed": False,
            "cells": [{"mean": float(mean_value), "n": n}],
        }
    
    # Group by dimensions
    # Filter to only include valid dimensions that exist in the DataFrame
    valid_dimensions = [d for d in dimensions if d in period_df.columns]
    
    if not valid_dimensions:
        # No valid dimensions - fall back to overall mean
        n = len(period_df)
        if n < min_n:
            return {
                "suppressed": True,
                "suppression_reason": "small-n",
                "cells": None,
            }
        
        mean_value = period_df[variable].mean()
        return {
            "suppressed": False,
            "cells": [{"mean": float(mean_value), "n": n}],
        }
    
    # Group and aggregate
    grouped = period_df.groupby(valid_dimensions, dropna=False)
    
    # Compute mean and count for each group
    cells = []
    for group_coords, group_df in grouped:
        n = len(group_df)
        mean_value = group_df[variable].mean()
        
        # Build cell with coordinates
        cell = {"mean": float(mean_value), "n": n}
        
        # Add dimension coordinates
        if len(valid_dimensions) == 1:
            group_coords = (group_coords,)
        
        for i, dim in enumerate(valid_dimensions):
            cell[dim] = group_coords[i]
        
        cells.append(cell)
    
    # Check for blanket suppression
    min_cell_n = min(cell["n"] for cell in cells) if cells else 0
    if min_cell_n < min_n:
        return {
            "suppressed": True,
            "suppression_reason": "small-n",
            "cells": None,
        }
    
    return {
        "suppressed": False,
        "cells": cells,
    }
