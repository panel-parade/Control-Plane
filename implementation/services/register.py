"""Work Register: create, assign and read-only query of work items.

Only the state machine (state_machine.py) may change ``state``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

STATES = ("Assigned", "Active", "Blocked", "Claimed Complete", "Complete", "Archived")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorkItem:
    work_id: str
    project_id: str
    assigned_to: Optional[str]
    state: str
    done_criterion: str
    evidence_ref: Optional[str]
    block_reason: Optional[str]
    required: bool
    created_ts: str
    last_update_ts: str


def _row_to_item(row: sqlite3.Row) -> WorkItem:
    return WorkItem(
        work_id=row["work_id"],
        project_id=row["project_id"],
        assigned_to=row["assigned_to"],
        state=row["state"],
        done_criterion=row["done_criterion"],
        evidence_ref=row["evidence_ref"],
        block_reason=row["block_reason"],
        required=bool(row["required"]),
        created_ts=row["created_ts"],
        last_update_ts=row["last_update_ts"],
    )


class Register:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        work_id: str,
        project_id: str,
        done_criterion: str,
        actor: str,
        assigned_to: Optional[str] = None,
        required: bool = False,
    ) -> WorkItem:
        """Create a work item in state ``Assigned`` with one ``CREATE`` audit entry."""
        if not work_id or not work_id.strip():
            raise ValueError("work_id is required")
        if not project_id or not project_id.strip():
            raise ValueError("project_id is required")
        if not done_criterion or not done_criterion.strip():
            raise ValueError("done_criterion must be non-empty")
        now = utc_now()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """INSERT INTO work_items
                   (work_id, project_id, assigned_to, state, done_criterion,
                    evidence_ref, block_reason, required, created_ts, last_update_ts)
                   VALUES (?, ?, ?, 'Assigned', ?, NULL, NULL, ?, ?, ?)""",
                (work_id, project_id, assigned_to, done_criterion, int(required), now, now),
            )
            conn.execute(
                """INSERT INTO audit_log
                   (work_id, event_type, old_state, new_state, actor, timestamp)
                   VALUES (?, 'CREATE', NULL, 'Assigned', ?, ?)""",
                (work_id, actor, now),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return self.get(work_id)

    def assign(self, work_id: str, assigned_to: Optional[str], actor: str) -> WorkItem:
        """Set the owner (or clear it, creating an Ownership Gap) with an ``ASSIGNMENT`` audit entry."""
        conn = self._conn
        now = utc_now()
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT state FROM work_items WHERE work_id = ?", (work_id,)
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise KeyError(work_id)
            conn.execute(
                "UPDATE work_items SET assigned_to = ?, last_update_ts = ? WHERE work_id = ?",
                (assigned_to, now, work_id),
            )
            conn.execute(
                """INSERT INTO audit_log
                   (work_id, event_type, old_state, new_state, actor, timestamp)
                   VALUES (?, 'ASSIGNMENT', ?, ?, ?, ?)""",
                (work_id, row["state"], row["state"], actor, now),
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return self.get(work_id)

    def get(self, work_id: str) -> Optional[WorkItem]:
        row = self._conn.execute(
            "SELECT * FROM work_items WHERE work_id = ?", (work_id,)
        ).fetchone()
        return _row_to_item(row) if row else None

    def query(
        self,
        *,
        work_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        state: Optional[str] = None,
        project_id: Optional[str] = None,
        last_update_ts_from: Optional[str] = None,
        last_update_ts_to: Optional[str] = None,
    ) -> list[WorkItem]:
        """Read-only, side-effect-free query. Results ordered by work_id."""
        clauses: list[str] = []
        params: list[object] = []
        for column, value in (
            ("work_id", work_id),
            ("assigned_to", assigned_to),
            ("state", state),
            ("project_id", project_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if last_update_ts_from is not None:
            clauses.append("last_update_ts >= ?")
            params.append(last_update_ts_from)
        if last_update_ts_to is not None:
            clauses.append("last_update_ts <= ?")
            params.append(last_update_ts_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM work_items{where} ORDER BY work_id", params
        ).fetchall()
        return [_row_to_item(r) for r in rows]

    def audit_entries(self, work_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM audit_log WHERE work_id = ? ORDER BY audit_id", (work_id,)
        ).fetchall()
