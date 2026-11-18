# ADR-003: Status Is Derived, Not Reported

Status: Proposed

## Context
Observed failures include stale status and false completion claims. Worker-reported status is subjective and drifts from reality.

## Decision
Project and programme status (GREEN / AMBER / RED / COMPLETE) is computed solely from Work Register contents and exceptions. Workers have no write path to status.

## Consequences
- Same register contents always yield the same status; it is auditable.
- Status quality depends on register and evidence quality.
- The Intent Owner sees only derived status in normal operation.

See `specifications/Derived-Status-Spec.md`.
