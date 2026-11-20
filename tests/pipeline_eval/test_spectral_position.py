from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import spectral_position
from tools.pipeline_eval.qualification.pilot_kernel_eval import _digest
from tools.pipeline_eval.qualification.spectral_position import verify_pair, verify_window


def test_replay_binds_scheduled_samples_and_full_candidate_payload():
    payload = dict(candidates=[dict(epoch=100, rank=0, score=0.13)])
    scheduled = dict(sequence=3, visit=1027, iq_sha256="authenticated", status="processed",
                     payload_sha256={"spectral": _digest(encoded(payload))})
    window = SimpleNamespace(sequence=3, acquisition={"global_visit": 1027},
                             iq_sha256="authenticated")
    result = SimpleNamespace(status="processed", model_dump=lambda **_: payload)
    verify_window(window, result, scheduled)
    payload["candidates"][0]["epoch"] += 1
    with pytest.raises(ValueError, match="stage-only visit"):
        verify_window(window, result, scheduled)


def test_paired_positions_require_distinct_authority_and_identical_arcs():
    numerical = dict(
        metrics=dict(observations_sha256="obs", tracks_sha256="tracks",
                     final_owners_sha256={"c0": "owners c0", "fitted_c": "owners fitted"}),
        arms={"c0": {"latlon": [37.0, -122.0], "rf_rms_hz": 100.0},
              "fitted_c": {"latlon": [37.01, -122.01], "rf_rms_hz": 99.0}},
    )
    control = dict(input_sha256="capture", result=numerical)
    trial = dict(input_sha256="partial-iq", result=deepcopy(numerical))
    verify_pair(control, trial)
    with pytest.raises(ValueError, match="distinct input identity"):
        verify_pair(control, control)
    trial["result"]["metrics"]["final_owners_sha256"]["c0"] = "different owner"
    with pytest.raises(ValueError, match="arc ownership"):
        verify_pair(control, trial)
    trial["result"]["metrics"] = deepcopy(numerical["metrics"])
    trial["result"]["arms"]["c0"]["rf_rms_hz"] += 1
    with pytest.raises(ValueError, match="v5 arm outputs"):
        verify_pair(control, trial)


def test_splice_restricts_replacement_to_qualified_probe_slots(monkeypatch):
    fresh = dict(visit_index=1024, receiver_id=0, valid_start_counter=8, candidates=[{"rank": 0}])
    unrelated = dict(fresh, visit_index=1025, valid_start_counter=18)
    archive = dict(
        source=dict(sample_rate_hz=10_000_000, analysis_manifest_sha256="original",
                    probes=[deepcopy(fresh), unrelated]),
        provenance={"run_id": "capture", "excluded_windows": [{"visit": 1026}]},
    )
    measurement = dict(
        producer={"run_id": "capture"}, source_sha256="source", kernel_sha256="kernel",
        rows=[dict(visit=1024, native=[fresh], sample_start=8, iq_sha256="recorded",
                   equal_status=True)],
    )
    audit = dict(archive_exclusions_equal=True, different_probe_keys=[], archive_sha256="archive")
    monkeypatch.setattr(spectral_position, "_measure", lambda *_: audit)
    native, checked = spectral_position.compose({"id": "capture"}, archive, measurement)
    assert checked == audit
    assert native["source"]["probes"][0] is fresh
    assert native["source"]["probes"][1] is unrelated
    assert native["source"]["analysis_manifest_sha256"] != "original"
    assert native["provenance"]["excluded_windows"] == archive["provenance"]["excluded_windows"]
    fresh["candidates"][0]["rank"] += 1
    with pytest.raises(ValueError, match="changed the archived fractional candidates"):
        spectral_position.compose({"id": "capture"}, archive, measurement)
