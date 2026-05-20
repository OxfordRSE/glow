"""Contract examples registry for API validation and OpenAPI documentation.

This module provides utilities to load contract examples from JSON files
and attach them to Pydantic models for OpenAPI schema generation.
"""

import json
from pathlib import Path
from typing import Any, Iterator

# Path to contract examples directory
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples" / "contracts"


def iter_contract_examples() -> Iterator[tuple[str, dict[str, Any]]]:
    """Iterate over all contract example files.
    
    Yields:
        Tuples of (example_id, example_dict) for each JSON file.
    """
    if not EXAMPLES_DIR.exists():
        return
    
    for json_file in sorted(EXAMPLES_DIR.glob("*.json")):
        with open(json_file) as f:
            example = json.load(f)
            yield example["id"], example


def examples_for_model(model_name: str) -> list[dict[str, Any]]:
    """Get all response examples for a given Pydantic model.
    
    Args:
        model_name: The name of the Pydantic model (e.g., "QueryResponse")
        
    Returns:
        List of example response bodies that match the given model.
    """
    examples = []
    for example_id, example in iter_contract_examples():
        if example.get("response_model") == model_name:
            examples.append(example["response"])
    return examples


def get_example(example_id: str) -> dict[str, Any] | None:
    """Get a specific contract example by ID.
    
    Args:
        example_id: The example identifier (e.g., "query.default")
        
    Returns:
        The full example dict or None if not found.
    """
    for eid, example in iter_contract_examples():
        if eid == example_id:
            return example
    return None


def get_openapi_examples(model_name: str) -> dict[str, Any] | None:
    """Get OpenAPI examples configuration for a model.
    
    Args:
        model_name: The name of the Pydantic model
        
    Returns:
        OpenAPI examples dict or None if no examples found.
    """
    examples = examples_for_model(model_name)
    if not examples:
        return None
    
    # For schema-level examples, just use the first example
    # (Route-level named examples would go in the router decorator)
    return {"examples": examples}
