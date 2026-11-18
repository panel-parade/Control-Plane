"""Idempotent reconciliation of exception records against detections.

reconcile() is a pure function: it returns the new ledger and never mutates
work items. Records are resolved, never deleted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from .detect import _require_aware
from .types import (
    Detection,
    ExceptionRecord,
    ExceptionStatus,
    Responder,
)

_RESPONDER_RANK = {Responder.MANAGER: 0, Responder.INTENT_OWNER: 1}


def reconcile(
    existing: Sequence[ExceptionRecord],
    detections: Sequence[Detection],
    now: datetime,
) -> tuple[ExceptionRecord, ...]:
    """Return the ledger after applying current detections.

    - At most one open record per (work_id, type). Re-detection keeps it.
    - Open records whose condition has cleared are resolved with resolved_ts.
    - New records get exception_id "<work_id>-<type>-<n>", where n counts all
      prior records for that key, so ids stay unique across reopenings.
    - Responder only escalates (Manager -> IntentOwner), never downgrades.
    """
    _require_aware(now)

    open_by_key: dict[tuple[str, str], ExceptionRecord] = {}
    count_by_key: Counter[tuple[str, str]] = Counter()
    for rec in existing:
        key = (rec.work_id, rec.type.value)
        count_by_key[key] += 1
        if rec.status is ExceptionStatus.OPEN:
            if key in open_by_key:
                raise ValueError(f"duplicate open exception for {key}")
            open_by_key[key] = rec

    detected: dict[tuple[str, str], Detection] = {}
    for d in detections:
        key = (d.work_id, d.type.value)
        if key in detected:
            raise ValueError(f"duplicate detection for {key}")
        detected[key] = d

    ledger: list[ExceptionRecord] = [r for r in existing if r.status is ExceptionStatus.RESOLVED]

    for key, rec in open_by_key.items():
        if key in detected:
            d = detected[key]
            ledger.append(replace(
                rec,
                detail=d.detail,
                responder=_escalate(rec.responder, d.responder),
            ))
        else:
            ledger.append(replace(rec, status=ExceptionStatus.RESOLVED, resolved_ts=now))

    for key, d in detected.items():
        if key in open_by_key:
            continue
        ledger.append(ExceptionRecord(
            exception_id=f"{d.work_id}-{d.type.value}-{count_by_key[key] + 1}",
            work_id=d.work_id,
            project_id=d.project_id,
            type=d.type,
            detected_ts=now,
            responder=d.responder,
            status=ExceptionStatus.OPEN,
            detail=d.detail,
        ))

    return tuple(sorted(ledger, key=lambda r: r.exception_id))


def _escalate(current: Responder, proposed: Responder) -> Responder:
    return current if _RESPONDER_RANK[current] >= _RESPONDER_RANK[proposed] else proposed
