from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_ds5


def test_zero_timing_identity_selection_uses_training_only_and_keeps_sites_separate(monkeypatch):
    track = SimpleNamespace(track_id="track")
    prepared = SimpleNamespace(
        catalogue=object(), candidate_indices=[0, 1], start_utc_ns=0, tracks=[track]
    )
    measured = np.array([0.0, 1.0, 50.0, -80.0])
    training = np.array([True, True, False, False])

    def evaluator(_banks, point, taus_s):
        # Site 1 makes ID 10 exact on training; site 2 makes ID 20 exact.
        good = np.array([0.0, 1.0, 9999.0, -9999.0])
        bad = np.array([0.0, 3.0, 50.0, -80.0])
        prediction = np.stack((good, bad) if point == 1.0 else (bad, good))[:, None, :]
        block = SimpleNamespace(
            track_id="track",
            measured_hz=measured,
            predictions_hz=prediction,
            training_mask=training,
            visible=np.array([[True], [True]]),
            candidate_ids=np.array([10, 20]),
        )
        return lambda _east, _north: (block,)

    monkeypatch.setattr(run_ds5, "build_prediction_banks", lambda *a, **k: (object(), object()))
    monkeypatch.setattr(run_ds5, "point_factory", lambda latitude, longitude: latitude)
    monkeypatch.setattr(run_ds5, "RegionalTrackPredictionEvaluator", evaluator)
    sites = {
        "first": {"latitude_deg": 1.0, "longitude_deg": 0.0},
        "second": {"latitude_deg": 2.0, "longitude_deg": 0.0},
    }
    selected = run_ds5.select_zero_timing(prepared, sites)
    assert selected["first"]["track"]["candidate_id"] == "10"
    assert selected["second"]["track"]["candidate_id"] == "20"


def test_sites_from_document_does_not_merge_prior_coordinates():
    document = {
        "diagnostics": {
            "reference_evaluation_only": {"latitude_deg": 3.0, "longitude_deg": 4.0}
        },
        "priors": [
            {"name": "sacramento", "selected": {"latitude_deg": 1.0, "longitude_deg": 2.0}},
            {"name": "reno", "selected": {"latitude_deg": 5.0, "longitude_deg": 6.0}},
        ],
    }
    sites = run_ds5.sites_from_document(document)
    assert sites["sacramento"] is document["priors"][0]["selected"]
    assert sites["reno"] is document["priors"][1]["selected"]
    assert sites["reference"] is document["diagnostics"]["reference_evaluation_only"]
    assert len({(v["latitude_deg"], v["longitude_deg"]) for v in sites.values()}) == 3


def test_generated_results_bind_every_scan_to_evidence_and_snapshot():
    results = run_ds5.json.loads((HERE / "results.json").read_text())
    assert len(results["scans"]) == results["dataset"]["expected_included"] == 42
    assert results["failures"] == []
    assert all(scan["document_sha256"] for scan in results["scans"])
    assert all(scan["evidence_sha256"] for scan in results["scans"])
    assert all(scan["snapshot_digest"] for scan in results["scans"])

