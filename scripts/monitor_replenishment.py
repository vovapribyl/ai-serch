"""Launch the read-only terminal monitor; no runtime grant required."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root)]

from product_search.infrastructure.replenishment_monitor import main

if __name__ == "__main__":
    raise SystemExit(main())
