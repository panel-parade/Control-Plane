"""Focused tests for stream B evidence verification (Evidence-Spec §2-§6)."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import datetime, timezone

import pytest
from verification import (
    Check,
    EvidenceRecord,
    EvidenceType,
    InvalidEvidenceError,
    VerificationStatus,
    attach_evidence,
    can_claim_complete,
    may_complete,
    validate_record,
    verify,
)
from verification.transition import failure_exception

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
WORK = "W-1"


class FakeSource:
    """In-memory ExternalSource. `errors` names methods that raise."""

    def __init__(self, commits=(), tests_passing=(), tool_outcomes=None, errors=()):
        self.commits = set(commits)
        self.tests_passing = set(tests_passing)
        self.tool_outcomes = dict(tool_outcomes or {})
        self.errors = set(errors)

    def _maybe_raise(self, name):
        if name in self.errors:
            raise ConnectionError(name)

    def commit_exists(self, repository, sha):
        self._maybe_raise("commit_exists")
        return (repository, sha) in self.commits

    def test_result_passing(self, run_id):
        self._maybe_raise("test_result_passing")
        return run_id in self.tests_passing

    def artifact_exists(self, uri, digest):
        return False

    def document_revision_exists(self, doc_id, revision):
        return False

    def tool_execution_outcome(self, execution_id):
        return self.tool_outcomes.get(execution_id)


def record(evidence_id, evidence_type, reference, work_id=WORK):
    return EvidenceRecord(
        evidence_id=evidence_id,
        work_id=work_id,
        type=evidence_type,
        reference=reference,
        attached_by="worker-1",
        attached_ts=NOW,
    )


COMMIT = record("E-1", EvidenceType.COMMIT_SHA, f"panel-parade/Control-Plane@{SHA}")
TESTS = record("E-2", EvidenceType.TEST_RESULT, "run-42")
COMMIT_OK = FakeSource(commits={("panel-parade/Control-Plane", SHA)}, tests_passing={"run-42"})


@pytest.mark.parametrize("text", ["Finished.", "Done.", "Should be complete.", "Ready.", ""])
def test_narrative_claims_are_rejected_as_evidence(text):
    with pytest.raises(InvalidEvidenceError) as exc:
        validate_record(record("E-x", EvidenceType.COMMIT_SHA, text))
    assert exc.value.code == "EVIDENCE_MISSING"


def test_narrative_claim_alone_does_not_satisfy_t4():
    assert can_claim_complete(WORK, [record("E-x", EvidenceType.TEST_RESULT, "Done.")]) is False
    assert can_claim_complete(WORK, []) is False


def test_t4_needs_at_least_one_structurally_valid_record_for_this_work_item():
    assert can_claim_complete(WORK, [COMMIT]) is True
    assert can_claim_complete(WORK, [record("E-3", EvidenceType.TEST_RESULT, "run-9", work_id="W-2")]) is False


@pytest.mark.parametrize(
    "evidence_type, reference",
    [
        (EvidenceType.COMMIT_SHA, "panel-parade/Control-Plane@xyz"),
        (EvidenceType.COMMIT_SHA, "no-slash@" + SHA),
        (EvidenceType.TEST_RESULT, "has space"),
        (EvidenceType.ARTIFACT, "s3://bucket/a.tar"),
        (EvidenceType.DOCUMENT_REVISION, "doc-without-revision"),
        (EvidenceType.TOOL_EXECUTION, ""),
    ],
)
def test_structurally_invalid_references_are_rejected(evidence_type, reference):
    with pytest.raises(InvalidEvidenceError):
        validate_record(record("E-x", evidence_type, reference))


def test_attach_returns_new_records_and_takes_no_state():
    existing = (COMMIT,)
    updated = attach_evidence(existing, TESTS)
    assert updated == (COMMIT, TESTS)
    assert existing == (COMMIT,)
    assert list(inspect.signature(attach_evidence).parameters) == ["existing", "record"]


def test_attach_rejects_duplicate_and_invalid_records():
    with pytest.raises(InvalidEvidenceError):
        attach_evidence((COMMIT,), dataclasses.replace(TESTS, evidence_id="E-1"))
    with pytest.raises(InvalidEvidenceError):
        attach_evidence((), record("E-9", EvidenceType.TEST_RESULT, "Finished."))


def test_all_checks_pass_returns_pass():
    result = verify(WORK, [COMMIT, TESTS], [Check("E-1"), Check("E-2")], COMMIT_OK, NOW)
    assert result.status is VerificationStatus.PASS
    assert result.detail == ()
    assert result.checked_ts == NOW
    assert may_complete(result) is True


def test_failed_verification_keeps_item_claimed_complete_and_raises_verification_failure():
    source = FakeSource(commits={("panel-parade/Control-Plane", SHA)})
    result = verify(WORK, [COMMIT, TESTS], [Check("E-1"), Check("E-2")], source, NOW)
    assert failure_exception(result) == "VERIFICATION_FAILURE"
    assert failure_exception(verify(WORK, [COMMIT], [Check("E-1")], COMMIT_OK, NOW)) is None


def test_failed_check_returns_fail_with_failing_check_detail():
    source = FakeSource(commits={("panel-parade/Control-Plane", SHA)})
    result = verify(WORK, [COMMIT, TESTS], [Check("E-1"), Check("E-2")], source, NOW)
    assert result.status is VerificationStatus.FAIL
    assert may_complete(result) is False
    assert [(f.evidence_id, f.type, f.reason) for f in result.detail] == [
        ("E-2", EvidenceType.TEST_RESULT, "TEST_RESULT_NOT_PASSING"),
    ]


def test_missing_evidence_record_is_a_failed_check():
    result = verify(WORK, [COMMIT], [Check("E-1"), Check("E-2")], COMMIT_OK, NOW)
    assert result.status is VerificationStatus.FAIL
    assert (result.detail[0].evidence_id, result.detail[0].reason) == ("E-2", "EVIDENCE_NOT_FOUND")


def test_external_error_fails_closed():
    source = FakeSource(commits={("panel-parade/Control-Plane", SHA)}, errors={"test_result_passing"})
    result = verify(WORK, [COMMIT, TESTS], [Check("E-1"), Check("E-2")], source, NOW)
    assert result.status is VerificationStatus.FAIL
    assert result.detail[0].reason == "EXTERNAL_CHECK_ERROR: ConnectionError"


def test_no_checks_fails():
    result = verify(WORK, [COMMIT], [], COMMIT_OK, NOW)
    assert result.status is VerificationStatus.FAIL
    assert result.detail[0].reason == "NO_CHECKS"


def test_tool_execution_requires_matching_expected_outcome():
    tool = record("E-5", EvidenceType.TOOL_EXECUTION, "exec-7")
    source = FakeSource(tool_outcomes={"exec-7": "success"})
    ok = verify(WORK, [tool], [Check("E-5", expected_outcome="success")], source, NOW)
    bad = verify(WORK, [tool], [Check("E-5", expected_outcome="failure")], source, NOW)
    missing = verify(WORK, [tool], [Check("E-5")], source, NOW)
    assert ok.status is VerificationStatus.PASS
    assert bad.detail[0].reason.startswith("OUTCOME_MISMATCH")
    assert missing.detail[0].reason == "EXPECTED_OUTCOME_MISSING"


def test_verification_is_deterministic_for_same_evidence_and_external_state():
    checks = [Check("E-1"), Check("E-2")]
    first = verify(WORK, [COMMIT, TESTS], checks, COMMIT_OK, NOW)
    second = verify(WORK, [COMMIT, TESTS], checks, COMMIT_OK, NOW)
    assert first == second


def test_verify_does_not_mutate_inputs():
    evidence = (COMMIT, TESTS)
    checks = (Check("E-1"), Check("E-2"))
    verify(WORK, evidence, checks, COMMIT_OK, NOW)
    assert evidence == (COMMIT, TESTS)
    assert checks == (Check("E-1"), Check("E-2"))


def test_record_from_other_work_item_is_a_failed_check():
    foreign = record("E-1", EvidenceType.COMMIT_SHA, f"panel-parade/Control-Plane@{SHA}", work_id="W-2")
    result = verify(WORK, [foreign], [Check("E-1")], COMMIT_OK, NOW)
    assert result.detail[0].reason == "WORK_ID_MISMATCH"
