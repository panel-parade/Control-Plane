# Observation Registry Specification

Status: DRAFT v0.1 — Control Plane v1.1 Candidate (leading) — Source: panel-parade/Control-Plane#29

## 1. Purpose

Give the Control Plane memory of what has been learned, so that findings are surfaced during later investigations instead of being rediscovered. Work items record what must be completed. Observations record what was learned. The two are linked but kept separate.

Trial 1 finding: the system needs memory of observations, not more intelligence. Most repeated investigations (PO-03 looping) occurred because earlier findings were not surfaced.

## 2. Scope

In scope: observation records, resolution, query by work item, Pre-Investigation Check, re-investigation limit.
Out of scope: any State Machine change, planner, DCRR, optimisation, scheduling, ranking, automatic blocking, automatic duplicate merging, new intelligence layers.

## 3. Observation Record

| Field | Type | Required | Notes |
|---|---|---|---|
| `observation_id` | string (immutable) | yes | Unique, never reused. |
| `project_id` | string | yes | Same vocabulary as Work-Register-Spec §3. |
| `work_id` | string | no | Affected work item. Null for project-level observations. |
| `kind` | enum | yes | One of §4. |
| `detail` | string | yes | Non-empty. Free text is permitted here because the observation is not a completion claim (see Evidence-Spec §4). |
| `reference` | string | no | Typed locator where one exists (commit SHA, run ID, spec section). |
| `recorded_by` | string | yes | Actor identity. |
| `recorded_ts` | timestamp (UTC) | yes | Register-assigned. |
| `status` | enum | yes | `open` \| `resolved`. Initial: `open`. |
| `resolved_by` | string | no | Required when `status` = `resolved`. |
| `resolved_ts` | timestamp (UTC) | no | Required when `status` = `resolved`. |

## 4. Observation Kinds and Resolution Authority

| Kind | Category | Resolved by |
|---|---|---|
| `missing_artefact` | Operational | Manager Layer |
| `duplicate_detected` | Operational | Manager Layer |
| `stale_reference` | Operational | Manager Layer |
| `verification_issue` | Operational | Manager Layer |
| `reproduction_issue` | Operational | Manager Layer |
| `spec_gap` | Operational | Manager Layer |
| `decision` | Governance | Intent Owner |
| `validation` | Governance | Intent Owner |
| `policy` | Governance | Intent Owner |
| `authority` | Governance | Intent Owner |
| `ratification` | Governance | Intent Owner |
| `strategic_direction` | Governance | Intent Owner |

Notes:
- `decision` and `validation` are governance kinds per the Intent Owner split in #29. Revisit only with trial data.
- `spec_gap` is accepted as a Manager Layer kind. It records CP-03 (missing spec artefacts).

## 5. Invariants

1. Observations are append-only. Records are never updated in place except for the `status`, `resolved_by`, and `resolved_ts` transition, and never deleted.
2. Resolution is recorded, not deleted. A resolved observation remains queryable.
3. Recording or resolving an observation never changes any work item's `state`, and never writes to the Work Register audit log.
4. `work_id`, when present, must reference an existing work item. Observations are not orphaned from the register.
5. `recorded_ts` and `resolved_ts` are register-assigned, never client-supplied.
6. Each `resolved_by` must hold the resolution authority for the observation's `kind` (§4).

## 6. Operations

- **Record** — requires `project_id`, `kind`, `detail`, `recorded_by`. Optional `work_id`, `reference`. Status `open`.
- **Resolve** — requires `observation_id`, `resolved_by`. Authorised per §4. Sets `resolved_ts`.
- **Query** — by `work_id`, `project_id`, `kind`, `status`. Read-only, side-effect free.
- **Query for work item** — returns all observations for a `work_id` in a single query, open and resolved, so that observations are discoverable from the affected work item without a separate search (#29 acceptance criterion).

## 7. Pre-Investigation Check

Runs before any investigation or re-investigation. Read-only. In this order:

1. **Existing observations.** Query observations for the `work_id` and the trigger's `kind`. If an open observation already records the same finding, do not investigate. Record the reason as an observation.
2. **New evidence.** Check whether evidence has been attached since the last investigation (Evidence-Spec §3, `attached_ts`). If not, do not investigate.
3. **Trigger still valid.** Confirm the triggering condition still holds (e.g. the stale reference still differs from its source of truth; the failure is still unreproduced; the duplicate is still open). If not, do not investigate.

If any check blocks, no investigation is created and the reason is recorded as an observation of the trigger's kind. The check does not score, rank, or prioritise.

## 8. Re-investigation Limit

- Default: 2 per work item. Configurable per project.
- Meaning: one initial investigation, plus one confirmation investigation.
- Counted from re-investigation records, not from `state`.
- On reaching the limit, raise an escalation to the Intent Owner (Exception-Detection-Spec §5). Do not re-investigate automatically after that.
- Idempotent: at most one open re-investigation per (`work_id`, trigger).

## 9. Relationship to Other Specs

- **Work Register**: observations reference work items by `work_id`. Work-Register-Spec §2 scope is unchanged.
- **Exception Detection**: exceptions remain the mechanism for operational problems that need a responder. Observations record what was learned; they are not a second exception store. Whether an observation raises an exception is an open question (§11).
- **Evidence**: observation `reference` values use the typed references of Evidence-Spec §2 where applicable.
- **State Machine**: unchanged.

## 10. Acceptance Criteria

- Observations can be recorded, queried by `project_id`, `kind`, and `status`, and resolved without deletion.
- Recording an observation leaves every work item's `state` and audit log unchanged.
- An observation is discoverable from its affected work item in a single query.
- The Pre-Investigation Check blocks investigation when an existing observation covers the finding, when no new evidence exists, or when the trigger no longer holds, and records the reason.
- The Pre-Investigation Check blocks a duplicate re-investigation for the same (`work_id`, trigger).
- A third investigation is blocked and escalates to the Intent Owner.
- The limit is 2 by default and can be overridden per project.
- `resolved_by` is validated against the authority in §4.

### 10.1 Future Acceptance Criteria

- Given a work item, the latest open observations are displayed before any investigation begins.

## 11. Open Questions

1. Resolved: `decision` and `validation` remain governance kinds (Intent Owner). Revisit only with trial data.
2. Should a `kind` vocabulary be fixed in v1.1, or extensible per project?
3. Does recording an observation of an operational kind ever raise an exception (Exception-Detection-Spec §2)? Proposed: no in v1.1.
4. How is "new evidence" detected in the Pre-Investigation Check when evidence is attached without a timestamp (Evidence-Spec §3 requires `attached_ts`, so this is expected to be resolved)?
5. Resolved: `spec_gap` is accepted as a Manager Layer kind.
6. What is the trigger vocabulary for re-investigation (§7 step 3)?
7. Where does per-project configuration of the limit live?

## 12. Trial Evidence Required

- Observation counts by `kind`.
- Pre-Investigation Check outcomes, with block reasons.
- Items reaching the re-investigation limit.
- Any case requiring a lifecycle change. This is the only evidence that would justify revisiting the State Machine.
