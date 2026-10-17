"""Read a private export and its deferred-photo list; no processing or database access."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root)]

from product_search.infrastructure.replenishment_deferred_photos import main

if __name__ == "__main__":
    raise SystemExit(main())
