"""Observation Registry: record, resolve and query observations (Observation-Registry-Spec).

Observations are separate from the Work Register. Recording or resolving never
changes a work item's state and never writes to ``audit_log``.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Mapping, Optional

from services.register import utc_now

OPERATIONAL_KINDS = (
    "missing_artefact",
    "duplicate_detected",
    "stale_reference",
    "verification_issue",
    "reproduction_issue",
    "spec_gap",
)
GOVERNANCE_KINDS = (
    "decision",
    "validation",
    "policy",
    "authority",
    "ratification",
    "strategic_direction",
)
KINDS = OPERATIONAL_KINDS + GOVERNANCE_KINDS
STATUSES = ("open", "resolved")
MANAGER_ROLE = "manager"


@dataclass(frozen=True)
class Observation:
    observation_id: str
    project_id: str
    work_id: Optional[str]
    kind: str
    detail: str
    reference: Optional[str]
    recorded_by: str
    recorded_ts: str
    status: str
    resolved_by: Optional[str]
    resolved_ts: Optional[str]


def _row_to_observation(row: sqlite3.Row) -> Observation:
    return Observation(**{key: row[key] for key in row.keys()})


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")


class ObservationRegistry:
    """``intent_owners`` maps project_id to the Intent Owner identity for that project.

    The Intent Owner is project configuration, not a State Machine actor. It
    authorises resolution of governance kinds only.
    """

    def __init__(
        self, conn: sqlite3.Connection, intent_owners: Optional[Mapping[str, str]] = None
    ) -> None:
        self._conn = conn
        self._intent_owners = dict(intent_owners or {})

    def record(
        self,
        project_id: str,
        kind: str,
        detail: str,
        recorded_by: str,
        work_id: Optional[str] = None,
        reference: Optional[str] = None,
    ) -> Observation:
        """Record an observation with status ``open``. Writes only to ``observations``."""
        _require(project_id, "project_id")
        _require(detail, "detail")
        _require(recorded_by, "recorded_by")
        if kind not in KINDS:
            raise ValueError(f"unknown observation kind: {kind!r}")
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            if work_id is not None:
                exists = conn.execute(
                    "SELECT 1 FROM work_items WHERE work_id = ?", (work_id,)
                ).fetchone()
                if exists is None:
                    raise LookupError(f"work item not found: {work_id}")
            observation_id = str(uuid.uuid4())
            now = utc_now()
            conn.execute(
                """INSERT INTO observations
                   (observation_id, project_id, work_id, kind, detail, reference,
                    recorded_by, recorded_ts, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
                (observation_id, project_id, work_id, kind, detail, reference, recorded_by, now),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return self.get(observation_id)

    def resolve(self, observation_id: str, resolved_by: str, role: str) -> Observation:
        """Resolve an open observation. Resolution is recorded, never deleted.

        Operational kinds require the ``manager`` role. Governance kinds require
        ``resolved_by`` to be the Intent Owner configured for the observation's project.
        """
        _require(resolved_by, "resolved_by")
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT project_id, kind, status FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"observation not found: {observation_id}")
            if row["status"] != "open":
                raise ValueError(f"observation already resolved: {observation_id}")
            if row["kind"] in OPERATIONAL_KINDS:
                if role != MANAGER_ROLE:
                    raise PermissionError(
                        f"{row['kind']} is resolved by the Manager Layer, not role {role!r}"
                    )
            elif resolved_by != self._intent_owners.get(row["project_id"]):
                raise PermissionError(
                    f"{row['kind']} is resolved by the Intent Owner of {row['project_id']}"
                )
            conn.execute(
                """UPDATE observations SET status = 'resolved', resolved_by = ?, resolved_ts = ?
                   WHERE observation_id = ?""",
                (resolved_by, utc_now(), observation_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return self.get(observation_id)

    def get(self, observation_id: str) -> Optional[Observation]:
        row = self._conn.execute(
            "SELECT * FROM observations WHERE observation_id = ?", (observation_id,)
        ).fetchone()
        return _row_to_observation(row) if row is not None else None

    def for_work_item(self, work_id: str) -> tuple[Observation, ...]:
        """All observations for one work item, open and resolved, in one query."""
        rows = self._conn.execute(
            """SELECT * FROM observations WHERE work_id = ?
               ORDER BY recorded_ts, observation_id""",
            (work_id,),
        ).fetchall()
        return tuple(_row_to_observation(r) for r in rows)

    def query(
        self,
        project_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
    ) -> tuple[Observation, ...]:
        """Read-only filter by any combination of project_id, kind and status."""
        if kind is not None and kind not in KINDS:
            raise ValueError(f"unknown observation kind: {kind!r}")
        if status is not None and status not in STATUSES:
            raise ValueError(f"unknown observation status: {status!r}")
        clauses, params = [], []
        for column, value in (("project_id", project_id), ("kind", kind), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM observations {where} ORDER BY recorded_ts, observation_id",
            params,
        ).fetchall()
        return tuple(_row_to_observation(r) for r in rows)
