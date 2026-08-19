#!/usr/bin/env python3
"""Build the reviewed content manifest for the pinned legacy oracle environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

REVISION = "0bb80d14759fd8496b74e7d3219a690be18565a6"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _entry(path: Path, *, relative_to: Path | None = None) -> dict[str, object]:
    info = path.lstat()
    name = str(path.relative_to(relative_to)) if relative_to is not None else str(path)
    if stat.S_ISLNK(info.st_mode):
        return {"path": name, "kind": "symlink", "target": os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"environment contains unsupported file type: {path}")
    return {
        "path": name,
        "kind": "file",
        "mode": stat.S_IMODE(info.st_mode),
        "size": info.st_size,
        "sha256": _sha256(path),
    }


def _nofollow_inventory(root: Path) -> list[Path]:
    inventory: list[Path] = []
    for directory, names, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in tuple(names):
            candidate = parent / name
            if stat.S_ISLNK(candidate.lstat().st_mode):
                inventory.append(candidate)
                names.remove(name)
        inventory.extend(parent / name for name in files)
    return sorted(inventory)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.legacy_root.absolute()
    venv = root / ".venv"
    python = venv / "bin/python"
    probe = """
import json, os, sys
sys.path.insert(0, os.environ['LEGACY_SOURCE'])
import numpy, scipy
from leo_tracker.radio.beacon.acquisition import acquire_exact_receiver
from leo_tracker.radio.beacon.decode import demodulate_edge_window
paths = {sys.executable, os.path.realpath(sys.executable)}
for line in open('/proc/self/maps', encoding='utf-8'):
    fields = line.split()
    if len(fields) >= 6 and 'x' in fields[1] and fields[-1].startswith('/'):
        paths.add(fields[-1].removesuffix(' (deleted)'))
print(json.dumps(sorted(paths)))
"""
    environment = os.environ.copy()
    environment.update(
        {
            "LEGACY_SOURCE": str(root / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CACHE_HOME": str(root / ".venv/.oracle-cache-disabled"),
        }
    )
    result = subprocess.run(
        [str(python), "-I", "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    external = []
    for item in json.loads(result.stdout):
        path = Path(item)
        if venv == path or venv in path.parents:
            continue
        external.append(_entry(path))
    entries = [_entry(path, relative_to=venv) for path in _nofollow_inventory(venv)]
    values = {
        "schema_version": 1,
        "kind": "legacy_oracle_environment_content_manifest",
        "source_revision": REVISION,
        "fixed_legacy_root": str(root),
        "python_relative_path": ".venv/bin/python",
        "venv_entries": entries,
        "external_executable_files": sorted(external, key=lambda item: str(item["path"])),
    }
    document = {**values, "manifest_digest": _canonical_digest(values)}
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
