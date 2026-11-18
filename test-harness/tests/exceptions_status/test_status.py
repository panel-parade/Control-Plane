from datetime import datetime, timedelta, timezone

from exceptions import (
    ExceptionRecord,
    ExceptionStatus,
    ExceptionType,
    Responder,
    Snapshot,
    WorkItem,
    WorkState,
)
from status import Status, derive_programme_status, derive_project_status

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def item(work_id, state=WorkState.ACTIVE, project="P1", required=True, assigned="alice"):
    return WorkItem(work_id, project, assigned, state, T0, required)


def exc(work_id, kind, project="P1", detected=T0, resolved=None):
    return ExceptionRecord(f"{work_id}-{kind.value}-1", work_id, project, kind, detected,
                           Responder.MANAGER, ExceptionStatus.OPEN if resolved is None
                           else ExceptionStatus.RESOLVED, "detail", resolved)


def project(items, exceptions=(), as_of=T0):
    return derive_project_status(Snapshot(tuple(items)), tuple(exceptions), "P1", as_of)


def test_complete_wins_over_red_when_all_required_done():
    p = project([item("W1", WorkState.COMPLETE)],
                [exc("W1", ExceptionType.VERIFICATION_FAILURE)])
    assert p.status is Status.COMPLETE


def test_red_wins_over_amber():
    p = project([item("W1", WorkState.ACTIVE), item("W2", WorkState.ACTIVE)],
                [exc("W1", ExceptionType.PROGRESS_GAP), exc("W2", ExceptionType.OWNERSHIP_GAP)])
    assert p.status is Status.RED
    assert p.exception_ids == ("W2-OWNERSHIP_GAP-1",)


def test_each_red_type_makes_project_red():
    for kind in (ExceptionType.VERIFICATION_FAILURE, ExceptionType.OWNERSHIP_GAP,
                 ExceptionType.LONG_TERM_BLOCK):
        assert project([item("W1")], [exc("W1", kind)]).status is Status.RED


def test_old_progress_gap_does_not_escalate_to_red():
    p = project([item("W1")], [exc("W1", ExceptionType.PROGRESS_GAP)])
    assert p.status is Status.AMBER


def test_blocked_item_without_long_term_block_is_amber():
    assert project([item("W1", WorkState.BLOCKED)]).status is Status.AMBER


def test_empty_project_is_green_and_not_complete():
    assert project([]).status is Status.GREEN


def test_no_open_exceptions_is_green():
    assert project([item("W1")]).status is Status.GREEN


def test_completion_requires_required_work_only():
    p = project([item("W1", WorkState.COMPLETE), item("W2", WorkState.ACTIVE, required=False)])
    assert p.status is Status.COMPLETE


def test_resolved_exception_is_not_counted_as_of_now():
    later = T0 + timedelta(minutes=5)
    p = project([item("W1")], [exc("W1", ExceptionType.OWNERSHIP_GAP, resolved=later)],
                as_of=later)
    assert p.status is Status.GREEN


def test_exception_still_open_before_resolution_time():
    later = T0 + timedelta(minutes=5)
    p = project([item("W1")], [exc("W1", ExceptionType.OWNERSHIP_GAP, resolved=later)],
                as_of=T0 + timedelta(minutes=1))
    assert p.status is Status.RED


def test_status_output_is_explainable():
    p = project([item("W1", WorkState.BLOCKED)], [exc("W1", ExceptionType.LONG_TERM_BLOCK)])
    assert p.exception_ids == ("W1-LONG_TERM_BLOCK-1",)
    assert p.work_ids == ("W1",)
    assert any("LONG_TERM_BLOCK" in r for r in p.reasons)


def test_programme_rollup_is_worst_of():
    items = [item("A1", project="A"), item("B1", WorkState.BLOCKED, project="B")]
    snap = Snapshot(tuple(items))
    exceptions = [exc("A1", ExceptionType.VERIFICATION_FAILURE, project="A")]
    prog = derive_programme_status(snap, exceptions, T0)
    assert prog.status is Status.RED
    assert {p.project_id: p.status for p in prog.projects} == {"A": Status.RED, "B": Status.AMBER}


def test_programme_complete_only_if_every_project_complete():
    items = [item("A1", WorkState.COMPLETE, project="A"), item("B1", project="B")]
    prog = derive_programme_status(Snapshot(tuple(items)), (), T0)
    assert prog.status is Status.GREEN


def test_programme_complete_when_all_projects_complete():
    items = [item("A1", WorkState.COMPLETE, project="A"), item("B1", WorkState.ARCHIVED, project="B")]
    assert derive_programme_status(Snapshot(tuple(items)), (), T0).status is Status.COMPLETE


def test_empty_programme_is_green():
    assert derive_programme_status(Snapshot(()), (), T0).status is Status.GREEN


def test_derivation_is_deterministic_regardless_of_input_order():
    items = [item("W2", WorkState.BLOCKED), item("W1")]
    exceptions = [exc("W2", ExceptionType.LONG_TERM_BLOCK), exc("W1", ExceptionType.PROGRESS_GAP)]
    a = derive_programme_status(Snapshot(tuple(items)), tuple(exceptions), T0)
    b = derive_programme_status(Snapshot(tuple(reversed(items))), tuple(reversed(exceptions)), T0)
    assert a == b
