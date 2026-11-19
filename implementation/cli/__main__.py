"""Entry point. Run from the repository root: python implementation/cli <command> ...

Also runnable as python -m cli from implementation/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
