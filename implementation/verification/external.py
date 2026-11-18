"""Narrow interface to the external source of truth used by verification.

Implementations are adapters to GitHub, CI, artifact stores, document stores
and tool-execution logs. None are provided in v1 (Evidence-Spec §9.2: verifier
credentials are unresolved). Tests use fakes.

Contract: each method returns a definite answer. Implementations that cannot
determine the answer should raise; the checks treat any exception as a failed
check (fail-closed).
"""

from __future__ import annotations

from typing import Protocol


class ExternalSource(Protocol):
    def commit_exists(self, repository: str, sha: str) -> bool:
        """True if the commit is visible on origin."""

    def test_result_passing(self, run_id: str) -> bool:
        """True if the test run/job exists and its result is passing."""

    def artifact_exists(self, uri: str, digest: str) -> bool:
        """True if the artifact exists and its digest matches."""

    def document_revision_exists(self, doc_id: str, revision: str) -> bool:
        """True if the document revision exists."""

    def tool_execution_outcome(self, execution_id: str) -> str | None:
        """Return the recorded outcome for an execution, or None if absent."""
