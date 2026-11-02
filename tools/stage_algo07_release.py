"""Stage ALGO07 and preserve all frozen ALGO06 dependencies."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stage_algo03_release as installer
import stage_algo06_release as previous

MANIFEST = "reports/ALGO07/releases/2026-11-01-r1/manifest.json"
MANIFEST_SHA256 = "6614bc662bc67c9e7c28bdedcd1e0dbfd469b677c7402886591f115973f7b8fa"
MODEL_VERSION = "algo07-causal-guarded-reassociation-v1"

def scientific_inventory(source, revision):
    files = previous.scientific_inventory(source, revision)
    payload = installer._git(source, "show", f"{revision}:{MANIFEST}")
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise ValueError("ALGO07 manifest changed")
    for name, expected in json.loads(payload)["sha256"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe ALGO07 member")
        if hashlib.sha256(installer._git(source, "show", f"{revision}:{name}")).hexdigest() != expected:
            raise ValueError("ALGO07 member changed: " + name)
        files[name] = expected
    return {**files, MANIFEST: MANIFEST_SHA256}

def stage(source, revision, python_root, uv, *, execute=False):
    files = scientific_inventory(source, revision)
    old = installer.scientific_inventory, installer.MODEL_VERSION, installer.MANIFEST_SHA256
    try:
        installer.scientific_inventory = lambda *_: files
        installer.MODEL_VERSION, installer.MANIFEST_SHA256 = MODEL_VERSION, MANIFEST_SHA256
        return installer.stage(source, revision, python_root, uv, execute=execute)
    finally:
        installer.scientific_inventory, installer.MODEL_VERSION, installer.MANIFEST_SHA256 = old

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--revision',required=True)
    p.add_argument('--python-root',type=Path,required=True);p.add_argument('--uv',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    print(json.dumps(stage(a.source,a.revision,a.python_root,a.uv,execute=a.execute)))
