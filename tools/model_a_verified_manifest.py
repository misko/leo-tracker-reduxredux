"""Exact-byte validation port after a genuine scientific authority qualification.

Callers qualify semantics with their existing reader before pinning this manifest.
This port never invents authority, reconstructs a model, or relaxes source checks.
"""

import hashlib
from pathlib import Path


def file_digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin_qualified_files(directories, *, source_files, extra_files=()):
    """Pin original inputs, receipts and archive bytes from qualified directories."""
    files = {Path(p).resolve() for p in (*source_files, *extra_files)}
    inventories = {}
    for folder in directories:
        folder = Path(folder).resolve()
        inventory = []
        for path in folder.rglob("*"):
            if path.is_file() and not path.name.startswith("development-errors"):
                files.add(path.resolve())
                inventory.append(str(path.relative_to(folder)))
        inventories[str(folder)] = sorted(inventory)
    return dict(
        files={str(path): file_digest(path) for path in sorted(files)},
        directories=inventories,
        excluded_derived_filename_prefix="development-errors",
    )


def verify_pinned_files(manifest):
    """Check every originally qualified byte; missing files are explicit failures."""
    if (
        not isinstance(manifest, dict)
        or not manifest.get("files")
        or manifest.get("excluded_derived_filename_prefix") != "development-errors"
    ):
        raise ValueError("A nonempty qualified file manifest is required")
    for folder, expected_inventory in manifest["directories"].items():
        actual = sorted(
            str(p.relative_to(folder))
            for p in Path(folder).rglob("*")
            if p.is_file() and not p.name.startswith("development-errors")
        )
        if actual != expected_inventory:
            raise ValueError(f"Qualified authority directory inventory changed: {folder}")
    for filename, expected in manifest["files"].items():
        if not Path(filename).is_absolute() or not isinstance(expected, str):
            raise ValueError("Qualified manifest requires absolute files and digest strings")
        if file_digest(filename) != expected:
            raise ValueError(f"Qualified authority changed: {filename}")
