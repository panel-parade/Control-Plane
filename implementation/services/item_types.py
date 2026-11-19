"""Explicit work item type (Control Plane #32). Allowed values only; no inference from text."""

from typing import Optional

ITEM_TYPES = ("Decision", "Validation", "Execution", "Observation", "Exception")

TYPE_MISSING = "TYPE_MISSING"
TYPE_INVALID = "TYPE_INVALID"

# Labels that name no type. They are treated as a missing type, not as an invalid one.
NON_TYPE_LABELS = frozenset({"plain text"})


def validate_item_type(item_type: Optional[str]) -> None:
    """Raise ValueError prefixed with TYPE_MISSING or TYPE_INVALID unless item_type is allowed."""
    if item_type is None or not item_type.strip() or item_type.strip().lower() in NON_TYPE_LABELS:
        raise ValueError(f"{TYPE_MISSING}: item_type must be one of {ITEM_TYPES}")
    if item_type not in ITEM_TYPES:
        raise ValueError(f"{TYPE_INVALID}: {item_type!r} is not one of {ITEM_TYPES}")
