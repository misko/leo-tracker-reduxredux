from importlib import import_module
from hashlib import sha256
import json
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


@pytest.mark.parametrize("wrong", [None, "digest", "session", "inventory", "receiver"])
def test_replay_requires_all_saved_input_bindings(wrong, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    verified_saved = import_module("joint_publication").verified_saved
    native = dict(source=dict(session_id="session", input_manifest_sha256="inventory"),
                  provenance=dict(detector_sha256="sha256:receiver"))
    args = dict(expected=canonical_digest(native), session="session", inventory_digest="inventory", receiver="receiver")
    if wrong:
        args[{"digest": "expected", "inventory": "inventory_digest"}.get(wrong, wrong)] = "wrong"
        with pytest.raises(ValueError):
            verified_saved(native, **args)
    else:
        assert verified_saved(native, **args) is native


def test_recorded_raw_pair_binds_decoded_positions_and_saved_science():
    root = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    source = (root / "measurements/joint-south-raw-pair.json").read_bytes()
    runs = json.loads(source)["runs"]
    audit = json.loads((root / "development/joint-south-audit.json").read_bytes())
    assert audit["raw_pair_sha256"] == sha256(source).hexdigest()
    assert runs["candidate"]["native_file_sha256"] == runs["baseline"]["native_file_sha256"]
    assert audit["scientific"]["candidate"] == audit["scientific"]["saved"]
    for name, row in runs.items():
        assert row["receipt"]["window_count"] == 1200 and row["receipt"]["decision"] == "complete"
        images = row["evidence"]["images"]
        assert len(images) == 8
        pixel_file = (root / f"development/joint-{name}-position.png").read_bytes()
        assert "sha256:" + sha256(pixel_file).hexdigest() == images["position"]["sha256"]
