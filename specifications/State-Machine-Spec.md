# State Machine Specification

Status: DRAFT
v0.2 — Source: Programme Management Architecture v2.0 (Stage 1, Sprint 2). v0.2 amends v0.1 to add a legal Intent Owner decision path from `Assigned` (CP-02, Control-Plane #28; proposal #31).

## 1. Purpose

Define the formal lifecycle of a work item, the legal transitions, who may perform each, and what evidence each requires. Illegal transitions are rejected.

## 2. States

| State | Meaning |
|---|---|
| `Assigned` | Created/assigned; work not yet started. Initial state for all items. |
| `Active` | Worker has started; activity recorded. |
| `Blocked` | Worker cannot proceed; block reason recorded. |
| `Claimed Complete` | Claim of completion with attached evidence. Not yet verified. For decision items, the Intent Owner decision has been recorded. For execution items, the assigned work has been delivered. |
| `Complete` | Done criterion verified. |
| `Archived` | Closed out; terminal. |

## 3. Transition Table

| # | From | To | Trigger | Actor | Required Evidence |
|---|---|---|---|---|---|
| T1 | Assigned | Active | Worker starts work | Worker | Activity recorded |
| T2 | Active | Blocked | Worker cannot proceed | Worker | Block reason |
| T3 | Blocked | Active | Blocker removed | Worker / Manager | Block resolved |
| T4 | Active | Claimed Complete | Worker claims done | Worker | Evidence reference |
| T5 | Claimed Complete | Complete | Verification passes | Verification process | Done criterion satisfied |
| T6 | Complete | Archived | Closure rule met | Manager / System | Closure rule |
| T7 | Assigned | Claimed Complete | Intent Owner records a decision on a decision item | Intent Owner | Decision recorded |

Any transition not listed is illegal and must be rejected without mutating the register.

```mermaid
stateDiagram-v2
    [*] --> Assigned
    Assigned --> Active: T1
    Assigned --> ClaimedComplete: T7 decision recorded (Intent Owner)

    Active --> Blocked: T2
    Blocked --> Active: T3
    Active --> ClaimedComplete: T4

    ClaimedComplete --> Complete: T5 verified

    Complete --> Archived: T6
    Archived --> [*]
```

## 4. Rules

1. Only the listed actors may perform a transition; actor identity is recorded in the audit log.
2. Only the verification process may produce `Complete`. Workers, managers and the Intent Owner cannot set it directly. T7 does not set `Complete`; T5 verification still applies.
3. A failed verification does **not** change state: the item stays in `Claimed Complete` and a Verification Failure exception is raised (Exception-Detection Spec).
4. Every accepted transition writes one audit entry atomically with the state change and updates `last_update_ts`.
5. `Archived` is terminal.
6. T7 is the only transition that bypasses Worker activity. It is restricted to the Intent Owner and requires a recorded decision. `Assigned` remains the universal initial state; T7 is an exit from it, not a new initial state. The meaning of `Claimed Complete` depends on item type: for decision items it means the required Intent Owner decision has been recorded; for execution items it means the assigned work has been delivered.

## 5. Transition Request Contract

Input: `work_id`, `to_state`, `actor`, `evidence` (per table). Output: accepted (new state + audit_id) or rejected (reason code: `ILLEGAL_TRANSITION`, `ACTOR_NOT_PERMITTED`, `EVIDENCE_MISSING`, `NOT_FOUND`). Rejections do not mutate the register.

For T7, `ACTOR_NOT_PERMITTED` is returned when the actor is not the Intent Owner, and `EVIDENCE_MISSING` when no decision record is supplied. Requests that name a non-decision item are rejected as `ILLEGAL_TRANSITION`.

## 6. Acceptance Criteria (Sprint 2)

- Illegal transitions are rejected.
- Valid transitions are accepted.
- All transitions are audited.
- T7 is accepted only for the Intent Owner with a recorded decision, and is rejected otherwise.

## 7. Open Questions

1. How does a `Claimed Complete` item recover after failed verification (e.g. `Claimed Complete → Active`)? Not in source; proposed as an addition.
2. Definition of the T6 "closure rule".
3. What counts as "Activity recorded" for T1?
4. Should T1 be rejected when `assigned_to` is null? Proposed: yes.
5. Should rejected transitions be logged separately?
6. How are decision items distinguished from execution items in the register? Rule 6 depends on this; proposed: a item-type field. Until it exists, type is inferred from the done criterion.
