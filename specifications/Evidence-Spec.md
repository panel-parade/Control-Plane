# Evidence Specification

Status: DRAFT v0.1 — Source: Programme Management Architecture v2.0 (Stage 3, Sprints 3–4)

## 1. Purpose

Make work completion objectively verifiable. **Narrative claims are not evidence.**

## 2. Accepted Evidence Types

| Type | Example reference | Verifiable by |
|---|---|---|
| `commit_sha` | SHA + repository | Commit exists on origin |
| `test_result` | Run/job ID | Result retrieved and passing |
| `artifact` | Path/URI + digest | Artifact exists |
| `document_revision` | Doc ID + revision | Revision exists |
| `tool_execution` | Execution record ID | Record exists with expected outcome |

## 3. Evidence Record

| Field | Notes |
|---|---|
| `evidence_id` | Unique. |
| `work_id` | Work item it supports. |
| `type` | One of §2. |
| `reference` | Type-specific locator. |
| `attached_by`, `attached_ts` | Actor and UTC time. |
| `verification_result` | `unverified` \| `pass` \| `fail`, plus detail and checked timestamp. |

Records are append-only and traceable from the work item (`evidence_ref`).

## 4. Rejection of Narrative Claims

Free text without a typed, resolvable reference is rejected. Examples that must be rejected: "Finished.", "Done.", "Should be complete.", "Ready." A T4 claim with no valid evidence is rejected with `EVIDENCE_MISSING`.

## 5. Attachment Rules

- Evidence may be attached while the item is `Active` or `Claimed Complete`.
- Attaching evidence alone does not change state.
- T4 (Active → Claimed Complete) requires at least one structurally valid evidence record.

## 6. Done Criterion & Verification

The `done_criterion` must be expressed as checks that map onto evidence types, e.g.:

> Task: Merge feature branch. Criterion: commit visible on origin AND associated tests pass.
> Checks: commit lookup; test result lookup.

Verification:
1. Triggered automatically on entry to `Claimed Complete`.
2. Runs every check against attached evidence and the external source of truth.
3. All pass → verification process performs T5 (`Complete`).
4. Any fail → state unchanged; Verification Failure exception raised with failing check details.

Verification is deterministic for given evidence and external state.

## 7. Validation Levels

| Level | Description | v1 handling |
|---|---|---|
| 1 | Worker claim | Recorded, never sufficient |
| 2 | System evidence (commit, tests, artifact) | Automated by this spec |
| 3 | Product reality (Intent Owner inspects running product) | Manual, during the operational trial |

## 8. Acceptance Criteria (Sprints 3–4)

- Evidence can be attached, stored, and traced.
- Completion claims require evidence.
- Verification runs automatically; failure generates an exception; success closes the work.

## 9. Open Questions

1. Are `done_criterion` checks machine-readable, or text with manual mapping in the trial?
2. Integrations needed for the trial (GitHub, CI) and who owns verifier credentials.
3. Handling stale evidence after `Complete` (e.g. force-pushed commit).
4. Is Level 3 confirmation an evidence type or a separate attestation?
