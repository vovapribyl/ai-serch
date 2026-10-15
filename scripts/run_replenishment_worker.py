"""Use the pinned environment with isolated Python, loading this checkout explicitly."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root)]

from product_search.infrastructure.replenishment_worker_entry import (
    run_guard,
    run_native,
)

if __name__ == "__main__":
    try:
        if len(sys.argv) == 5 and sys.argv[1] == "--guard":
            run_guard(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
        elif len(sys.argv) == 2:
            run_native(Path(sys.argv[1]))
        else:
            raise ValueError
    except Exception:  # noqa: BLE001 -- private source/model paths never reach terminal output.
        sys.stderr.write("WORKER_REFUSED\n")
        raise SystemExit(5) from None
