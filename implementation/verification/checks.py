"""Done-criterion checks and the verification process (Evidence-Spec §6).

Verification is a pure function of (work_id, evidence, checks, external state,
checked_ts). It never writes state; the caller decides what to do with the
result (see transition.py).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from .evidence import CheckFailure, EvidenceRecord, EvidenceType, VerificationResult, VerificationStatus
from .external import ExternalSource
from .validation import InvalidEvidenceError, ParsedReference, validate_record


@dataclass(frozen=True)
class Check:
    """One done-criterion check: verify the evidence record `evidence_id`.

    The check kind is taken from the record's type. `expected_outcome` is
    required for `tool_execution` checks ("record exists with expected outcome").
    """

    evidence_id: str
    expected_outcome: str | None = None


def verify(
    work_id: str,
    evidence: Sequence[EvidenceRecord],
    checks: Sequence[Check],
    source: ExternalSource,
    checked_ts: datetime,
) -> VerificationResult:
    """Run every check. All pass -> PASS; any fail -> FAIL with every failing check.

    Every check is evaluated (no short-circuit) so the failure detail is complete
    and the result does not depend on evaluation order beyond `checks` order.
    """
    if not checks:
        return VerificationResult(
            VerificationStatus.FAIL, checked_ts, (CheckFailure("", None, "NO_CHECKS"),)
        )

    duplicates = {eid for eid, n in Counter(r.evidence_id for r in evidence).items() if n > 1}
    by_id = {r.evidence_id: r for r in evidence}
    failures: list[CheckFailure] = []

    for check in checks:
        record = by_id.get(check.evidence_id)
        if record is None:
            failures.append(CheckFailure(check.evidence_id, None, "EVIDENCE_NOT_FOUND"))
            continue
        if check.evidence_id in duplicates:
            failures.append(CheckFailure(record.evidence_id, record.type, "DUPLICATE_EVIDENCE_ID"))
            continue
        if record.work_id != work_id:
            failures.append(CheckFailure(record.evidence_id, record.type, "WORK_ID_MISMATCH"))
            continue
        try:
            parsed = validate_record(record)
        except InvalidEvidenceError as exc:
            failures.append(CheckFailure(record.evidence_id, record.type, f"INVALID_EVIDENCE: {exc}"))
            continue
        reason = _run_external_check(parsed, check, source)
        if reason is not None:
            failures.append(CheckFailure(record.evidence_id, record.type, reason))

    if failures:
        return VerificationResult(VerificationStatus.FAIL, checked_ts, tuple(failures))
    return VerificationResult(VerificationStatus.PASS, checked_ts, ())


def _run_external_check(parsed: ParsedReference, check: Check, source: ExternalSource) -> str | None:
    """Return None if the check passes, otherwise a failure reason. Fail-closed on errors."""
    kind = parsed.type
    p = parsed.parts
    try:
        if kind is EvidenceType.COMMIT_SHA:
            ok = source.commit_exists(p["repo"], p["ref"])
            return None if ok else "COMMIT_NOT_FOUND"
        if kind is EvidenceType.TEST_RESULT:
            ok = source.test_result_passing(p["ref"])
            return None if ok else "TEST_RESULT_NOT_PASSING"
        if kind is EvidenceType.ARTIFACT:
            ok = source.artifact_exists(p["uri"], p["ref"])
            return None if ok else "ARTIFACT_NOT_FOUND"
        if kind is EvidenceType.DOCUMENT_REVISION:
            ok = source.document_revision_exists(p["doc"], p["ref"])
            return None if ok else "DOCUMENT_REVISION_NOT_FOUND"
        if kind is EvidenceType.TOOL_EXECUTION:
            if check.expected_outcome is None:
                return "EXPECTED_OUTCOME_MISSING"
            outcome = source.tool_execution_outcome(p["ref"])
            if outcome is None:
                return "TOOL_EXECUTION_NOT_FOUND"
            return None if outcome == check.expected_outcome else f"OUTCOME_MISMATCH: got {outcome!r}"
    except Exception as exc:  # fail-closed: unknown external state is not a pass
        return f"EXTERNAL_CHECK_ERROR: {type(exc).__name__}"
    return "UNKNOWN_EVIDENCE_TYPE"
