"""Pure, read-only exception detection.

Conditions are evaluated against a snapshot at a given evaluation time. A
threshold is breached only when elapsed time is strictly greater than the
threshold ("beyond threshold").
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from .thresholds import Thresholds, thresholds_for
from .types import (
    Detection,
    ExceptionType,
    Responder,
    Snapshot,
    VerificationOutcome,
    VerificationSignal,
    WorkItem,
    WorkState,
)

_CLOSED_STATES = frozenset({WorkState.ARCHIVED})
_TERMINAL_STATES = frozenset({WorkState.COMPLETE, WorkState.ARCHIVED})


def detect(
    snapshot: Snapshot,
    now: datetime,
    thresholds: Thresholds | None = None,
    overrides: Mapping[str, Thresholds] | None = None,
) -> tuple[Detection, ...]:
    """Return the exception conditions that hold at `now`, sorted by (work_id, type)."""
    _require_aware(now)
    default = thresholds or Thresholds()
    entered = _entered_index(snapshot)
    signals = _signals_by_work(snapshot.verifications)

    found: list[Detection] = []
    blocked_beyond: set[str] = set()
    thresholds_by_project: dict[str, Thresholds] = {}

    for item in sorted(snapshot.items, key=lambda i: i.work_id):
        t = thresholds_by_project.setdefault(
            item.project_id, thresholds_for(item.project_id, default, overrides)
        )

        if item.assigned_to is None and item.state not in _CLOSED_STATES:
            found.append(_detection(item, ExceptionType.OWNERSHIP_GAP, Responder.MANAGER,
                                    "assigned_to is null"))

        if item.state in (WorkState.ASSIGNED, WorkState.ACTIVE):
            limit = t.progress_gap_for(item)
            age = now - item.last_update_ts
            if age > limit:
                found.append(_detection(
                    item, ExceptionType.PROGRESS_GAP, Responder.MANAGER,
                    f"no update for {_fmt(age)}, threshold {_fmt(limit)}"))

        if item.state is WorkState.BLOCKED:
            since = _entered_at(entered, item, WorkState.BLOCKED)
            limit = t.long_term_block_for(item)
            if now - since > limit:
                blocked_beyond.add(item.work_id)
                found.append(_detection(
                    item, ExceptionType.LONG_TERM_BLOCK, Responder.MANAGER,
                    f"blocked since {since.isoformat()}, threshold {_fmt(limit)}"))

        if item.state is WorkState.CLAIMED_COMPLETE:
            since = _entered_at(entered, item, WorkState.CLAIMED_COMPLETE)
            reason = _verification_reason(
                signals.get(item.work_id, ()), since, now, t.verification_delay)
            if reason:
                found.append(_detection(item, ExceptionType.VERIFICATION_FAILURE,
                                        Responder.MANAGER, reason))

    found = _escalate_long_term_blocks(found, snapshot.items, blocked_beyond, default, overrides)
    return tuple(sorted(found, key=lambda d: (d.work_id, d.type.value)))


def _escalate_long_term_blocks(
    found: list[Detection],
    items: tuple[WorkItem, ...],
    blocked_beyond: set[str],
    default: Thresholds,
    overrides: Mapping[str, Thresholds] | None,
) -> list[Detection]:
    """Escalate LONG_TERM_BLOCK to IntentOwner when the whole project is blocked.

    Assumption: a project is "blocked beyond threshold" when it has open work
    (not Complete or Archived) and every open item is a long-term block.
    """
    open_by_project: dict[str, list[WorkItem]] = {}
    for item in items:
        if item.state not in _TERMINAL_STATES:
            open_by_project.setdefault(item.project_id, []).append(item)

    project_blocked = {
        pid: bool(work) and all(i.work_id in blocked_beyond for i in work)
        for pid, work in open_by_project.items()
    }

    result = []
    for d in found:
        if d.type is ExceptionType.LONG_TERM_BLOCK and project_blocked.get(d.project_id):
            d = Detection(d.work_id, d.project_id, d.type, Responder.INTENT_OWNER, d.detail)
        result.append(d)
    return result


def _verification_reason(
    signals: tuple[VerificationSignal, ...],
    since: datetime,
    now: datetime,
    delay: timedelta,
) -> str | None:
    """A VERIFICATION_FAILURE for an item in Claimed Complete, or None.

    Only signals checked on or after the item entered Claimed Complete count.
    """
    current = [s for s in signals if s.checked_ts >= since]
    failures = [s for s in current if s.outcome is VerificationOutcome.FAIL]
    if failures:
        latest = max(failures, key=lambda s: s.checked_ts)
        checks = ", ".join(latest.failing_checks) or "unspecified"
        return f"failing checks: {checks}"
    if any(s.outcome is VerificationOutcome.PASS for s in current):
        return None
    if now - since > delay:
        return f"not verified within verification_delay {_fmt(delay)}"
    return None


def _entered_index(snapshot: Snapshot) -> dict[tuple[str, WorkState], datetime]:
    """Latest audit timestamp at which each (work_id, state) was entered."""
    index: dict[tuple[str, WorkState], datetime] = {}
    for entry in snapshot.audit:
        key = (entry.work_id, entry.new_state)
        if key not in index or entry.timestamp > index[key]:
            index[key] = entry.timestamp
    return index


def _entered_at(
    entered: dict[tuple[str, WorkState], datetime],
    item: WorkItem,
    state: WorkState,
) -> datetime:
    """Entry time for `state`, falling back to last_update_ts without an audit entry."""
    return entered.get((item.work_id, state), item.last_update_ts)


def _signals_by_work(
    signals: tuple[VerificationSignal, ...],
) -> dict[str, tuple[VerificationSignal, ...]]:
    grouped: dict[str, list[VerificationSignal]] = {}
    for s in signals:
        grouped.setdefault(s.work_id, []).append(s)
    return {k: tuple(v) for k, v in grouped.items()}


def _detection(item: WorkItem, kind: ExceptionType, responder: Responder, detail: str) -> Detection:
    return Detection(item.work_id, item.project_id, kind, responder, detail)


def _fmt(td: timedelta) -> str:
    return f"{int(td.total_seconds())}s"


def _require_aware(ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("evaluation time must be timezone-aware UTC")
