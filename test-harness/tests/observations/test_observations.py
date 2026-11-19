"""Observation Registry tests: append-only records, resolution authority,
no mutation of work items or the audit log, and lookup queries."""

import uuid

import pytest

from schema.db import connect, initialize
from services.observations import ObservationRegistry
from services.register import Register

INTENT_OWNER = "owner"


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
    register.create("W-2", "CONTROL-PLANE", "docs updated", "mgr", assigned_to="alice",
                    item_type="Execution")
    return ObservationRegistry(db, intent_owners={"CONTROL-PLANE": INTENT_OWNER})


def work_snapshot(db):
    items = [dict(r) for r in db.execute("SELECT * FROM work_items ORDER BY work_id")]
    audit = [dict(r) for r in db.execute("SELECT * FROM audit_log ORDER BY rowid")]
    return items, audit


def test_record_defaults_to_open_with_register_timestamp(env):
    obs = env.record("CONTROL-PLANE", "missing_artefact", "no test file", "alice", work_id="W-1")
    assert obs.status == "open"
    assert obs.resolved_by is None and obs.resolved_ts is None
    assert obs.recorded_ts
    assert obs.work_id == "W-1"


def test_observation_id_is_canonical_uuid(env):
    obs = env.record("CONTROL-PLANE", "spec_gap", "gap", "alice")
    assert str(uuid.UUID(obs.observation_id)) == obs.observation_id


def test_record_rejects_unknown_kind_empty_detail_and_unknown_work_item(env):
    with pytest.raises(ValueError):
        env.record("CONTROL-PLANE", "not_a_kind", "x", "alice")
    with pytest.raises(ValueError):
        env.record("CONTROL-PLANE", "spec_gap", "   ", "alice")
    with pytest.raises(LookupError):
        env.record("CONTROL-PLANE", "spec_gap", "x", "alice", work_id="W-MISSING")


def test_recording_and_resolving_do_not_touch_work_items_or_audit_log(env, db):
    before = work_snapshot(db)
    obs = env.record("CONTROL-PLANE", "spec_gap", "spec silent on retries", "alice", work_id="W-1")
    env.resolve(obs.observation_id, "mgr", "manager")
    assert work_snapshot(db) == before


def test_resolve_records_resolution_and_rejects_second_resolve(env):
    obs = env.record("CONTROL-PLANE", "spec_gap", "gap", "alice", work_id="W-1")
    resolved = env.resolve(obs.observation_id, "mgr", "manager")
    assert resolved.status == "resolved"
    assert resolved.resolved_by == "mgr"
    assert resolved.resolved_ts
    with pytest.raises(ValueError):
        env.resolve(obs.observation_id, "mgr", "manager")


def test_operational_kind_requires_manager_role(env):
    obs = env.record("CONTROL-PLANE", "stale_reference", "old link", "alice", work_id="W-1")
    with pytest.raises(PermissionError):
        env.resolve(obs.observation_id, "alice", "worker")
    assert env.get(obs.observation_id).status == "open"


@pytest.mark.parametrize("kind", ["decision", "validation"])
def test_governance_kind_requires_intent_owner(env, kind):
    obs = env.record("CONTROL-PLANE", kind, "governance item", "alice", work_id="W-1")
    with pytest.raises(PermissionError):
        env.resolve(obs.observation_id, "mgr", "manager")
    assert env.resolve(obs.observation_id, INTENT_OWNER, "worker").status == "resolved"


def test_governance_kind_rejected_when_project_has_no_intent_owner(db):
    registry = ObservationRegistry(db)
    Register(db).create("W-3", "OTHER", "criterion", "mgr", assigned_to="alice", item_type="Execution")
    obs = registry.record("OTHER", "policy", "policy point", "alice", work_id="W-3")
    with pytest.raises(PermissionError):
        registry.resolve(obs.observation_id, "owner", "manager")


def test_delete_and_in_place_edit_are_rejected(env, db):
    obs = env.record("CONTROL-PLANE", "duplicate_detected", "dup of W-2", "alice", work_id="W-1")
    with pytest.raises(Exception):
        db.execute("DELETE FROM observations WHERE observation_id = ?", (obs.observation_id,))
    with pytest.raises(Exception):
        db.execute("UPDATE observations SET detail = 'changed' WHERE observation_id = ?", (obs.observation_id,))
    assert env.get(obs.observation_id).detail == "dup of W-2"


def test_for_work_item_returns_open_and_resolved_for_that_item_only(env):
    a = env.record("CONTROL-PLANE", "spec_gap", "a", "alice", work_id="W-1")
    b = env.record("CONTROL-PLANE", "spec_gap", "b", "alice", work_id="W-1")
    env.record("CONTROL-PLANE", "spec_gap", "other item", "alice", work_id="W-2")
    env.resolve(a.observation_id, "mgr", "manager")
    result = env.for_work_item("W-1")
    assert {o.observation_id for o in result} == {a.observation_id, b.observation_id}
    assert {o.status for o in result} == {"open", "resolved"}


def test_query_filters_by_project_kind_and_status_alone_and_combined(env):
    s1 = env.record("CONTROL-PLANE", "spec_gap", "s1", "alice", work_id="W-1")
    env.record("CONTROL-PLANE", "decision", "d1", "alice", work_id="W-1")
    env.record("OTHER-PROJECT", "spec_gap", "s2", "alice")
    env.resolve(s1.observation_id, "mgr", "manager")

    assert len(env.query(project_id="CONTROL-PLANE")) == 2
    assert len(env.query(kind="spec_gap")) == 2
    assert len(env.query(status="resolved")) == 1
    assert len(env.query(project_id="CONTROL-PLANE", kind="spec_gap", status="open")) == 0
    assert len(env.query(project_id="CONTROL-PLANE", kind="decision", status="open")) == 1
    assert len(env.query()) == 3
