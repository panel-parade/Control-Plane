# ADR-004: Required Work

Status: Accepted

## Context
Project completion is derived from register contents (ADR-003). Ancillary work items must not block completion.

## Decision
Work items are not completion-gating unless explicitly marked `required`.

## Reason
Prevents ancillary work from blocking project completion and keeps roll-up behaviour deterministic.

See `specifications/Work-Register-Spec.md` and `specifications/Derived-Status-Spec.md`.
