# Exception Detection Specification

Status: DRAFT v0.1 — Source: Programme Management Architecture v2.0 (Stage 4, Sprint 5)

## 1. Purpose

Surface operational problems automatically from register data so no one has to watch workers.

## 2. Exception Types

| Type | Condition | Source |
|---|---|---|
| `OWNERSHIP_GAP` | `assigned_to` is null on a non-terminal item | `assigned_to` |
| `PROGRESS_GAP` | Item in `Assigned`/`Active` with no update beyond threshold | `last_update_ts`, `state` |
| `VERIFICATION_FAILURE` | Done criterion not satisfied | Evidence verification result |
| `LONG_TERM_BLOCK` | Item `Blocked` beyond threshold | audit log (time entered Blocked) |

### Default thresholds

Defaults are intentionally aggressive: Control Plane v1 assumes an autonomous worker environment where many work items complete in minutes rather than hours. Projects may override any default.

| Threshold | Default | Human-Dependent Work |
|---|---|---|
| `ownership_gap` | immediate | immediate |
| `progress_gap` | 10m | 1h |
| `verification_delay` | 5m | — |
| `long_term_block` | 30m | 24h |

`verification_delay` is the maximum time an item may sit in `Claimed Complete` awaiting verification before raising a `VERIFICATION_FAILURE`. Human-dependent work is work whose progress depends on a human; how it is flagged on a work item is an open question.

## 3. Exception Record

| Field | Notes |
|---|---|
| `exception_id` | Unique. |
| `work_id` / `project_id` | Affected item and project. |
| `type` | §2. |
| `detected_ts` | UTC. |
| `responder` | `Manager` or `IntentOwner`. |
| `status` | `open` \| `resolved`, with `resolved_ts`. |
| `detail` | Cause (threshold, failing check). |

## 4. Detection Behaviour

- Periodic, read-only evaluation of the register, plus event-triggered for verification failure.
- Idempotent: one open exception per (`work_id`, `type`).
- Auto-resolves when the condition clears; resolution is recorded, not deleted.
- Detection never mutates work item state.

## 5. Responders

| Responder | Handles |
|---|---|
| Manager Layer (primary) — Control Plane operational handling | Ownership, progress, verification |
| Intent Owner (escalation only) | Project blocked beyond threshold; authority boundary reached; strategic intervention required |

`LONG_TERM_BLOCK` goes to the Manager first and escalates to the Intent Owner when the project is blocked beyond threshold. Authority-boundary and strategic-decision escalations are raised explicitly by the Manager.

## 6. Acceptance Criteria (Sprint 5)

- Exceptions detected automatically.
- Exceptions recorded.
- Exceptions assigned to a responder.

## 7. Open Questions

1. How is an item flagged as human-dependent (per item, per project)?
2. Notification channel (belongs in `implementation/exceptions`).
3. Definition of "project blocked" for escalation.
4. Should `PROGRESS_GAP` apply to `Claimed Complete` items awaiting verification?
5. "Missed handoffs" has no dedicated exception type; is `OWNERSHIP_GAP` sufficient?
