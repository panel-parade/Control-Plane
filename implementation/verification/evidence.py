"""Evidence records and verification results (Evidence-Spec §2, §3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EvidenceType(str, Enum):
    COMMIT_SHA = "commit_sha"
    TEST_RESULT = "test_result"
    ARTIFACT = "artifact"
    DOCUMENT_REVISION = "document_revision"
    TOOL_EXECUTION = "tool_execution"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class EvidenceRecord:
    """Append-only evidence record (Evidence-Spec §3).

    `reference` is a type-specific locator; see validation.py for its shape.
    """

    evidence_id: str
    work_id: str
    type: EvidenceType
    reference: str
    attached_by: str
    attached_ts: datetime


@dataclass(frozen=True)
class CheckFailure:
    evidence_id: str
    type: EvidenceType
    reason: str


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    checked_ts: datetime | None
    detail: tuple[CheckFailure, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.status is VerificationStatus.PASS


UNVERIFIED = VerificationResult(VerificationStatus.UNVERIFIED, None)
