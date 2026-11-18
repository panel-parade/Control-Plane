import sys
from pathlib import Path

_IMPLEMENTATION = Path(__file__).resolve().parents[3] / "implementation"
if str(_IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(_IMPLEMENTATION))
