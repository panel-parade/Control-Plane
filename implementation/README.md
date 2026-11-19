# Implementation

## Stack

No stack is defined by `test-harness/README.md` or `implementation/*/README.md`, so the streams use Python 3.12 and pytest. Stream A uses stdlib `sqlite3` for persistence. Stream C uses stdlib only.

Run tests from the repository root:

- Stream A: `python -m pytest test-harness/tests/register -q`
- Stream C: `python -m pytest test-harness/tests/exceptions_status -q`
- Vertical slice CLI: `python -m pytest test-harness/tests/vertical_slice -q` (see `implementation/cli/README.md`)

## Layout

### Stream A: Work Register and State Machine

- `schema/`: DDL (`schema.sql`) and connection helpers (`db.py`).
- `services/`: `register.py` (Work Register), `state_machine.py` (transitions T1-T6) and `observations.py` (Observation Registry, v1.1 Phases A and B; spec in `specifications/Observation-Registry-Spec.md`).
- `test-harness/tests/register/`: register and state machine tests.
- `test-harness/tests/observations/`: Observation Registry tests. Run with `python -m pytest test-harness/tests/observations -q`.

### Stream C: Exception Detection and Derived Status

- `exceptions/`: read-only snapshot types (`types.py`), defaults and per-project overrides (`thresholds.py`), pure detection (`detect.py`), and idempotent reconciliation into the exception ledger (`ledger.py`).
- `status/`: derived status (`derive.py`). It imports from `exceptions` only and stores nothing (ADR-003).
- `test-harness/tests/exceptions_status/`: `conftest.py` puts `implementation/` on `sys.path`.

`exceptions` and `status` are sibling top-level packages under `implementation/`, so imports are absolute (`from exceptions import ...`). Stream C does not import from `schema/`, `services/` or `verification/`. Its inputs arrive as the local mirror types in `implementation/exceptions/types.py`.

### Stream B: Evidence Verification

- `verification/`: evidence verification (Evidence-Spec), see its README.
- `test-harness/tests/verification/`: tests. Run with `python -m pytest test-harness/tests/verification -q`.
