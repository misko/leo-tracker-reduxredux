import json
import struct

import numpy as np
import pytest

from tools.native_presence import write_probe
from tools.qualify_native_presence import digest
from tools.qualify_presence_worker import compare_values, prepare


def fixture_source(directory, rate=2500000):
    directory.mkdir()
    counter = 10**16 + 37
    probe = directory / "one.probe"
    write_probe(probe, np.zeros(rate // 50), rate, "lower", counter, ci16=True)
    provenance = {"rx": 1, "visit": 83, "channel": 4, "probe_offset_ms": 0}
    row = {
        "file": probe.name,
        "sha256": digest(probe),
        "rate_hz": rate,
        "edge": "lower",
        "device_counter": str(counter),
        "provenance": provenance,
        "oracle_candidates": [],
    }
    result = {
        "probe": probe.name,
        "provenance": provenance,
        "reference_positive": False,
        "detected": False,
        "matched_reference": False,
        "result": {
            "rate_hz": rate,
            "device_counter": str(counter),
            "format": 2,
            "edge": 0,
            "candidates": [],
        },
    }
    (directory / "inputs.json").write_text(json.dumps([row]))
    (directory / "results.json").write_text(json.dumps([result]))
    return directory, probe


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_pack_preserves_exact_ci16_and_counter(tmp_path, rate):
    source, original = fixture_source(tmp_path / "source", rate)
    output = tmp_path / "pack"
    prepare(source, output, rate)
    data = (output / "probes.pack").read_bytes()
    assert struct.unpack("<4sIIQQII", data[:36]) == (b"LPP1", rate, 1, 10**16 + 37, 83, 0, 4)
    assert data[36:] == bytes(rate // 50 * 4)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["pack_sha256"] == digest(output / "probes.pack")
    assert manifest["records"][0]["sha256"] == digest(original)
    with pytest.raises(FileExistsError):
        prepare(source, output, rate)


@pytest.mark.parametrize("damage", ["hash", "provenance", "duplicate"])
def test_pack_refuses_changed_or_misassociated_evidence(tmp_path, damage):
    source, probe = fixture_source(tmp_path / "source")
    if damage == "hash":
        with probe.open("ab") as stream:
            stream.write(b"x")
    else:
        path = source / "results.json"
        rows = json.loads(path.read_text())
        if damage == "duplicate":
            rows.append(rows[0])
        else:
            rows[0]["provenance"]["visit"] += 1
        path.write_text(json.dumps(rows))
    with pytest.raises(ValueError):
        prepare(source, tmp_path / "out", 2500000)


def test_numerical_comparison_uses_fixed_tolerances_and_rejects_nonfinite():
    reference = {
        "epoch": 12,
        "fractional_complete": 1,
        "fractional_offset_samples": 0.2,
        "acquired_cfo_hz": 10000.0,
        "tracking_cfo_hz": 10001.0,
        "exact_score": 0.2,
        "control_score": 0.1,
        "margin": 0.1,
    }
    compare_values(reference, reference)
    for key, value in (
        ("tracking_cfo_hz", 10001.1),
        ("fractional_offset_samples", 0.201),
        ("margin", float("nan")),
        ("fractional_complete", 0),
    ):
        with pytest.raises(ValueError):
            compare_values({**reference, key: value}, reference)
