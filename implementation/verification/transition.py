"""Gates the state machine calls for T4 and T5. This module writes no state.

- T4 (Active -> Claimed Complete): `can_claim_complete` needs at least one
  structurally valid evidence record for the work item.
- Attaching evidence (`attach_evidence`) returns a new tuple of records. It
  takes no state argument and has no side effects beyond the returned value.
- T5 (Claimed Complete -> Complete): `may_complete` is true only for a PASS.
"""

from __future__ import annotations

from collections.abc import Sequence

from .evidence import EvidenceRecord, VerificationResult
from .validation import InvalidEvidenceError, is_structurally_valid, validate_record


def can_claim_complete(work_id: str, evidence: Sequence[EvidenceRecord]) -> bool:
    """T4 gate: at least one structurally valid record for this work item."""
    return any(record.work_id == work_id and is_structurally_valid(record) for record in evidence)


def attach_evidence(
    existing: Sequence[EvidenceRecord], record: EvidenceRecord
) -> tuple[EvidenceRecord, ...]:
    """Append-only attach. Raises InvalidEvidenceError on invalid or duplicate records."""
    validate_record(record)
    if any(r.evidence_id == record.evidence_id for r in existing):
        raise InvalidEvidenceError(f"duplicate evidence_id {record.evidence_id!r}")
    return (*existing, record)


def may_complete(result: VerificationResult) -> bool:
    """T5 gate: the verification process may move Claimed Complete -> Complete only on PASS."""
    return result.passed
