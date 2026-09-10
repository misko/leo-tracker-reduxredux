"""Archived execution recipes retain their bytes instead of being reformatted."""

import hashlib
import json
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = (
    ("2026_09_08_arm_presence_300s", "receipt.json"),
    ("2026_09_08_scanner_glrt_package_arm", "index.json"),
    ("2026_09_08_scanner_glrt_sdk_replay", "receipt.json"),
    ("2026_09_08_scanner_glrt_userspace_bundle", "index.json"),
)


@pytest.mark.parametrize(("directory", "manifest"), ARCHIVES)
def test_archived_glrt_recipes_match_original_manifest(directory, manifest):
    relative = "reports/evidence/" + directory
    root = ROOT / relative
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert relative in config["tool"]["ruff"]["extend-exclude"]
    document = json.loads((root / manifest).read_text())
    inventory = document.get("artifacts")
    if inventory is None:
        inventory = {item["path"]: item for item in document["evidence"]}
    scripts = {path.relative_to(root).as_posix() for path in root.rglob("*.py")}
    assert scripts == {name for name in inventory if name.endswith(".py")}
    assert scripts
    for name in sorted(scripts):
        raw = (root / name).read_bytes()
        assert len(raw) == inventory[name]["bytes"], name
        assert hashlib.sha256(raw).hexdigest() == inventory[name]["sha256"], name
