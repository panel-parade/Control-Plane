"""Control Plane v1 State Machine: the only path that may change work item state.

See specifications/State-Machine-Spec.md (T1-T6) and Evidence-Spec §5.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional, Union

from services.register import STATES, utc_now

ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
ACTOR_NOT_PERMITTED = "ACTOR_NOT_PERMITTED"
EVIDENCE_MISSING = "EVIDENCE_MISSING"
NOT_FOUND = "NOT_FOUND"

ROLES = ("worker", "manager", "system", "verifier")

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


# T1-T6 from State-Machine-Spec §3. Any (from, to) pair not listed is ILLEGAL_TRANSITION.
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
            "SELECT state, assigned_to FROM work_items WHERE work_id = ?", (work_id,)
        ).fetchone()
        if row is None:
            return _reject(work_id, NOT_FOUND, f"work item {work_id!r} does not exist")

        from_state = row["state"]
        rule = TRANSITIONS.get((from_state, to_state))
        if to_state not in STATES or rule is None:
            return _reject(
                work_id, ILLEGAL_TRANSITION, f"{from_state!r} -> {to_state!r} is not in T1-T6")

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
        block_reason_sql = "block_reason"
        evidence_ref_sql = "evidence_ref"
        params: list[object] = []
        if rule.tid == "T2":
            block_reason_sql = "?"
            params.append(refs[0])
        elif rule.tid == "T3":
            block_reason_sql = "NULL"
        if rule.tid == "T4":
            evidence_ref_sql = "?"
            params.append("\n".join(refs))

        conn.execute("UPDATE register_guard SET allow_state_write = 1 WHERE id = 1")
        try:
            conn.execute(
                f"""UPDATE work_items
                    SET state = ?, block_reason = {block_reason_sql},
                        evidence_ref = {evidence_ref_sql}, last_update_ts = ?
                    WHERE work_id = ?""",
                [to_state, *params, now, work_id],
            )
        finally:
            conn.execute("UPDATE register_guard SET allow_state_write = 0 WHERE id = 1")

        cursor = conn.execute(
            """INSERT INTO audit_log
               (work_id, event_type, old_state, new_state, actor, timestamp)
               VALUES (?, 'TRANSITION', ?, ?, ?, ?)""",
            (work_id, from_state, to_state, actor.identity, now),
        )
        return TransitionResult(
            accepted=True, work_id=work_id, new_state=to_state, audit_id=cursor.lastrowid)
