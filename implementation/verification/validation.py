"""Structural validation of evidence references (Evidence-Spec §2, §4).

Reference shapes (v1, chosen here; the spec only gives examples):
- commit_sha:          "<owner>/<repo>@<sha>", sha 7-40 lowercase hex
- test_result:         "<run_id>", non-empty, [A-Za-z0-9._:-]{1,128}
- artifact:            "<uri>@sha256:<64 lowercase hex>"
- document_revision:   "<doc_id>@<revision>", both non-empty, no whitespace
- tool_execution:      "<execution_id>", non-empty, [A-Za-z0-9._:-]{1,128}

Free text such as "Done." or "Ready." matches none of these and is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .evidence import EvidenceRecord, EvidenceType


class InvalidEvidenceError(ValueError):
    """Raised for narrative or structurally invalid evidence (EVIDENCE_MISSING)."""

    code = "EVIDENCE_MISSING"


# Opaque IDs: 1-128 chars, no trailing dot, and at least one digit or ":_-" so plain prose ("Done.", "Ready") is rejected.
_ID = r"(?=.{1,128}$)(?!.*\.$)(?=.*[0-9:_-])[A-Za-z0-9._:-]+"
_PATTERNS: dict[EvidenceType, re.Pattern[str]] = {
    EvidenceType.COMMIT_SHA: re.compile(r"^(?P<repo>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)@(?P<ref>[0-9a-f]{7,40})$"),
    EvidenceType.TEST_RESULT: re.compile(rf"^(?P<ref>{_ID})$"),
    EvidenceType.ARTIFACT: re.compile(r"^(?P<uri>\S+)@sha256:(?P<ref>[0-9a-f]{64})$"),
    EvidenceType.DOCUMENT_REVISION: re.compile(r"^(?P<doc>\S+)@(?P<ref>\S+)$"),
    EvidenceType.TOOL_EXECUTION: re.compile(rf"^(?P<ref>{_ID})$"),
}


@dataclass(frozen=True)
class ParsedReference:
    type: EvidenceType
    parts: dict[str, str]


def parse_reference(evidence_type: EvidenceType, reference: str) -> ParsedReference:
    """Return the typed parts of a reference, or raise InvalidEvidenceError."""
    if not isinstance(reference, str):
        raise InvalidEvidenceError("reference must be a string")
    match = _PATTERNS[evidence_type].match(reference.strip())
    if match is None or reference != reference.strip():
        raise InvalidEvidenceError(
            f"{evidence_type.value} reference {reference!r} is not a typed, resolvable reference"
        )
    return ParsedReference(evidence_type, match.groupdict())


def validate_record(record: EvidenceRecord) -> ParsedReference:
    """Structural validity of one record. Raises InvalidEvidenceError."""
    if not isinstance(record.type, EvidenceType):
        raise InvalidEvidenceError(f"unknown evidence type {record.type!r}")
    if not record.evidence_id or not record.work_id:
        raise InvalidEvidenceError("evidence_id and work_id are required")
    if not record.attached_by:
        raise InvalidEvidenceError("attached_by is required")
    if record.attached_ts.tzinfo is None:
        raise InvalidEvidenceError("attached_ts must be timezone-aware UTC")
    return parse_reference(record.type, record.reference)


def is_structurally_valid(record: EvidenceRecord) -> bool:
    try:
        validate_record(record)
    except InvalidEvidenceError:
        return False
    return True
