"""Real metadata-only I server: inference routes cannot be reached."""

import argparse
import hashlib
import json
import socket
import sys
from pathlib import Path

from starlette.responses import JSONResponse


def health_application(assembly, *, factory):
    app = factory(
        assembly["manifest"],
        {key: Path(value) for key, value in assembly["files"].items()},
        runtime_root=Path(assembly["runtime_root"]),
        gdino_snapshot_path=Path(assembly["gdino_snapshot_path"]),
        sam_checkpoint_path=Path(assembly["sam_checkpoint_path"]),
    )

    @app.middleware("http")
    async def readonly(request, call_next):
        if request.method != "GET" or request.url.path != "/health/ready":
            return JSONResponse({"code": "MODEL_FREE_ENDPOINT_ONLY"}, status_code=403)
        return await call_next(request)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", required=True)
    parser.add_argument("--assembly-sha256", required=True)
    parser.add_argument("--fd", type=int, required=True)
    args = parser.parse_args()
    blob = Path(args.assembly).read_bytes()
    if hashlib.sha256(blob).hexdigest() != args.assembly_sha256:
        raise SystemExit("ASSEMBLY_MISMATCH")
    with socket.fromfd(args.fd, socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.getsockname()[0] != "127.0.0.1":
            raise SystemExit("LOOPBACK_REQUIRED")
    import uvicorn

    from services.candidate_i.bootstrap import assemble_service

    app = health_application(json.loads(blob), factory=assemble_service)
    print(
        json.dumps(
            {
                "event": "model_free_i_bootstrap",
                "torch_imported": "torch" in sys.modules,
                "transformers_imported": "transformers" in sys.modules,
            }
        ),
        flush=True,
    )
    uvicorn.run(app, fd=args.fd, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
