"""Read-only verification of the proposed B0 source and pre-transfer target."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
manifest_path = ROOT / 'baseline-manifest.json'
manifest = json.loads(manifest_path.read_text())
failures = []
for entry in manifest['files']:
    rel = Path(entry['path'])
    if rel.is_absolute() or '..' in rel.parts:
        failures.append(f'Unsafe relative path: {rel}')
        continue
    source = Path(manifest['source_root']) / rel
    target = Path(manifest['target_root']) / rel
    if not source.is_file() or source.is_symlink():
        failures.append(f'Source missing/unsafe: {rel}')
        continue
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != entry['source_sha256']:
        failures.append(f'Source changed: {rel}')
    expected = entry['target_sha256']
    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
    if actual != expected:
        failures.append(f'Pre-transfer target changed: {rel}')
if manifest['unresolved_local_imports']:
    failures.append('Unresolved static local imports')
if failures:
    raise SystemExit('\n'.join(failures))
print(f"Verified {len(manifest['files'])} source/target entries; no copy/import/execution")
print('Manifest SHA256:', hashlib.sha256(manifest_path.read_bytes()).hexdigest())
