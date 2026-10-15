"""Model-free external runtime identity; bootstrap supplies the approved manifest."""

import hashlib
import json
import re


class VerifiedReadiness:
    """Revalidate actual files and observations; never load or import a model.

    The manifest is produced outside the service from the approved bill. This checks
    identity, not model compatibility. Runtime observers must report the configured
    device/dtype and actual Python/platform/fallback state, not values from a request.
    """

    def __init__(self, manifest, files, *, observe_inventory, observe_vcs, observe_runtime):
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        expected = json.loads(encoded)
        if (
            set(expected) != {"files", "packages", "vcs", "runtime"}
            or set(expected["files"]) != set(files)
            or not {"contract", "lock", "config", "runtime_profile"} <= expected["files"].keys()
            or not any(name.startswith("code/") for name in files)
            or not any(name.startswith("model/") for name in files)
            or not expected["packages"]
            or expected["packages"] != sorted(set(expected["packages"]))
            or set(expected["vcs"]) != {"lang-sam", "sam-2"}
            or any(not re.fullmatch("[0-9a-f]{40}", value) for value in expected["vcs"].values())
            or set(expected["runtime"]) != {
                "python", "machine", "device", "dtype", "operator_fallback"
            }
            or expected["runtime"]["device"] != "mps"
            or expected["runtime"]["dtype"] != "float32"
            or expected["runtime"]["operator_fallback"] is not None
        ):
            raise ValueError("complete approved runtime manifest required")
        for entry in expected["files"].values():
            if (
                set(entry) != {"size", "sha256"}
                or type(entry["size"]) is not int
                or entry["size"] < 0
                or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])
            ):
                raise ValueError("exact file size and SHA-256 required")
        self._expected = expected
        self._files = dict(files)
        self._fingerprint = hashlib.sha256(encoded).hexdigest()
        self._inventory = observe_inventory
        self._vcs = observe_vcs
        self._runtime = observe_runtime

    @property
    def extractor_fingerprint(self):
        return self._fingerprint

    def __call__(self):
        try:
            if (
                sorted(self._inventory()) != self._expected["packages"]
                or self._vcs() != self._expected["vcs"]
                or self._runtime() != self._expected["runtime"]
            ):
                return False
            # ponytail: full hashing per check; optimize only after measured bootstrap cost.
            for name, path in self._files.items():
                entry = self._expected["files"][name]
                if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["size"]:
                    return False
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                        return False
            return True
        except Exception:  # noqa: BLE001 - failures cannot attest readiness or expose private paths.
            return False
