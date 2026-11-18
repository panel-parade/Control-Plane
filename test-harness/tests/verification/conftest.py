"""Make implementation/verification importable as `verification` without packaging."""

import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[3] / "implementation"
if str(_IMPL) not in sys.path:
    sys.path.insert(0, str(_IMPL))
