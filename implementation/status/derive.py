"""Derived status (Derived-Status-Spec, ADR-003).

Status is computed on every call from a snapshot, the exception ledger and an
evaluation time. Nothing is stored. Rules are first-match-wins in the order
COMPLETE, RED, AMBER, GREEN.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exceptions import (
    ExceptionRecord,
    ExceptionType,
    Snapshot,
    WorkItem,
    WorkState,
)

_RED_TYPES = frozenset({
    ExceptionType.VERIFICATION_FAILURE,
    ExceptionType.OWNERSHIP_GAP,
    ExceptionType.LONG_TERM_BLOCK,
})
_DONE_STATES = frozenset({WorkState.COMPLETE, WorkState.ARCHIVED})


class Status(StrEnum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    COMPLETE = "COMPLETE"


_SEVERITY = {Status.GREEN: 0, Status.AMBER: 1, Status.RED: 2}


@dataclass(frozen=True)
class ProjectStatus:
    project_id: str
    status: Status
    reasons: tuple[str, ...]
    exception_ids: tuple[str, ...]
    work_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProgrammeStatus:
    status: Status
    projects: tuple[ProjectStatus, ...]


def derive_project_status(
    snapshot: Snapshot,
    exceptions: Sequence[ExceptionRecord],
    project_id: str,
    as_of: datetime,
) -> ProjectStatus:
    """Status of one project at `as_of`. Empty projects are GREEN (assumption)."""
    items = tuple(sorted((i for i in snapshot.items if i.project_id == project_id),
                         key=lambda i: i.work_id))
    open_exc = tuple(sorted(
        (e for e in exceptions if e.project_id == project_id and _is_open(e, as_of)),
        key=lambda e: e.exception_id,
    ))

    if _is_complete(items):
        return ProjectStatus(project_id, Status.COMPLETE, ("all required work is complete",),
                             (), tuple(i.work_id for i in items if i.required))

    red = tuple(e for e in open_exc if e.type in _RED_TYPES)
    if red:
        return _result(project_id, Status.RED, red, items)

    blocked = tuple(i for i in items if i.state is WorkState.BLOCKED)
    if open_exc or blocked:
        return _result(project_id, Status.AMBER, open_exc, items, blocked)

    return ProjectStatus(project_id, Status.GREEN, ("no open exceptions or blocked work",), (), ())


def derive_programme_status(
    snapshot: Snapshot,
    exceptions: Sequence[ExceptionRecord],
    as_of: datetime,
) -> ProgrammeStatus:
    """Worst-of roll-up (RED > AMBER > GREEN). COMPLETE only if every project is COMPLETE."""
    project_ids = sorted({i.project_id for i in snapshot.items}
                         | {e.project_id for e in exceptions})
    projects = tuple(derive_project_status(snapshot, exceptions, pid, as_of)
                     for pid in project_ids)

    if not projects:
        return ProgrammeStatus(Status.GREEN, ())
    if all(p.status is Status.COMPLETE for p in projects):
        return ProgrammeStatus(Status.COMPLETE, projects)

    worst = max((p.status for p in projects if p.status is not Status.COMPLETE),
                key=_SEVERITY.__getitem__)
    return ProgrammeStatus(worst, projects)


def _is_open(e: ExceptionRecord, as_of: datetime) -> bool:
    return e.detected_ts <= as_of and (e.resolved_ts is None or e.resolved_ts > as_of)


def _is_complete(items: tuple[WorkItem, ...]) -> bool:
    required = [i for i in items if i.required]
    return bool(required) and all(i.state in _DONE_STATES for i in required)


def _result(
    project_id: str,
    status: Status,
    exc: tuple[ExceptionRecord, ...],
    items: tuple[WorkItem, ...],
    blocked: tuple[WorkItem, ...] = (),
) -> ProjectStatus:
    reasons = [f"{e.exception_id}: {e.type.value} ({e.detail})" for e in exc]
    reasons += [f"{i.work_id}: Blocked without open LONG_TERM_BLOCK"
                for i in blocked if not any(e.work_id == i.work_id for e in exc)]
    work_ids = sorted({e.work_id for e in exc} | {i.work_id for i in blocked})
    return ProjectStatus(project_id, status, tuple(reasons),
                         tuple(e.exception_id for e in exc), tuple(work_ids))
