# Evidence verification (stream B)

Implements Evidence-Spec §3 to §6 with no state writes.

## Modules

- `evidence.py`: `EvidenceRecord`, `EvidenceType` (five accepted types), `VerificationResult`, `VerificationStatus` (unverified/pass/fail), `CheckFailure`.
- `external.py`: `ExternalSource` protocol (`commit_exists`, `test_result_passing`, `artifact_exists`, `document_revision_exists`, `tool_execution_outcome`). No real adapter; supply one or a fake.
- `validation.py`: reference parsing. Narrative text such as "Done." is rejected with `InvalidEvidenceError` (code `EVIDENCE_MISSING`).
- `checks.py`: `verify(work_id, evidence, checks, source, checked_ts)`. Evaluates every check, returns `PASS` only if all pass, otherwise `FAIL` with each failing check in `detail`. Deterministic for the same inputs. External errors fail closed.
- `transition.py`: `can_claim_complete` (T4 gate), `attach_evidence` (returns new tuple, no state), `may_complete` (T5 gate, true only on PASS). The state machine performs the transition.

## Assumptions / open-question defaults

| Assumption | Reason | Alternative considered |
|---|---|---|
| Done criteria are typed `Check` objects supplied by the caller; no parsing of free-text criteria. | Spec leaves machine-readable criteria open; typed checks keep verification deterministic. | Parse criteria text. |
| No verifier credentials or real adapters; `ExternalSource` is an interface, tests use fakes. | Credentials are an open question; adapters are not trivial. | Ship a GitHub/CI adapter now. |
| Verification is point-in-time; no stale-evidence handling after Complete. | Stale evidence after Complete is open; the module does not own state. | Re-verify on a schedule. |
| Level 3 attestation is not an evidence type. | Not among the five accepted types. | Add an attestation type. |
| `evidence_ref` is a list of records per work item, not a single ID. | Evidence-Spec assumes a list; Work-Register-Spec §3/§8 says single. Mismatch flagged. | Single reference. |
| Unknown external state or raised exception fails the check (fail-closed). | Prevents false PASS. | Treat as unverified. |
| Zero checks returns FAIL (`NO_CHECKS`). | A pass with no checks would be vacuous. | Pass vacuously. |
| Failed verification leaves the item in Claimed Complete and raises `VERIFICATION_FAILURE` (via `failure_exception`); no Claimed Complete → Active transition. | Preserves the worker's completion claim and the evidence trail; fix by attaching new evidence and re-verifying. | Return to Active. |
| Module returns detail only; raising verification-delay exceptions is left to Exception-Detection. | Keeps this module free of state and scheduling. | Emit exceptions here. |
| Reference formats are chosen here because the spec gives only examples (see `validation.py`). | Needed to implement structural validity. | Wait for a spec. |
