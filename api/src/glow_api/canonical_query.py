"""Canonical query normalization utilities.

This module provides utilities to normalize query parameters into a canonical
form for deterministic behavior, response echoes, and ETag generation.
"""

from glow_api.models import CanonicalQuery


def normalize_query(
    school_id: int | None = None,
    v: list[str] | None = None,
    d: list[str] | None = None,
    variable_prefix: list[str] | None = None,
) -> CanonicalQuery:
    """Normalize query parameters into canonical form.

    Args:
        school_id: Optional school ID for school-scoped queries
        v: List of variable names (can be repeated in query params)
        d: List of dimension names (can be repeated in query params)
        variable_prefix: List of variable prefixes (can be repeated in query params)

    Returns:
        CanonicalQuery with sorted, deduped lists

    Rules:
        - All lists are sorted alphabetically and deduplicated
        - None/empty lists become empty lists in the canonical form
        - Omitted 'd' means no dimensions (empty list)
        - Omitted 'v' and 'variable_prefix' means all variables (handled at query execution)
    """
    # Normalize and dedupe variables
    variables = sorted(set(v or []))

    # Normalize and dedupe dimensions
    dimensions = sorted(set(d or []))

    # Normalize and dedupe variable prefixes
    prefixes = sorted(set(variable_prefix or []))

    return CanonicalQuery(
        school_id=school_id,
        variables=variables,
        dimensions=dimensions,
        variable_prefixes=prefixes,
    )


def canonical_query_to_etag_key(query: CanonicalQuery) -> str:
    """Convert a canonical query to a string key for ETag generation.

    Args:
        query: The normalized canonical query

    Returns:
        A deterministic string representation of the query
    """
    parts = []

    if query.school_id is not None:
        parts.append(f"school_id={query.school_id}")

    if query.variables:
        parts.append(f"v={','.join(query.variables)}")

    if query.dimensions:
        parts.append(f"d={','.join(query.dimensions)}")

    if query.variable_prefixes:
        parts.append(f"variable_prefix={','.join(query.variable_prefixes)}")

    return "&".join(parts) if parts else ""
