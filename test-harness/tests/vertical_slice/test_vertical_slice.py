"""Vertical slice: CLI flow end to end and the T7 Decision demonstration.

The full T1-T7 transition matrix lives in tests/state_machine_v02; these tests cover the CLI path
and the T7 -> T5 sequence only.
"""

import io

import pytest

from cli.app import EXIT_ACCEPTED, EXIT_ERROR, EXIT_REJECTED, derive_display, main
from schema.db import connect, initialize
from services.register import Register
from services.state_machine import StateMachine


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "cp.db"
    conn = connect(str(path))
    initialize(conn)
    conn.close()
    return str(path)


def run(db, *args):
    out = io.StringIO()
    code = main([*args, "--db", db], out=out)
    return code, out.getvalue()


def register(db):
    conn = connect(db)
    return conn, Register(conn), StateMachine(conn)


def test_create_assign_transition_audit_and_query_flow(db):
    assert run(db, "create", "--work-id", "W-1", "--project-id", "P", "--done-criterion", "ship",
               "--item-type", "Execution", "--actor", "pm")[0] == EXIT_ACCEPTED
    assert run(db, "assign", "--work-id", "W-1", "--assigned-to", "worker-1",
               "--actor", "pm")[0] == EXIT_ACCEPTED
    code, out = run(db, "transition", "--work-id", "W-1", "--to", "Active", "--actor", "worker-1",
                    "--role", "worker", "--evidence", "branch x")
    assert code == EXIT_ACCEPTED and "ACCEPTED W-1" in out

    conn, reg, _ = register(db)
    try:
        item = reg.get("W-1")
        assert item.state == "Active" and item.assigned_to == "worker-1"
        assert [r["event_type"] for r in reg.audit_entries("W-1")] == [
            "CREATE", "ASSIGNMENT", "TRANSITION"]
        assert [i.work_id for i in reg.query(state="Active")] == ["W-1"]
    finally:
        conn.close()
    assert "derived:        Active" in run(db, "show", "--work-id", "W-1")[1]


def test_create_rejects_missing_or_plain_text_item_type(db):
    code, out = run(db, "create", "--work-id", "W-2", "--project-id", "P",
                    "--done-criterion", "x", "--item-type", "plain text", "--actor", "pm")
    assert code == EXIT_ERROR and "TYPE_MISSING" in out
    conn, reg, _ = register(db)
    try:
        assert reg.get("W-2") is None
    finally:
        conn.close()


def test_rejections_return_reason_codes_and_write_no_audit(db):
    run(db, "create", "--work-id", "W-3", "--project-id", "P", "--done-criterion", "x",
        "--item-type", "Execution", "--assigned-to", "worker-1", "--actor", "pm")
    cases = [
        (["--to", "Active", "--actor", "worker-2", "--role", "worker", "--evidence", "e"],
         "ACTOR_NOT_PERMITTED"),
        (["--to", "Complete", "--actor", "worker-1", "--role", "worker", "--evidence", "e"],
         "ILLEGAL_TRANSITION"),
        (["--to", "Active", "--actor", "worker-1", "--role", "worker"], "EVIDENCE_MISSING"),
    ]
    for args, reason in cases:
        code, out = run(db, "transition", "--work-id", "W-3", *args)
        assert code == EXIT_REJECTED and reason in out, out
    conn, reg, _ = register(db)
    try:
        assert reg.get("W-3").state == "Assigned"
        assert [r["event_type"] for r in reg.audit_entries("W-3")] == ["CREATE"]
    finally:
        conn.close()


def test_t7_decision_then_t5_required_before_complete(db):
    run(db, "create", "--work-id", "D-1", "--project-id", "P", "--done-criterion", "decide",
        "--item-type", "Decision", "--assigned-to", "lucien", "--actor", "pm")

    code, out = run(db, "transition", "--work-id", "D-1", "--to", "Claimed Complete",
                    "--actor", "lucien", "--role", "intent_owner", "--evidence", "Decision recorded")
    assert code == EXIT_ACCEPTED and "Claimed Complete" in out

    code, out = run(db, "transition", "--work-id", "D-1", "--to", "Complete",
                    "--actor", "lucien", "--role", "intent_owner", "--evidence", "Decision recorded")
    assert code == EXIT_REJECTED and "ACTOR_NOT_PERMITTED" in out

    code, _ = run(db, "transition", "--work-id", "D-1", "--to", "Complete",
                  "--actor", "verifier-1", "--role", "verifier", "--evidence", "criterion met")
    assert code == EXIT_ACCEPTED

    conn, reg, _ = register(db)
    try:
        item = reg.get("D-1")
        assert item.state == "Complete" and item.evidence_refs == ("Decision recorded",)
        assert [r["event_type"] for r in reg.audit_entries("D-1")] == [
            "CREATE", "TRANSITION", "TRANSITION"]
    finally:
        conn.close()


def test_t7_only_for_decision_items_and_intent_owner(db):
    run(db, "create", "--work-id", "E-1", "--project-id", "P", "--done-criterion", "x",
        "--item-type", "Execution", "--assigned-to", "lucien", "--actor", "pm")
    run(db, "create", "--work-id", "D-2", "--project-id", "P", "--done-criterion", "x",
        "--item-type", "Decision", "--assigned-to", "lucien", "--actor", "pm")

    code, out = run(db, "transition", "--work-id", "E-1", "--to", "Claimed Complete",
                    "--actor", "lucien", "--role", "intent_owner", "--evidence", "Decision recorded")
    assert code == EXIT_REJECTED and "ILLEGAL_TRANSITION" in out

    code, out = run(db, "transition", "--work-id", "D-2", "--to", "Claimed Complete",
                    "--actor", "verifier-1", "--role", "verifier", "--evidence", "Decision recorded")
    assert code == EXIT_REJECTED and "ACTOR_NOT_PERMITTED" in out


def test_derived_display_flags_ownership_gap(db):
    conn, reg, _ = register(db)
    try:
        gap = reg.create("G-1", "P", "x", "pm", item_type="Execution")
        assert derive_display(gap) == "Ownership Gap"
    finally:
        conn.close()
