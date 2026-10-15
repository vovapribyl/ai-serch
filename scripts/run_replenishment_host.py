"""Explicit private native-host launch; permission proposals are refused."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root)]

from product_search.infrastructure.replenishment_cli import private_json
from product_search.infrastructure.replenishment_host import run_native_host

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError
        run_native_host(private_json(sys.argv[1]))
    except Exception:  # noqa: BLE001 -- keep paths/credentials/input metadata private.
        sys.stderr.write("HOST_REFUSED\n")
        raise SystemExit(5) from None
