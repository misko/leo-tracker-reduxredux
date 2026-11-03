import json
from types import SimpleNamespace

import finite_set_grouped_cohort as cohort
import numpy as np
import pytest
from finite_set_grouped_cohort import expanded_seed_ladder, fit_grouped_cohort_unit


def source_fit():
    return {
        "rough": {"assignments": [
            {"accepted": True, "source_groups": 30 - index, "span_s": 20,
             "satellite_index": index}
            for index in range(16)
        ]},
        "trials": [
            {"satellite_indices": list(range(size)),
             "parameters": [float(size)] * 6 + [0.1] * size + [0.] * (20 - size)}
            for size in (4, 8, 12)
        ],
    }


def test_expanded_ladder_keeps_all_eligible_tracks_and_same_bank_seeds():
    seeds = expanded_seed_ladder(source_fit(), 20, 1)
    assert [len(seed["satellite_indices"]) for seed in seeds] == [4, 8, 12, 16]
    assert seeds[0]["seed_policy"] == "same_bank_coherent"
    assert seeds[-1]["seed_bank"] == list(range(12))
    np.testing.assert_array_equal(seeds[-1]["parameters"][18:], np.zeros(8))


def test_duplicate_banks_and_bad_candidate_indices_fail():
    source = source_fit()
    source["trials"].append(source["trials"][0])
    with pytest.raises(ValueError, match="distinct"):
        expanded_seed_ladder(source, 20, 1)
    source = source_fit()
    source["rough"]["assignments"][0]["satellite_index"] = 21
    with pytest.raises(ValueError, match="invalid satellite"):
        expanded_seed_ladder(source, 20, 1)


def test_all_banks_keep_fixed_mass_and_unresolved_status():
    calls = []
    data = SimpleNamespace(
        numbers=np.arange(20), times=np.arange(2.), measured=np.arange(2.),
        rf=np.ones(2), receiver=np.array([0, 1]), channel=np.ones(2), group=np.arange(2),
        geometry_receipt={"verified": True},
    )

    def refiner(data, parameters, satellites, weights, likelihood, **options):
        calls.append((likelihood.detection_probability, options))
        return {"objective": 1., "initial_objective": 2., "selection_score": 2.,
                "success": len(satellites) != 16}

    result = fit_grouped_cohort_unit(data, source_fit(), capture_count=1, refiner=refiner)
    assert len(calls) == 4
    assert all(call[0] == 0.8 / 16 for call in calls)
    assert calls[0][1]["slope_bound"] == 50.0
    assert calls[0][1]["tau_sigma_s"] == 1.0
    assert not result["selection"]["selection_resolved"]


def test_initialization_failures_are_persisted_without_overwriting(monkeypatch, tmp_path):
    monkeypatch.setattr(cohort, "ROOT", tmp_path)

    def fail(unit_id, **options):
        raise ValueError("bad bound input")

    monkeypatch.setattr(cohort, "_run_unit", fail)
    with pytest.raises(ValueError, match="bad bound input"):
        cohort.run_unit("DS10-S01")
    path = tmp_path / "runs" / cohort.RUN_ID / "DS10-S01" / "failure.json"
    assert json.loads(path.read_text())["stage"] == "loading_or_initialization"
    frozen = path.read_bytes()
    with pytest.raises(FileExistsError):
        cohort.run_unit("DS10-S01")
    assert path.read_bytes() == frozen


def test_short_bank_pool_is_retained_without_padding_or_duplicate_trials():
    source = source_fit()
    source["rough"]["assignments"] = source["rough"]["assignments"][:15]
    seeds = expanded_seed_ladder(source, 20, 1)
    assert [len(seed["satellite_indices"]) for seed in seeds] == [4, 8, 12, 15]


def test_legacy_joint_child_bindings_use_same_immutable_contract():
    children = [{"session_id": "capture", "bundle_json_sha256": "json",
                 "bundle_npz_sha256": "npz"}]
    assert cohort.joint_child_bindings({"children": children}) == children
    assert cohort.joint_child_bindings({"legacy_manifest_artifacts": {
        "children": children,
    }}) == children
    with pytest.raises(ValueError, match="lacks child"):
        cohort.joint_child_bindings({})
