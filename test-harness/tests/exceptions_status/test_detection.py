from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from exceptions import (
    AuditEntry,
    ExceptionRecord,
    ExceptionStatus,
    ExceptionType,
    Responder,
    Snapshot,
    Thresholds,
    VerificationOutcome,
    VerificationSignal,
    WorkItem,
    WorkState,
    detect,
    reconcile,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)


def item(work_id="W1", state=WorkState.ACTIVE, assigned="alice", last=T0,
         project="P1", required=True, human=False):
    return WorkItem(work_id, project, assigned, state, last, required, human)


def kinds(detections):
    return [(d.work_id, d.type) for d in detections]


def get(detections, work_id, kind):
    return next(d for d in detections if d.work_id == work_id and d.type is kind)


# Ownership gap

def test_ownership_gap_is_immediate_for_unassigned_open_work():
    d = detect(Snapshot((item(assigned=None),)), T0)
    assert kinds(d) == [("W1", ExceptionType.OWNERSHIP_GAP)]
    assert d[0].responder is Responder.MANAGER


def test_archived_unassigned_item_has_no_ownership_gap():
    assert detect(Snapshot((item(assigned=None, state=WorkState.ARCHIVED),)), T0) == ()


# Progress gap boundaries

@pytest.mark.parametrize("age,expected", [(10 * MIN, False), (10 * MIN + timedelta(seconds=1), True)])
def test_progress_gap_boundary_is_strictly_beyond_10m(age, expected):
    d = detect(Snapshot((item(last=T0 - age),)), T0)
    assert (ExceptionType.PROGRESS_GAP in {x.type for x in d}) is expected


def test_progress_gap_applies_to_assigned_and_active_only():
    old = T0 - timedelta(hours=5)
    for state in (WorkState.ASSIGNED, WorkState.ACTIVE):
        assert ExceptionType.PROGRESS_GAP in {x.type for x in detect(
            Snapshot((item(state=state, last=old),)), T0)}
    assert detect(Snapshot((item(state=WorkState.CLAIMED_COMPLETE, last=T0),)), T0) == ()


def test_human_dependent_progress_gap_uses_one_hour():
    snap = Snapshot((item(last=T0 - timedelta(minutes=30), human=True),))
    assert detect(snap, T0) == ()
    snap = Snapshot((item(last=T0 - timedelta(hours=1, seconds=1), human=True),))
    assert kinds(detect(snap, T0)) == [("W1", ExceptionType.PROGRESS_GAP)]


def test_per_project_threshold_override_applies():
    snap = Snapshot((item(last=T0 - timedelta(minutes=20), project="P9"),))
    overrides = {"P9": Thresholds(progress_gap=timedelta(minutes=30))}
    assert detect(snap, T0, overrides=overrides) == ()


# Long-term block

def blocked_audit(entered):
    return AuditEntry("W1", WorkState.ACTIVE, WorkState.BLOCKED, entered)


def test_long_term_block_boundary_is_30m_from_block_entry():
    snap = Snapshot((item(state=WorkState.BLOCKED, last=T0 - timedelta(hours=2)),),
                    (blocked_audit(T0 - timedelta(minutes=30)),))
    assert detect(snap, T0) == ()
    snap = Snapshot((item(state=WorkState.BLOCKED, last=T0),),
                    (blocked_audit(T0 - timedelta(minutes=30, seconds=1)),))
    assert kinds(detect(snap, T0)) == [("W1", ExceptionType.LONG_TERM_BLOCK)]


def test_long_term_block_uses_entry_time_not_last_update():
    snap = Snapshot((item(state=WorkState.BLOCKED, last=T0 - timedelta(hours=3)),),
                    (blocked_audit(T0 - timedelta(minutes=5)),))
    assert detect(snap, T0) == ()


def test_human_dependent_long_term_block_uses_24h():
    snap = Snapshot((item(state=WorkState.BLOCKED, human=True),),
                    (blocked_audit(T0 - timedelta(hours=23)),))
    assert detect(snap, T0) == ()
    snap = Snapshot((item(state=WorkState.BLOCKED, human=True),),
                    (blocked_audit(T0 - timedelta(hours=24, seconds=1)),))
    assert kinds(detect(snap, T0)) == [("W1", ExceptionType.LONG_TERM_BLOCK)]


def test_whole_blocked_project_escalates_to_intent_owner():
    items = (item("W1", WorkState.BLOCKED), item("W2", WorkState.BLOCKED))
    audit = (AuditEntry("W1", None, WorkState.BLOCKED, T0 - timedelta(hours=1)),
             AuditEntry("W2", None, WorkState.BLOCKED, T0 - timedelta(hours=1)))
    d = detect(Snapshot(items, audit), T0)
    assert {x.responder for x in d} == {Responder.INTENT_OWNER}


def test_partially_blocked_project_stays_with_manager():
    items = (item("W1", WorkState.BLOCKED), item("W2", WorkState.ACTIVE, last=T0))
    audit = (AuditEntry("W1", None, WorkState.BLOCKED, T0 - timedelta(hours=1)),)
    d = detect(Snapshot(items, audit), T0)
    assert get(d, "W1", ExceptionType.LONG_TERM_BLOCK).responder is Responder.MANAGER


# Verification failure

def claimed(entered=T0 - timedelta(minutes=10)):
    return ((item(state=WorkState.CLAIMED_COMPLETE),),
            (AuditEntry("W1", WorkState.ACTIVE, WorkState.CLAIMED_COMPLETE, entered),))


def signal(outcome, checked, checks=()):
    return VerificationSignal("W1", outcome, tuple(checks), checked)


def test_verification_failure_when_not_verified_within_5m():
    items, audit = claimed(T0 - timedelta(minutes=5, seconds=1))
    d = detect(Snapshot(items, audit), T0)
    assert kinds(d) == [("W1", ExceptionType.VERIFICATION_FAILURE)]


def test_no_verification_failure_within_delay():
    items, audit = claimed(T0 - timedelta(minutes=5))
    assert detect(Snapshot(items, audit), T0) == ()


def test_failed_verification_raises_immediately_with_failing_checks():
    items, audit = claimed(T0 - timedelta(minutes=1))
    snap = Snapshot(items, audit, (signal(VerificationOutcome.FAIL, T0, ["tests"]),))
    d = get(detect(snap, T0), "W1", ExceptionType.VERIFICATION_FAILURE)
    assert "tests" in d.detail


def test_passing_verification_suppresses_failure():
    items, audit = claimed(T0 - timedelta(hours=1))
    snap = Snapshot(items, audit, (signal(VerificationOutcome.PASS, T0),))
    assert detect(snap, T0) == ()


def test_signals_before_entering_claimed_complete_are_ignored():
    items, audit = claimed(T0 - timedelta(minutes=1))
    snap = Snapshot(items, audit, (signal(VerificationOutcome.PASS, T0 - timedelta(hours=1)),))
    assert detect(snap, T0) == ()  # old pass ignored; still inside the 5m delay window


# Idempotency, auto-resolve, reconciliation

def test_detect_is_deterministic_and_does_not_mutate_inputs():
    snap = Snapshot((item(assigned=None), item("W2", last=T0 - timedelta(hours=1))))
    before = snap.items
    assert detect(snap, T0) == detect(snap, T0)
    assert snap.items is before


def open_record(work_id="W1", kind=ExceptionType.OWNERSHIP_GAP, n=1):
    return ExceptionRecord(f"{work_id}-{kind.value}-{n}", work_id, "P1", kind, T0,
                           Responder.MANAGER, ExceptionStatus.OPEN, "old")


def test_reconcile_keeps_one_open_record_per_work_and_type():
    snap = Snapshot((item(assigned=None),))
    once = reconcile((), detect(snap, T0), T0)
    twice = reconcile(once, detect(snap, T0 + MIN), T0 + MIN)
    assert len(twice) == 1
    assert twice[0].status is ExceptionStatus.OPEN
    assert twice[0].detected_ts == T0


def test_reconcile_rejects_duplicate_open_records():
    with pytest.raises(ValueError):
        reconcile((open_record(n=1), open_record(n=2)), (), T0)


def test_auto_resolve_records_resolved_ts_instead_of_deleting():
    later = T0 + MIN
    out = reconcile((open_record(),), (), later)
    assert len(out) == 1
    assert out[0].status is ExceptionStatus.RESOLVED
    assert out[0].resolved_ts == later


def test_reopen_creates_new_record_with_new_id():
    snap = Snapshot((item(assigned=None),))
    resolved = reconcile((open_record(),), (), T0 + MIN)
    reopened = reconcile(resolved, detect(snap, T0 + 2 * MIN), T0 + 2 * MIN)
    open_ids = [r.exception_id for r in reopened if r.status is ExceptionStatus.OPEN]
    assert open_ids == ["W1-OWNERSHIP_GAP-2"]
    assert len(reopened) == 2


def test_responder_escalates_but_never_downgrades():
    snap = Snapshot((item(assigned=None),))
    rec = reconcile((), detect(snap, T0), T0)
    escalated = tuple(replace(r, responder=Responder.INTENT_OWNER) for r in rec)
    out = reconcile(escalated, detect(snap, T0 + MIN), T0 + MIN)
    assert out[0].responder is Responder.INTENT_OWNER
