# Work Register Specification

Status: DRAFT v0.1 — Source: Programme Management Architecture v2.0 (Stage 1–2, Sprint 1)

## 1. Purpose

The Work Register is the single authoritative source of operational truth. Every other component (State Machine, Evidence, Exception Detection, Derived Status) reads from or writes through it. No parallel store of work state may exist.

## 2. Scope

In scope: work item records, audit log, create / assign / query operations.
Out of scope: planning, decomposition, prioritisation, scheduling (deferred Phases A–C).

## 3. Work Item

| Field | Type | Required | Notes |
|---|---|---|---|
| `work_id` | string (immutable) | yes | Unique, never reused. |
| `project_id` | string | yes | Groups work items into a project, e.g. `SEEK`, `SAGE`, `CONTROL-PLANE`. |
| `assigned_to` | string \| null | yes (nullable) | Owner. Null is an Ownership Gap exception, not an invalid record. |
| `state` | enum | yes | One of the states in the State-Machine Spec. Initial: `Assigned`. |
| `done_criterion` | string | yes | Objective, verifiable (see Evidence Spec §6). Non-empty at creation. |
| `item_type` | enum | yes | One of `Decision`, `Validation`, `Execution`, `Observation`, `Exception`. Set at creation and immutable once recorded. Missing or non-type labels (e.g. "Plain Text") are rejected as `TYPE_MISSING`. Legacy rows without a type are flagged, not inferred, until backfilled. |
| `evidence_ref` | string \| null | no | Reference(s) to attached evidence. Required to enter `Claimed Complete`. |
| `last_update_ts` | timestamp (UTC) | yes | Set by the register on every accepted mutation. |
| `required` | boolean | no (default `false`) | Indicates whether the work item contributes to project completion determination. |

Additional fields required by dependent specs (proposed, see Open Questions): `block_reason`, `created_ts`.

## 4. Audit Log

Append-only. One entry per state change.

| Field | Notes |
|---|---|
| `audit_id` | Unique, monotonically ordered. |
| `work_id` | FK to work item. |
| `old_state` | Null for creation. |
| `new_state` | |
| `actor` | Identity performing the change (worker, manager, system, verifier). |
| `timestamp` | UTC, register-assigned. |

Audit entries are never updated or deleted. A state change and its audit entry are written atomically.

## 5. Operations

- **Create** — requires `work_id`, `done_criterion`, `item_type`; state `Assigned`; `assigned_to` may be null. Writes an audit entry (`null → Assigned`).
- **Assign / Reassign** — sets `assigned_to`; updates `last_update_ts`.
- **Query** — by `work_id`, `assigned_to`, `state`, `project_id`, `last_update_ts` range. Read-only, side-effect free.
- **Transition** — only via the State Machine (see State-Machine Spec). Direct writes to `state` are prohibited.

## 6. Invariants

1. `work_id` is unique and immutable.
2. `state` is always a valid enum value.
3. Every `state` change has exactly one audit entry.
4. `last_update_ts` is register-assigned, never client-supplied.
5. Status is never stored on a work item (see Derived-Status Spec, ADR-003).

## 7. Acceptance Criteria (Sprint 1)

- Work items can be created, assigned, queried.
- State changes create audit entries.
- Every work item has an owner (or is flagged as an Ownership Gap), a state, and a done criterion.

## 8. Open Questions

1. Persistence technology — deferred to `implementation/schema`.
2. Should `evidence_ref` be a single reference or a list? Evidence Spec assumes a list of evidence IDs.
3. Do ownership changes require an audit entry? Proposed: yes, via a separate event type.
