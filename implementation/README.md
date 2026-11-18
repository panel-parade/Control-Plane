# Implementation

## Stack decision

Python 3.12, pytest, standard library only. Chosen because `test-harness/README.md` and the `implementation/*/README.md` files were empty on `main` and no stack was defined. No packaging metadata is added; tests put `implementation/` on `sys.path` via `test-harness/tests/verification/conftest.py`.

## Layout

- `implementation/verification/`: stream B evidence verification (Evidence-Spec). See its README.
- `implementation/schema/`, `implementation/services/`: stream A (register and state machine). Owned by another stream; this stream has no import dependency on them.
- `test-harness/tests/verification/`: tests for stream B.

Run tests from the repo root:

```
python -m pytest test-harness/tests/verification -q
```
