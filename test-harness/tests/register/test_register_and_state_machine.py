"""Register and state machine tests: rejection without mutation, audit atomicity,
actor permission, NOT_FOUND, and the transition table."""

import sqlite3

import pytest

from schema.db import connect, initialize
from services.register import Register
from services.state_machine import (
    ACTOR_NOT_PERMITTED,
    EVIDENCE_MISSING,
    ILLEGAL_TRANSITION,
    NOT_FOUND,
    VERIFICATION_FAILURE,
    Actor,
    StateMachine,
)

WORKER = Actor("alice", "worker")
MANAGER = Actor("mgr", "manager")
VERIFIER = Actor("verifier-bot", "verifier")
SYSTEM = Actor("system", "system")


@pytest.fixture
def db():
    conn = connect()
    initialize(conn)
    yield conn
    conn.close()


@pytest.fixture
def env(db):
    register = Register(db)
    register.create("W-1", "CONTROL-PLANE", "commit on origin AND tests pass", "mgr", assigned_to="alice",
                    item_type="Execution")
    return register, StateMachine(db), db


def snapshot(db):
    item = db.execute("SELECT * FROM work_items WHERE work_id = 'W-1'").fetchone()
    audit_count = db.execute("SELECT COUNT(*) FROM audit_log WHERE work_id = 'W-1'").fetchone()[0]
    return dict(item), audit_count


def test_illegal_transition_rejected_without_mutation(env):
    _, sm, db = env
    before = snapshot(db)
    result = sm.transition("W-1", "Complete", WORKER, ["evidence"])
    assert not result.accepted
    assert result.reason_code == ILLEGAL_TRANSITION
    assert snapshot(db) == before


def test_skipping_states_is_illegal(env):
    _, sm, _ = env
    # Assigned -> Claimed Complete is not in T1-T6.
    result = sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    assert result.reason_code == ILLEGAL_TRANSITION


def test_claimed_complete_to_active_recovery_stays_illegal(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    before = snapshot(db)
    result = sm.transition("W-1", "Active", WORKER, ["retry"])
    assert result.reason_code == ILLEGAL_TRANSITION
    assert snapshot(db) == before


def test_worker_cannot_set_complete(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    before = snapshot(db)
    result = sm.transition("W-1", "Complete", WORKER, ["sha:abc"])
    assert result.reason_code == ACTOR_NOT_PERMITTED
    assert snapshot(db) == before


def test_non_owner_cannot_start_work(env):
    _, sm, db = env
    before = snapshot(db)
    result = sm.transition("W-1", "Active", Actor("bob", "worker"), ["started"])
    assert result.reason_code == ACTOR_NOT_PERMITTED
    assert snapshot(db) == before


def test_t1_rejected_when_owner_is_null(db):
    Register(db).create("W-2", "CONTROL-PLANE", "done", "mgr", assigned_to=None, item_type="Execution")
    result = StateMachine(db).transition("W-2", "Active", WORKER, ["started"])
    assert result.reason_code == ACTOR_NOT_PERMITTED
    assert db.execute("SELECT state FROM work_items WHERE work_id='W-2'").fetchone()[0] == "Assigned"


def test_missing_evidence_rejected_without_mutation(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    before = snapshot(db)
    for evidence in (None, [], ["   "], ""):
        result = sm.transition("W-1", "Claimed Complete", WORKER, evidence)
        assert result.reason_code == EVIDENCE_MISSING
    assert snapshot(db) == before


def test_any_nonempty_reference_satisfies_t4_structure(env):
    # Structural check only: resolving references is Stream B's responsibility.
    _, sm, _ = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    assert sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"]).accepted


def test_evidence_is_stored_as_ordered_list(env):
    register, sm, _ = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    assert sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc", "tests:pass"]).accepted
    assert register.get("W-1").evidence_refs == ("sha:abc", "tests:pass")


def test_verification_failure_keeps_claimed_complete_and_audits_once(env):
    register, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    audits_before = db.execute("SELECT COUNT(*) FROM audit_log WHERE work_id='W-1'").fetchone()[0]
    result = sm.verification_failed("W-1", VERIFIER, ["tests:fail"])
    assert result.accepted
    assert result.reason_code == VERIFICATION_FAILURE
    item = register.get("W-1")
    assert item.state == "Claimed Complete"
    assert item.evidence_refs == ("sha:abc", "tests:fail")
    audits = db.execute(
        "SELECT event_type, old_state, new_state FROM audit_log WHERE work_id='W-1' ORDER BY audit_id"
    ).fetchall()
    assert len(audits) == audits_before + 1
    assert tuple(audits[-1]) == ("VERIFICATION_FAILURE", "Claimed Complete", "Claimed Complete")


def test_verification_failure_is_verifier_only_and_leaves_state_unchanged(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    before = snapshot(db)
    assert sm.verification_failed("W-1", WORKER, ["tests:fail"]).reason_code == ACTOR_NOT_PERMITTED
    assert snapshot(db) == before


def test_verification_failure_requires_claimed_complete(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    before = snapshot(db)
    assert sm.verification_failed("W-1", VERIFIER, ["tests:fail"]).reason_code == ILLEGAL_TRANSITION
    assert snapshot(db) == before


def test_verification_failure_requires_evidence_and_known_item(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    before = snapshot(db)
    assert sm.verification_failed("W-1", VERIFIER, None).reason_code == EVIDENCE_MISSING
    assert snapshot(db) == before
    assert sm.verification_failed("missing", VERIFIER, ["tests:fail"]).reason_code == NOT_FOUND


def test_not_found_writes_nothing(db):
    result = StateMachine(db).transition("missing", "Active", WORKER, ["started"])
    assert result.reason_code == NOT_FOUND
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_full_lifecycle_accepted_with_one_audit_entry_per_change(env):
    _, sm, db = env
    steps = [
        ("Active", WORKER, ["started"]),
        ("Blocked", WORKER, ["waiting on API key"]),
        ("Active", MANAGER, ["key provided"]),
        ("Claimed Complete", WORKER, ["sha:abc123"]),
        ("Complete", VERIFIER, ["verification passed"]),
        ("Archived", SYSTEM, ["closure rule: complete and verified"]),
    ]
    for to_state, actor, evidence in steps:
        result = sm.transition("W-1", to_state, actor, evidence)
        assert result.accepted, result
        assert result.new_state == to_state
    audits = db.execute(
        "SELECT old_state, new_state, actor FROM audit_log WHERE work_id='W-1' "
        "AND event_type='TRANSITION' ORDER BY audit_id").fetchall()
    assert len(audits) == len(steps)
    assert audits[-1]["new_state"] == "Archived"


def test_t2_records_block_reason_and_t3_clears_it(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Blocked", WORKER, ["waiting on review"])
    assert db.execute("SELECT block_reason FROM work_items").fetchone()[0] == "waiting on review"
    sm.transition("W-1", "Active", WORKER, ["review received"])
    assert db.execute("SELECT block_reason FROM work_items").fetchone()[0] is None


def test_archived_is_terminal(env):
    _, sm, db = env
    sm.transition("W-1", "Active", WORKER, ["started"])
    sm.transition("W-1", "Claimed Complete", WORKER, ["sha:abc"])
    sm.transition("W-1", "Complete", VERIFIER, ["ok"])
    sm.transition("W-1", "Archived", MANAGER, ["closed"])
    before = snapshot(db)
    assert sm.transition("W-1", "Active", MANAGER, ["reopen"]).reason_code == ILLEGAL_TRANSITION
    assert snapshot(db) == before


def test_audit_write_failure_rolls_back_state_change(env):
    _, sm, db = env
    db.execute(
        "CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log WHEN NEW.new_state = 'Active' "
        "BEGIN SELECT RAISE(ABORT, 'simulated audit failure'); END")
    before = snapshot(db)
    with pytest.raises(sqlite3.DatabaseError):
        sm.transition("W-1", "Active", WORKER, ["started"])
    assert snapshot(db) == before
    assert db.in_transaction is False


def test_direct_state_write_is_prohibited(env):
    _, _, db = env
    with pytest.raises(sqlite3.IntegrityError, match="direct state writes prohibited"):
        db.execute("UPDATE work_items SET state = 'Complete' WHERE work_id = 'W-1'")
    assert db.execute("SELECT state FROM work_items").fetchone()[0] == "Assigned"


def test_audit_log_is_append_only(env):
    _, _, db = env
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE audit_log SET actor = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM audit_log")


def test_create_writes_creation_audit_entry(env):
    register, _, _ = env
    entries = register.audit_entries("W-1")
    assert len(entries) == 1
    assert entries[0]["old_state"] is None
    assert entries[0]["new_state"] == "Assigned"
    assert entries[0]["event_type"] == "CREATE"


def test_assignment_change_is_audited_without_state_change(env):
    register, _, _ = env
    register.assign("W-1", "bob", actor="mgr")
    entries = register.audit_entries("W-1")
    assert entries[-1]["event_type"] == "ASSIGNMENT"
    assert entries[-1]["old_state"] == entries[-1]["new_state"] == "Assigned"
    assert register.get("W-1").assigned_to == "bob"


def test_assign_unknown_work_item_is_not_found(db):
    with pytest.raises(KeyError):
        Register(db).assign("missing", "bob", actor="mgr")
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
