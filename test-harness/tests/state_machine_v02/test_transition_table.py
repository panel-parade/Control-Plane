"""State-Machine v0.2 verification: T1-T7 transition table.

The oracle below is transcribed from State-Machine-Spec v0.2 §3 and §5, independently of
services/state_machine.py. For every (from state, to state, actor role, evidence, item kind)
combination, the implementation must either accept the transition defined in the spec, or
reject it with the spec reason code, leaving the register and audit log unchanged.
"""

import pytest

from schema.db import connect, initialize
from services.register import STATES, Register
from services.state_machine import (
    ACTOR_NOT_PERMITTED,
    EVIDENCE_MISSING,
    ILLEGAL_TRANSITION,
    Actor,
    StateMachine,
    is_decision_item,
)

ROLE_IDENTITY = {
    "worker": "alice",  # assigned owner of W-1
    "manager": "mgr",
    "system": "system",
    "verifier": "verifier-bot",
    "intent_owner": "lucien",
}
ALL_ROLES = tuple(ROLE_IDENTITY)
OWNER = "alice"
DECISION_CRITERION = "Intent Owner decision recorded on CP-02 closure"
EXECUTION_CRITERION = "commit on origin AND tests pass"

# (from, to) -> (transition id, roles permitted). Every row of §3 requires evidence.
SPEC_TABLE = {
    ("Assigned", "Active"): ("T1", {"worker"}),
    ("Active", "Blocked"): ("T2", {"worker"}),
    ("Blocked", "Active"): ("T3", {"worker", "manager"}),
    ("Active", "Claimed Complete"): ("T4", {"worker"}),
    ("Claimed Complete", "Complete"): ("T5", {"verifier"}),
    ("Complete", "Archived"): ("T6", {"manager", "system"}),
    ("Assigned", "Claimed Complete"): ("T7", {"intent_owner"}),
}

# Steps that drive W-1 into each state through legal transitions.
PATHS = {
    "Assigned": [],
    "Active": [("worker", "Active")],
    "Blocked": [("worker", "Active"), ("worker", "Blocked")],
    "Claimed Complete": [("worker", "Active"), ("worker", "Claimed Complete")],
    "Complete": [("worker", "Active"), ("worker", "Claimed Complete"), ("verifier", "Complete")],
    "Archived": [
        ("worker", "Active"), ("worker", "Claimed Complete"),
        ("verifier", "Complete"), ("manager", "Archived"),
    ],
}


def expected_outcome(from_state, to_state, role, has_evidence, is_decision):
    """Spec oracle: None if the transition is accepted, otherwise the reason code."""
    entry = SPEC_TABLE.get((from_state, to_state))
    if entry is None:
        return ILLEGAL_TRANSITION
    tid, roles = entry
    if tid == "T7" and not is_decision:
        return ILLEGAL_TRANSITION
    if role not in roles:
        return ACTOR_NOT_PERMITTED
    if not has_evidence:
        return EVIDENCE_MISSING
    return None


@pytest.fixture
def db():
    conn = connect()
    initialize(conn)
    yield conn
    conn.close()


def make_item(db, state, is_decision):
    Register(db).create(
        "W-1", "CONTROL-PLANE",
        DECISION_CRITERION if is_decision else EXECUTION_CRITERION,
        "mgr", assigned_to=OWNER,
    )
    sm = StateMachine(db)
    for role, to_state in PATHS[state]:
        result = sm.transition("W-1", to_state, Actor(ROLE_IDENTITY[role], role), ["drive"])
        assert result.accepted, result
    return sm


def snapshot(db):
    item = dict(db.execute("SELECT * FROM work_items WHERE work_id = 'W-1'").fetchone())
    audit_count = db.execute("SELECT COUNT(*) FROM audit_log WHERE work_id = 'W-1'").fetchone()[0]
    return item, audit_count


@pytest.mark.parametrize("is_decision", [False, True], ids=["execution", "decision"])
@pytest.mark.parametrize("has_evidence", [False, True], ids=["no-evidence", "evidence"])
@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("to_state", STATES)
@pytest.mark.parametrize("from_state", list(PATHS))
def test_spec_matrix(db, from_state, to_state, role, has_evidence, is_decision):
    sm = make_item(db, from_state, is_decision)
    expected = expected_outcome(from_state, to_state, role, has_evidence, is_decision)
    before = snapshot(db)
    evidence = ["ref:1"] if has_evidence else None

    result = sm.transition("W-1", to_state, Actor(ROLE_IDENTITY[role], role), evidence)

    if expected is None:
        assert result.accepted, result
        assert result.new_state == to_state
        item, audit_count = snapshot(db)
        assert item["state"] == to_state
        assert audit_count == before[1] + 1
        audit = Register(db).audit_entries("W-1")[-1]
        assert (audit["event_type"], audit["old_state"], audit["new_state"]) == (
            "TRANSITION", from_state, to_state)
        assert audit["actor"] == ROLE_IDENTITY[role]
        if SPEC_TABLE[(from_state, to_state)][0] in ("T4", "T7"):
            assert Register(db).get("W-1").evidence_refs[-1] == "ref:1"
    else:
        assert not result.accepted
        assert result.reason_code == expected, result
        assert snapshot(db) == before


@pytest.mark.parametrize("criterion, expected", [
    (DECISION_CRITERION, True),
    ("Decision record filed for the programme", True),
    (EXECUTION_CRITERION, False),
])
def test_decision_item_inference_from_done_criterion(criterion, expected):
    # Assumption pending State-Machine-Spec Open Question 6 and issue #32.
    assert is_decision_item(criterion) is expected


def test_t7_decision_path_then_t5_is_only_route_to_complete(db):
    Register(db).create("W-1", "CONTROL-PLANE", DECISION_CRITERION, "mgr", assigned_to=OWNER)
    sm = StateMachine(db)
    intent_owner = Actor("lucien", "intent_owner")

    accepted = sm.transition("W-1", "Claimed Complete", intent_owner, ["decision:D-7"])

    assert accepted.accepted
    item = Register(db).get("W-1")
    assert item.state == "Claimed Complete"
    assert item.evidence_refs == ("decision:D-7",)
    audit = Register(db).audit_entries("W-1")[-1]
    assert (audit["old_state"], audit["new_state"], audit["actor"]) == (
        "Assigned", "Claimed Complete", "lucien")
    # T7 does not set Complete: the Intent Owner cannot, and T5 verification still applies.
    before = snapshot(db)
    assert sm.transition("W-1", "Complete", intent_owner, ["ok"]).reason_code == ACTOR_NOT_PERMITTED
    assert snapshot(db) == before
    assert sm.transition("W-1", "Complete", Actor("verifier-bot", "verifier"), ["ok"]).accepted
