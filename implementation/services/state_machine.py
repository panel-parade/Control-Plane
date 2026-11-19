"""Control Plane v1 State Machine: the only path that may change work item state.

See specifications/State-Machine-Spec.md (T1-T6) and Evidence-Spec §5.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional, Union

from services.item_types import TYPE_MISSING
from services.register import STATES, utc_now

ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
ACTOR_NOT_PERMITTED = "ACTOR_NOT_PERMITTED"
EVIDENCE_MISSING = "EVIDENCE_MISSING"
NOT_FOUND = "NOT_FOUND"
VERIFICATION_FAILURE = "VERIFICATION_FAILURE"

ROLES = ("worker", "manager", "system", "verifier", "intent_owner")

Evidence = Optional[Union[str, Iterable[str]]]


@dataclass(frozen=True)
class Actor:
    identity: str
    role: str  # one of ROLES


@dataclass(frozen=True)
class TransitionRule:
    tid: str
    from_state: str
    to_state: str
    allowed_roles: frozenset
    worker_must_be_owner: bool
    evidence_kind: str  # human-readable requirement, used in EVIDENCE_MISSING messages


# T1-T7 from State-Machine-Spec v0.2 §3. Any (from, to) pair not listed is ILLEGAL_TRANSITION.
TRANSITIONS: dict[tuple[str, str], TransitionRule] = {
    ("Assigned", "Active"): TransitionRule(
        "T1", "Assigned", "Active", frozenset({"worker"}), True, "activity reference"),
    ("Active", "Blocked"): TransitionRule(
        "T2", "Active", "Blocked", frozenset({"worker"}), True, "block reason"),
    ("Blocked", "Active"): TransitionRule(
        "T3", "Blocked", "Active", frozenset({"worker", "manager"}), True, "block resolution"),
    ("Active", "Claimed Complete"): TransitionRule(
        "T4", "Active", "Claimed Complete", frozenset({"worker"}), True, "evidence reference"),
    ("Claimed Complete", "Complete"): TransitionRule(
        "T5", "Claimed Complete", "Complete", frozenset({"verifier"}), False,
        "done criterion satisfied"),
    ("Complete", "Archived"): TransitionRule(
        "T6", "Complete", "Archived", frozenset({"manager", "system"}), False, "closure rule reference"),
    # T7 does not set Complete (Rule 2); T5 remains the only route to Complete.
    ("Assigned", "Claimed Complete"): TransitionRule(
        "T7", "Assigned", "Claimed Complete", frozenset({"intent_owner"}), False, "decision record"),
}


@dataclass(frozen=True)
class TransitionResult:
    accepted: bool
    work_id: str
    new_state: Optional[str] = None
    audit_id: Optional[int] = None
    reason_code: Optional[str] = None
    detail: Optional[str] = None


def _normalise_evidence(evidence: Evidence) -> list[str]:
    if evidence is None:
        return []
    if isinstance(evidence, str):
        items = [evidence]
    else:
        items = list(evidence)
    return [e.strip() for e in items if isinstance(e, str) and e.strip()]


def _reject(work_id: str, code: str, detail: str) -> TransitionResult:
    return TransitionResult(accepted=False, work_id=work_id, reason_code=code, detail=detail)


class StateMachine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def transition(
        self,
        work_id: str,
        to_state: str,
        actor: Actor,
        evidence: Evidence = None,
    ) -> TransitionResult:
        """Attempt a transition. Accepted results write one audit entry atomically with the state change.

        Rejected results (reason codes ILLEGAL_TRANSITION, ACTOR_NOT_PERMITTED,
        EVIDENCE_MISSING, NOT_FOUND) never mutate the register and write no audit entry.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = self._apply(work_id, to_state, actor, evidence)
        except Exception:
            conn.execute("ROLLBACK")
            raise
        if result.accepted:
            conn.execute("COMMIT")
        else:
            conn.execute("ROLLBACK")
        return result

    def _apply(self, work_id: str, to_state: str, actor: Actor, evidence: Evidence) -> TransitionResult:
        conn = self._conn
        row = conn.execute(
            "SELECT state, assigned_to, item_type FROM work_items WHERE work_id = ?",
            (work_id,),
        ).fetchone()
        if row is None:
            return _reject(work_id, NOT_FOUND, f"work item {work_id!r} does not exist")

        from_state = row["state"]
        rule = TRANSITIONS.get((from_state, to_state))
        if to_state not in STATES or rule is None:
            return _reject(
                work_id, ILLEGAL_TRANSITION, f"{from_state!r} -> {to_state!r} is not in T1-T7")
        if rule.tid == "T7":
            if row["item_type"] is None:
                return _reject(work_id, TYPE_MISSING, "T7 requires a recorded item type")
            if row["item_type"] != "Decision":
                return _reject(
                    work_id, ILLEGAL_TRANSITION, "T7 applies only to Decision items")

        if actor.role not in ROLES or actor.role not in rule.allowed_roles:
            return _reject(
                work_id, ACTOR_NOT_PERMITTED,
                f"role {actor.role!r} may not perform {rule.tid}")
        if (rule.worker_must_be_owner and actor.role == "worker"
                and actor.identity != row["assigned_to"]):
            return _reject(
                work_id, ACTOR_NOT_PERMITTED,
                f"{rule.tid} requires the assigned owner ({row['assigned_to']!r} or none)")

        refs = _normalise_evidence(evidence)
        if not refs:
            return _reject(work_id, EVIDENCE_MISSING, f"{rule.tid} requires {rule.evidence_kind}")

        now = utc_now()
        block_sql = "block_reason"
        block_params: list[object] = []
        if rule.tid == "T2":
            block_sql = "?"
            block_params = [refs[0]]
        elif rule.tid == "T3":
            block_sql = "NULL"

        conn.execute("UPDATE register_guard SET allow_state_write = 1 WHERE id = 1")
        try:
            conn.execute(
                f"""UPDATE work_items
                    SET state = ?, block_reason = {block_sql}, last_update_ts = ?
                    WHERE work_id = ?""",
                [to_state, *block_params, now, work_id],
            )
        finally:
            conn.execute("UPDATE register_guard SET allow_state_write = 0 WHERE id = 1")

        cursor = conn.execute(
            """INSERT INTO audit_log
               (work_id, event_type, old_state, new_state, actor, timestamp)
               VALUES (?, 'TRANSITION', ?, ?, ?, ?)""",
            (work_id, from_state, to_state, actor.identity, now),
        )
        if rule.tid in ("T4", "T7"):
            self._attach_evidence(work_id, cursor.lastrowid, refs)
        return TransitionResult(
            accepted=True, work_id=work_id, new_state=to_state, audit_id=cursor.lastrowid)

    def verification_failed(
        self,
        work_id: str,
        actor: Actor,
        evidence: Evidence = None,
    ) -> TransitionResult:
        """Record a failed verification of a Claimed Complete item.

        The state stays ``Claimed Complete`` (no transition). One ``VERIFICATION_FAILURE``
        audit entry is written atomically with the attached evidence. Rejections mutate nothing.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = self._apply_verification_failure(work_id, actor, evidence)
        except Exception:
            conn.execute("ROLLBACK")
            raise
        if result.accepted:
            conn.execute("COMMIT")
        else:
            conn.execute("ROLLBACK")
        return result

    def _apply_verification_failure(
        self, work_id: str, actor: Actor, evidence: Evidence
    ) -> TransitionResult:
        conn = self._conn
        row = conn.execute(
            "SELECT state FROM work_items WHERE work_id = ?", (work_id,)
        ).fetchone()
        if row is None:
            return _reject(work_id, NOT_FOUND, f"work item {work_id!r} does not exist")
        if row["state"] != "Claimed Complete":
            return _reject(
                work_id, ILLEGAL_TRANSITION,
                f"{VERIFICATION_FAILURE} is only valid from 'Claimed Complete', not {row['state']!r}")
        if actor.role != "verifier":
            return _reject(
                work_id, ACTOR_NOT_PERMITTED,
                f"role {actor.role!r} may not record {VERIFICATION_FAILURE}")
        refs = _normalise_evidence(evidence)
        if not refs:
            return _reject(
                work_id, EVIDENCE_MISSING, f"{VERIFICATION_FAILURE} requires verification evidence")

        now = utc_now()
        cursor = conn.execute(
            """INSERT INTO audit_log
               (work_id, event_type, old_state, new_state, actor, timestamp)
               VALUES (?, 'VERIFICATION_FAILURE', 'Claimed Complete', 'Claimed Complete', ?, ?)""",
            (work_id, actor.identity, now),
        )
        self._attach_evidence(work_id, cursor.lastrowid, refs)
        conn.execute(
            "UPDATE work_items SET last_update_ts = ? WHERE work_id = ?", (now, work_id))
        return TransitionResult(
            accepted=True, work_id=work_id, new_state="Claimed Complete",
            audit_id=cursor.lastrowid, reason_code=VERIFICATION_FAILURE)

    def _attach_evidence(self, work_id: str, audit_id: int, refs: list[str]) -> None:
        conn = self._conn
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM evidence_refs WHERE work_id = ?", (work_id,)
        ).fetchone()[0]
        conn.executemany(
            """INSERT INTO evidence_refs (work_id, seq, audit_id, evidence_id)
               VALUES (?, ?, ?, ?)""",
            [(work_id, seq + i, audit_id, ref) for i, ref in enumerate(refs, start=1)],
        )

