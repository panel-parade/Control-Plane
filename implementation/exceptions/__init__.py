"""Exception detection (Exception-Detection-Spec). Pure functions over read-only snapshots."""

from .detect import detect
from .ledger import reconcile
from .thresholds import Thresholds, thresholds_for
from .types import (
    AuditEntry,
    Detection,
    ExceptionRecord,
    ExceptionStatus,
    ExceptionType,
    Responder,
    Snapshot,
    VerificationOutcome,
    VerificationSignal,
    WorkItem,
    WorkState,
)

__all__ = [
    "AuditEntry",
    "Detection",
    "ExceptionRecord",
    "ExceptionStatus",
    "ExceptionType",
    "Responder",
    "Snapshot",
    "Thresholds",
    "VerificationOutcome",
    "VerificationSignal",
    "WorkItem",
    "WorkState",
    "detect",
    "reconcile",
    "thresholds_for",
]
