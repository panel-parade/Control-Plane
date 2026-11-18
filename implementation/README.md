# Implementation

## Stack (Stream A: Work Register and State Machine)

No stack is defined by the merged `implementation/*/README.md` or `test-harness/README.md` (all empty on `main`), so Stream A uses:

- Python 3.12
- stdlib `sqlite3` for persistence
- pytest for tests (`test-harness/`, run with `python -m pytest` from `test-harness/`)

## Layout

- `schema/`: DDL (`schema.sql`) and connection helpers (`db.py`).
- `services/`: `register.py` (Work Register) and `state_machine.py` (transitions T1-T6).
- `test-harness/tests/register/`: register and state machine tests.
