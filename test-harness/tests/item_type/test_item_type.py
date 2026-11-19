"""Explicit work item type (issue #32): validation, TYPE_MISSING, T7 gating, immutability, backfill."""

import re
import sqlite3

import pytest

from schema.db import SCHEMA_PATH, connect, initialize
from services.item_types import ITEM_TYPES, TYPE_INVALID, TYPE_MISSING
from services.register import Register
from services.state_machine import ILLEGAL_TRANSITION, Actor, StateMachine

INTENT_OWNER = Actor("lucien", "intent_owner")
CRITERION = "Intent Owner decision recorded on CP-02 closure"


@pytest.fixture
def db():
    conn = connect()
    initialize(conn)
    yield conn
    conn.close()


def insert_legacy_row(conn, work_id, criterion=CRITERION):
    """Row as written before #32: no item_type recorded."""
    conn.execute(
        """INSERT INTO work_items (work_id, project_id, assigned_to, state, done_criterion,
               block_reason, required, created_ts, last_update_ts)
           VALUES (?, 'CONTROL-PLANE', 'alice', 'Assigned', ?, NULL, 0, 'ts', 'ts')""",
        (work_id, criterion),
    )


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_each_allowed_type_is_accepted_and_recorded(db, item_type):
    Register(db).create("W-1", "CONTROL-PLANE", "done", "mgr", item_type=item_type)
    assert Register(db).get("W-1").item_type == item_type


@pytest.mark.parametrize("item_type", ["Plain Text", "  plain text  ", "", "   ", None])
def test_missing_or_non_type_label_is_rejected_as_type_missing(db, item_type):
    with pytest.raises(ValueError, match=f"^{TYPE_MISSING}"):
        Register(db).create("W-1", "CONTROL-PLANE", "done", "mgr", item_type=item_type)
    assert Register(db).get("W-1") is None


@pytest.mark.parametrize("item_type", ["decision", "Task", "Review", "Decisions"])
def test_unknown_or_wrong_case_type_is_rejected_as_type_invalid(db, item_type):
    with pytest.raises(ValueError, match=f"^{TYPE_INVALID}"):
        Register(db).create("W-1", "CONTROL-PLANE", "done", "mgr", item_type=item_type)
    assert Register(db).get("W-1") is None


def test_type_column_rejects_out_of_set_value_at_storage_layer(db):
    insert_legacy_row(db, "W-9")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE work_items SET item_type = 'Plain Text' WHERE work_id = 'W-9'")


def test_recorded_type_is_immutable(db):
    Register(db).create("W-1", "CONTROL-PLANE", "done", "mgr", item_type="Execution")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE work_items SET item_type = 'Decision' WHERE work_id = 'W-1'")


def test_t7_accepts_decision_item(db):
    Register(db).create("W-1", "CONTROL-PLANE", CRITERION, "mgr", assigned_to="alice",
                        item_type="Decision")
    result = StateMachine(db).transition("W-1", "Claimed Complete", INTENT_OWNER, ["decision record"])
    assert result.accepted, result


def test_t7_rejects_non_decision_item(db):
    Register(db).create("W-1", "CONTROL-PLANE", CRITERION, "mgr", assigned_to="alice",
                        item_type="Execution")
    result = StateMachine(db).transition("W-1", "Claimed Complete", INTENT_OWNER, ["decision record"])
    assert not result.accepted
    assert result.reason_code == ILLEGAL_TRANSITION


def test_t7_ignores_decision_wording_in_done_criterion(db):
    # A "decision" criterion no longer makes an item a Decision: only the explicit type counts.
    Register(db).create("W-1", "CONTROL-PLANE", CRITERION, "mgr", assigned_to="alice",
                        item_type="Execution")
    result = StateMachine(db).transition("W-1", "Claimed Complete", INTENT_OWNER, ["decision record"])
    assert result.reason_code == ILLEGAL_TRANSITION


def test_t7_rejects_untyped_legacy_item_as_type_missing(db):
    insert_legacy_row(db, "W-1")
    result = StateMachine(db).transition("W-1", "Claimed Complete", INTENT_OWNER, ["decision record"])
    assert not result.accepted
    assert result.reason_code == TYPE_MISSING


def test_migration_adds_column_and_flags_legacy_rows_without_inference(tmp_path):
    legacy_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    legacy_sql = re.sub(r",\n\s*-- NULL only.*?'Exception'\)\)", "", legacy_sql, flags=re.S)
    legacy_sql = re.sub(
        r"CREATE TRIGGER IF NOT EXISTS work_items_item_type_guard.*?END;", "", legacy_sql, flags=re.S)
    conn = connect(str(tmp_path / "legacy.db"))
    conn.executescript(legacy_sql)
    insert_legacy_row(conn, "W-OLD", criterion="Intent Owner decision recorded")  # must not infer Decision
    assert "item_type" not in {r[1] for r in conn.execute("PRAGMA table_info(work_items)")}

    initialize(conn)

    assert "item_type" in {r[1] for r in conn.execute("PRAGMA table_info(work_items)")}
    assert [item.work_id for item in Register(conn).untyped()] == ["W-OLD"]
    assert Register(conn).get("W-OLD").item_type is None
    conn.close()


def test_backfill_records_type_once_and_clears_flag(db):
    insert_legacy_row(db, "W-OLD", criterion="commit on origin")
    register = Register(db)

    assert register.set_item_type("W-OLD", "Execution").item_type == "Execution"
    assert register.untyped() == []
    with pytest.raises(ValueError, match="already recorded"):
        register.set_item_type("W-OLD", "Decision")


def test_backfill_rejects_invalid_type_and_unknown_item(db):
    insert_legacy_row(db, "W-OLD")
    with pytest.raises(ValueError, match=f"^{TYPE_MISSING}"):
        Register(db).set_item_type("W-OLD", "Plain Text")
    with pytest.raises(ValueError, match=f"^{TYPE_INVALID}"):
        Register(db).set_item_type("W-OLD", "Task")
    with pytest.raises(KeyError):
        Register(db).set_item_type("W-NOPE", "Execution")
    assert Register(db).get("W-OLD").item_type is None
