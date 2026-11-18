# Implementation

## Stack (stream C: exceptions and status)

No stack was defined in `test-harness/README.md` or `implementation/*/README.md`, so this stream uses:

- Python 3.12, standard library only (`dataclasses`, `enum.StrEnum`, `datetime`).
- pytest for tests. Run from the repository root:
  `python -m pytest test-harness/tests/exceptions_status -q`

## Layout

- `implementation/exceptions/`: read-only snapshot types (`types.py`), defaults and per-project overrides (`thresholds.py`), pure detection (`detect.py`), and idempotent reconciliation into the exception ledger (`ledger.py`).
- `implementation/status/`: derived status (`derive.py`). It imports from `exceptions` only and stores nothing (ADR-003).
- `test-harness/tests/exceptions_status/`: `conftest.py` puts `implementation/` on `sys.path`. Tests are split by behaviour.

`exceptions` and `status` are sibling top-level packages under `implementation/`, so imports are absolute (`from exceptions import ...`).

Streams A (`implementation/schema`, `implementation/services`) and B (`implementation/verification`) are not imported or modified here. Inputs arrive as the local mirror types in `implementation/exceptions/types.py`.
