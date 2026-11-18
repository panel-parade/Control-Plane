# Derived Status Specification

Status: DRAFT v0.1 — Source: Programme Management Architecture v2.0 (Stage 5, Sprint 6); see ADR-003

## 1. Purpose

Give the Intent Owner project/programme health at a glance. Status is **derived** from register contents; it is never worker-reported.

## 2. Values

`GREEN`, `AMBER`, `RED`, `COMPLETE`.

## 3. Inputs

Only: work items (state, `required`), exception records, and evaluation time. Nothing else.

## 4. Rules (first match wins)

1. **COMPLETE** — project has ≥1 required item and all required items are `Complete` or `Archived`.
2. **RED** — any open `VERIFICATION_FAILURE`, `OWNERSHIP_GAP`, or `LONG_TERM_BLOCK`.
3. **AMBER** — any other open exception (e.g. `PROGRESS_GAP`), or any item currently `Blocked` below the long-term threshold.
4. **GREEN** — otherwise: work progressing, evidence arriving, no exceptions.

Outcome precedence: product behaviour outranks register state. A Level 3 finding that the product does not meet intent overrides a derived `COMPLETE` (see Evidence Spec, Outcome Validation).

## 5. Programme Roll-Up

Worst of its projects by severity `RED > AMBER > GREEN`; `COMPLETE` only if all projects are `COMPLETE`.

## 6. Properties

- **Deterministic**: same register contents and evaluation time → same status.
- **Pure**: no side effects; workers have no write path to status.
- **Explainable**: result lists the contributing exceptions/items for optional drill-down.

## 7. Acceptance Criteria (Sprint 6)

- Same input always produces the same status.
- Status is generated entirely from register contents.

## 8. Open Questions

1. Definition of "required" work (item flag vs. all items in project).
2. Minor vs. significant exceptions: should an old `PROGRESS_GAP` escalate to RED?
3. Status of an empty / not-started project (proposed GREEN).
4. Should `COMPLETE` also require Level 3 confirmation by the Intent Owner?
5. Is status history retained? Not in v1 source.
