"""Read-only input and result types for exception detection.

Field names mirror specifications/Work-Register-Spec.md, State-Machine-Spec.md
and Exception-Detection-Spec.md. These are local mirrors; they do not import
the register or verification implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WorkState(StrEnum):
    ASSIGNED = "Assigned"
    ACTIVE = "Active"
    BLOCKED = "Blocked"
    CLAIMED_COMPLETE = "Claimed Complete"
    COMPLETE = "Complete"
    ARCHIVED = "Archived"


class ExceptionType(StrEnum):
    OWNERSHIP_GAP = "OWNERSHIP_GAP"
    PROGRESS_GAP = "PROGRESS_GAP"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    LONG_TERM_BLOCK = "LONG_TERM_BLOCK"


class Responder(StrEnum):
    MANAGER = "Manager"
    INTENT_OWNER = "IntentOwner"


class ExceptionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class VerificationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class WorkItem:
    work_id: str
    project_id: str
    assigned_to: str | None
    state: WorkState
    last_update_ts: datetime
    required: bool
    # Assumption: per-item flag, defaults to False (Exception-Detection-Spec §7.1).
    human_dependent: bool = False


@dataclass(frozen=True)
class AuditEntry:
    work_id: str
    old_state: WorkState | None
    new_state: WorkState
    timestamp: datetime


@dataclass(frozen=True)
class VerificationSignal:
    work_id: str
    outcome: VerificationOutcome
    failing_checks: tuple[str, ...]
    checked_ts: datetime


@dataclass(frozen=True)
class ExceptionRecord:
    exception_id: str
    work_id: str
    project_id: str
    type: ExceptionType
    detected_ts: datetime
    responder: Responder
    status: ExceptionStatus
    detail: str
    resolved_ts: datetime | None = None


@dataclass(frozen=True)
class Snapshot:
    items: tuple[WorkItem, ...]
    audit: tuple[AuditEntry, ...] = ()
    verifications: tuple[VerificationSignal, ...] = ()


@dataclass(frozen=True)
class Detection:
    work_id: str
    project_id: str
    type: ExceptionType
    responder: Responder
    detail: str
