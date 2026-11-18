"""Detection thresholds with Exception-Detection-Spec §2 defaults.

ownership_gap is always immediate and has no field: the register does not
record when an owner was removed, so there is no elapsed time to compare.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from .types import WorkItem


@dataclass(frozen=True)
class Thresholds:
    progress_gap: timedelta = timedelta(minutes=10)
    progress_gap_human: timedelta = timedelta(hours=1)
    verification_delay: timedelta = timedelta(minutes=5)
    long_term_block: timedelta = timedelta(minutes=30)
    long_term_block_human: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        for name in (
            "progress_gap",
            "progress_gap_human",
            "verification_delay",
            "long_term_block",
            "long_term_block_human",
        ):
            if getattr(self, name) < timedelta(0):
                raise ValueError(f"threshold {name} must be non-negative")

    def progress_gap_for(self, item: WorkItem) -> timedelta:
        return self.progress_gap_human if item.human_dependent else self.progress_gap

    def long_term_block_for(self, item: WorkItem) -> timedelta:
        return self.long_term_block_human if item.human_dependent else self.long_term_block


def thresholds_for(
    project_id: str,
    default: Thresholds,
    overrides: Mapping[str, Thresholds] | None,
) -> Thresholds:
    if overrides and project_id in overrides:
        return overrides[project_id]
    return default
