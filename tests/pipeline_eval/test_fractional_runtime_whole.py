import json
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import fractional_runtime_whole as parity

CANDIDATE = "12" * 32
STOCK = "34" * 32


def native(library, margin):
    probes = [{"visit_index": 3, "candidates": [{"margin": margin, "cfo": -1234.1}]}]
    excluded = [{"visit": 2, "reason": "capture exclusion"}]
    analysis = "sha256:" + parity.canonical_sha(
        [parity.IDENTITY, "sha256:" + library, "input", probes, excluded]
    )
    return {
        "schema_version": 2,
        "source": {
            "input_manifest_sha256": "input",
            "probes": probes,
            "analysis_manifest_sha256": analysis,
        },
        "provenance": {
            "detector_sha256": "sha256:" + library,
            "excluded_windows": excluded,
            "run_id": "replay-" + analysis[7:39],
        },
    }


def test_whole_parity_challenges_candidate_fields_after_normalizing_provenance(monkeypatch):
    monkeypatch.setattr(parity, "_sha", lambda _path: STOCK)
    candidate, stock = native(CANDIDATE, -0.0005), native(STOCK, -0.0005)
    stock_hash = parity.canonical_sha(stock, newline=True)
    assert parity.verify_native(candidate, stock_hash, CANDIDATE)["retained_probe_rows"] == 1
    assert candidate["provenance"]["detector_sha256"] == "sha256:" + CANDIDATE
    with pytest.raises(ValueError, match="three detector lineage"):
        parity.verify_native(native(CANDIDATE, -0.0004), stock_hash, CANDIDATE)


def request(library, path):
    digest = "sha256:" + library
    return {
        "job": {
            "native_input": {"path": path, "sha256": digest},
            "output_root": path + ".out",
            "evaluation_reference": None,
            "identity": {
                "input_sha256": digest,
                "run_id": "experiment-" + digest[7:39],
                "session_id": "recording",
            },
            "track_budget": 64,
        }
    }


def test_native_request_rebinding_preserves_blind_scientific_settings():
    trial, control = request(CANDIDATE, "/trial"), request(STOCK, "/stock")
    parity.verify_request(trial, control, native_path="/trial", native_sha256=CANDIDATE)
    alternate = deepcopy(trial)
    alternate["job"]["track_budget"] -= 1
    with pytest.raises(ValueError, match="differs beyond paths"):
        parity.verify_request(alternate, control, native_path="/trial", native_sha256=CANDIDATE)


def test_raw_lane_parity_retains_every_gate_and_allows_observed_timing(tmp_path):
    trial, baseline = tmp_path / "trial", tmp_path / "baseline"
    trial.mkdir()
    baseline.mkdir()
    for folder, digest, time in ((trial, CANDIDATE, 123), (baseline, STOCK, 12)):
        for lane in range(2):
            rows = (
                {"kind": "visit", "clock_anchor": None, "probes": [{"retained": True}]},
                {
                    "kind": "segment",
                    "library_sha256": "sha256:" + digest,
                    "segment": lane,
                    "detector_cpu_s": time,
                    "wall_s": time + 3,
                },
                {"kind": "worker", "worker": lane},
            )
            (folder / f"replayed-{lane}.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
            )
    allowed = dict(expected_binary=CANDIDATE, control_binary=STOCK)
    assert parity.compare_lanes(trial, baseline, **allowed) == {
        "visits": 2,
        "segments": 2,
        "lanes": 2,
    }
    path = trial / "replayed-1.jsonl"
    path.write_text(path.read_text().replace('"retained": true', '"retained": false'))
    with pytest.raises(ValueError, match="lane 1 row 0"):
        parity.compare_lanes(trial, baseline, **allowed)
