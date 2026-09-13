"""Release integrity checks and a bounded native engine call; no RF access."""

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from leo.radio.host_decision_release import load_host_decision_release

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "runtime/scanner-host-decision"


def identity(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_packaged_qualified_engine_loads_and_keeps_unknown_support_explicit():
    manifest = BUNDLE / "manifest.json"
    release = load_host_decision_release(manifest, identity(manifest))
    assert release.configuration.decision_rate_hz == 2_500_000
    with release.create_engine() as engine:
        result = engine.run(np.zeros((1_200_000, 2), dtype="<i2"), edge="lower")
    assert result.screen_mask == 63 and result.confirmation_mask in (1, 2, 4, 8, 16, 32)
    assert result.outcome != "detected"


@pytest.mark.parametrize(
    "fault", ["manifest", "binary", "source", "templates", "inventory", "escape", "symlink"]
)
def test_corrupt_release_is_rejected_before_loading_native_code(tmp_path, fault):
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE, bundle)
    manifest = bundle / "manifest.json"
    expected = identity(manifest)
    value = json.loads(manifest.read_text())
    if fault == "manifest":
        manifest.write_text(manifest.read_text() + " ")
    elif fault == "binary":
        (bundle / "decision.so").write_bytes(b"corrupt")
    elif fault == "symlink":
        (bundle / "decision.so").unlink()
        (bundle / "decision.so").symlink_to(BUNDLE / "decision.so")
    else:
        if fault == "source":
            value["sources"]["analysis/host_decision.py"] = "sha256:" + "0" * 64
        elif fault == "templates":
            value["templates_sha256"] = "sha256:" + "0" * 64
        elif fault == "inventory":
            del value["files"]["build.json"]
        elif fault == "escape":
            value["sources"]["../outside"] = "sha256:" + "0" * 64
        manifest.write_text(json.dumps(value))
        expected = identity(manifest)
    with pytest.raises(ValueError):
        load_host_decision_release(manifest, expected)
