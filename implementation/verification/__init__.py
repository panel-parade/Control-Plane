"""Evidence verification (Control Plane v1, stream B).

Public surface:
- evidence: EvidenceRecord, EvidenceType, VerificationResult, VerificationStatus
- validation: parse_reference, validate_record, is_structurally_valid
- external: ExternalSource protocol (adapters not provided in v1)
- checks: Check, verify
- transition: can_claim_complete (T4 gate), attach_evidence, may_complete (T5 gate)

No dependency on implementation/schema or implementation/services.
"""

from .checks import Check, verify
from .evidence import CheckFailure, EvidenceRecord, EvidenceType, VerificationResult, VerificationStatus
from .external import ExternalSource
from .transition import (
    VERIFICATION_FAILURE,
    attach_evidence,
    can_claim_complete,
    failure_exception,
    may_complete,
)
from .validation import InvalidEvidenceError, is_structurally_valid, parse_reference, validate_record

__all__ = [
    "Check",
    "CheckFailure",
    "EvidenceRecord",
    "EvidenceType",
    "ExternalSource",
    "InvalidEvidenceError",
    "VerificationResult",
    "VerificationStatus",
    "attach_evidence",
    "can_claim_complete",
    "is_structurally_valid",
    "may_complete",
    "failure_exception",
    "VERIFICATION_FAILURE",
    "parse_reference",
    "validate_record",
    "verify",
]
