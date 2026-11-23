import json
from hashlib import sha256

import numpy as np
import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3 import named_weak_exact, named_weak_visual


def test_raw_uses_original_acquisition_arguments_and_native_object():
    arguments = ("session", "inventory", object(), object())
    native = object()
    calls, audit = [], {}

    def original(*values):
        calls.append(values)
        return native

    acquire = named_weak_exact.acquire_once(original, "detector", audit)
    assert acquire(*arguments) is native
    assert calls == [arguments]
    assert audit["mode"] == "original"
    with pytest.raises(ValueError, match="one fresh"):
        acquire(*arguments)
    assert calls == [arguments]


def test_saved_handoff_checks_sealed_bytes_and_named_provenance(tmp_path):
    native = {
        "source": {
            "session_id": "session", "input_manifest_sha256": "inventory",
            "raw_recording_authority_digest": "raw", "qualified": True, "probes": [],
            "analysis_manifest_sha256": canonical_digest(["cancellation", "raw", "detector", []]),
        },
        "provenance": {"detector_sha256": "sha256:detector"},
    }
    saved = tmp_path / "sealed.json"
    data = json.dumps(native, sort_keys=True, separators=(",", ":")).encode()
    saved.write_bytes(data)
    expected = "sha256:" + sha256(data).hexdigest()

    def invalid(*_values):
        pytest.fail("saved launch would read I/Q")

    audit = {}
    acquire = named_weak_exact.acquire_once(invalid, "detector", audit, saved=saved, expected=expected)
    with pytest.raises(ValueError, match="raw authority"):
        acquire("different", "inventory", None, None)
    assert not audit
    assert acquire("session", "inventory", None, None) == native
    assert audit["mode"] == "saved"

    saved.write_bytes(data + b" ")
    acquire = named_weak_exact.acquire_once(invalid, "detector", {}, saved=saved, expected=expected)
    with pytest.raises(ValueError, match="Unreviewed bootstrap input"):
        acquire("session", "inventory", None, None)


def test_missing_saved_seal_is_rejected_before_loading_the_installed_runtime():
    with pytest.raises(ValueError, match="both the saved detector file"):
        named_weak_exact.run(None, optimized=True, saved="packet.json")


def test_registered_support_sees_missing_layers_and_uses_both_directions():
    stock = np.zeros((10, 10), dtype=bool)
    candidate = stock.copy()
    assert named_weak_visual.support(stock, candidate) == {"pixels": [0, 0], "fraction": None}
    stock[0, 0] = True
    with pytest.raises(ValueError, match="omitted"):
        named_weak_visual.support(stock, candidate)
    candidate[2, 2] = candidate[9, 9] = True
    assert named_weak_visual.support(stock, candidate) == {"pixels": [1, 2], "fraction": [1., .5]}


def test_registration_diagnostic_retains_failure_without_changing_default(monkeypatch):
    from PIL import Image, ImageDraw

    monkeypatch.setattr(named_weak_visual, "orbit_boxes", lambda rgb: [(0, 0, 2160, 246)])
    first = Image.new("RGB", (2160, 246), "white")
    ImageDraw.Draw(first).rectangle((30, 30, 45, 45), fill="red")
    second = first.copy()
    ImageDraw.Draw(second).rectangle((230, 30, 245, 45), fill="red")
    with pytest.raises(ValueError, match="two-pixel"):
        named_weak_visual.registered_orbits(first, second)
    rows = named_weak_visual.registered_orbits(first, second, require_match=False)["rows"]
    assert rows[0]["color"]["fraction"] == [1., .5]
