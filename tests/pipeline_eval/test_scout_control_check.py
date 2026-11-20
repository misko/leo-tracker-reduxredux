import json
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import scout_control_check as check


def encode(doc):
    return json.dumps(doc).encode()


def document():
    return {
        "clock_anchor": {"sample_counter": 0},
        "delivery_clocks": [{"sample_counter": 12}, {"sample_counter": 24}],
        "last_sample_counter": 24,
        "source": {
            "raw_recording_authority_digest": "sha256:" + "a" * 64,
            "input_manifest_sha256": "sha256:" + "b" * 64,
            "probes": [
                dict(visit_index=2, receiver_id=rx, probe_index=0, candidates=[{"hypothesis": 4}])
                for rx in (0, 1)
            ],
        },
        "provenance": {
            "detector_sha256": "sha256:" + "c" * 64,
            "excluded_windows": [{"visit": 0}, {"visit": 1}],
        },
    }


def signature(doc, receipts=()):
    payload = encode(doc)
    return check.native_signature(payload, sha256(payload).hexdigest(), receipts)


def test_exact_native_fields_detect_clock_probe_candidate_and_exclusion_changes():
    doc = document()
    original = signature(doc)
    doc["source"]["probes"][0]["candidates"] = [{"hypothesis": 5}]
    changed = signature(doc, [dict(probes_sha256=original["probes_sha256"])])
    assert changed["probe_order_sha256"] == original["probe_order_sha256"]
    assert changed["full_probes_sha256"] != original["full_probes_sha256"]
    doc["source"]["probes"].reverse()
    doc["delivery_clocks"].reverse()
    doc["provenance"]["excluded_windows"].reverse()
    changed = signature(doc)
    for key in ("probe_order_sha256", "probes_sha256", "excluded_sha256", "clock_sha256"):
        assert changed[key] != original[key]
    with pytest.raises(ValueError, match="clock_sha256"):
        signature(doc, [dict(clock_sha256=original["clock_sha256"])])


def test_position_missing_is_not_exact_and_coordinates_use_binary_values():
    control = {"status": "ok", "arms": {"c0": {"latlon": None}, "fitted_c": {"latlon": [0.0, 2]}}}
    archived = {
        "status": "ok",
        "arms": {"c0": {"latlon": [1, 2]}, "fitted_c": {"latlon": [-0.0, 2]}},
    }
    arms = check.endpoints(control, archived)["arms"]
    assert arms["c0"] == {"state": "missing_control", "exact": None, "displacement_km": None}
    assert arms["fitted_c"] == {"state": "compared", "exact": False, "displacement_km": 0.0}


def test_primary_lock_required_before_audit_reads_positions(tmp_path, monkeypatch):
    ordinary_sha = check._sha
    reads = []

    def trace(path):
        reads.append(path.name)
        return ordinary_sha(path)

    monkeypatch.setattr(check, "_sha", trace)
    (tmp_path / "positions.jsonl.gz").write_bytes(b"unsealed")
    with pytest.raises(FileNotFoundError, match="public prediction lock"):
        check.sealed(tmp_path)
    assert reads == []
    (tmp_path / "prediction-lock.json").write_bytes(
        encode(dict(cases=["opaque"], files={"positions.jsonl.gz": "0" * 64}))
    )
    with pytest.raises(ValueError, match="unauthenticated"):
        check.sealed(tmp_path)
    assert reads == ["positions.jsonl.gz"]
