"""Form version compatibility checking and value rescaling.

This module handles comparison of form versions to determine if values
can be safely compared, and provides rescaling when needed.
"""

import logging
from typing import Dict, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def check_version_compatibility(
    variable: str,
    v1_metadata: Dict[str, Dict[str, int]],
    v2_metadata: Dict[str, Dict[str, int]],
) -> Dict:
    """Check if a variable is compatible across two form versions.
    
    Args:
        variable: Variable name to check
        v1_metadata: Metadata from first form version
        v2_metadata: Metadata from second form version
    
    Returns:
        Dict with keys:
            - compatible: bool - Whether versions can be compared
            - rescale_needed: bool - Whether rescaling is needed
            - rescale_from: Optional[Tuple[int, int]] - Old (min, max)
            - rescale_to: Optional[Tuple[int, int]] - New (min, max)
            - reason: Optional[str] - Reason if incompatible
    
    Rules:
        - If limits are identical, compatible without rescaling
        - If limits differ but can be linearly mapped, compatible with rescaling
        - If variable removed in new version, incompatible
        - For safety, we're permissive - most scale changes are rescalable
    """
    # Check if variable exists in both versions
    if variable not in v1_metadata:
        return {
            "compatible": False,
            "rescale_needed": False,
            "reason": "variable-not-in-old-version",
        }
    
    if variable not in v2_metadata:
        return {
            "compatible": False,
            "rescale_needed": False,
            "reason": "variable-not-in-new-version",
        }
    
    v1_min = v1_metadata[variable]["min"]
    v1_max = v1_metadata[variable]["max"]
    v2_min = v2_metadata[variable]["min"]
    v2_max = v2_metadata[variable]["max"]
    
    # If limits are identical, no rescaling needed
    if v1_min == v2_min and v1_max == v2_max:
        return {
            "compatible": True,
            "rescale_needed": False,
        }
    
    # Limits differ - rescaling needed
    # We're permissive here - any linear transformation is allowed
    return {
        "compatible": True,
        "rescale_needed": True,
        "rescale_from": (v1_min, v1_max),
        "rescale_to": (v2_min, v2_max),
    }


def rescale_value(
    value: float,
    from_range: Tuple[int, int],
    to_range: Tuple[int, int],
) -> float:
    """Linearly rescale a value from one range to another.
    
    Args:
        value: Value to rescale
        from_range: Original (min, max)
        to_range: Target (min, max)
    
    Returns:
        Rescaled value
    
    Formula:
        new_value = (value - old_min) / (old_max - old_min) * (new_max - new_min) + new_min
    """
    old_min, old_max = from_range
    new_min, new_max = to_range
    
    # Handle edge case where old range has no width
    if old_max == old_min:
        return new_min
    
    # Linear interpolation
    normalized = (value - old_min) / (old_max - old_min)
    rescaled = normalized * (new_max - new_min) + new_min
    
    return rescaled


def apply_rescaling(
    df: pd.DataFrame,
    variable: str,
    from_range: Tuple[int, int],
    to_range: Tuple[int, int],
) -> pd.DataFrame:
    """Apply rescaling to all values of a variable in a DataFrame.
    
    Args:
        df: DataFrame with variable values
        variable: Variable name to rescale
        from_range: Original (min, max)
        to_range: Target (min, max)
    
    Returns:
        DataFrame with rescaled values
    """
    df = df.copy()
    
    # Apply rescaling to non-null values
    mask = df[variable].notna()
    df.loc[mask, variable] = df.loc[mask, variable].apply(
        lambda x: rescale_value(x, from_range, to_range)
    )
    
    return df
