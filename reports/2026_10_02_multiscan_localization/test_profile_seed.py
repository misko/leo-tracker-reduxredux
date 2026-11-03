import hashlib
import json

import numpy as np
import pytest

import profile_seed
from test_fixed_position_diagnostic import synthetic_sourcefit
from test_staged_gradient import synthetic_orbital_data


def test_profile_grid_uses_only_rough_center_common_initial_and_objective_selection(monkeypatch):
    data, parameters = synthetic_orbital_data()
    sourcefit = synthetic_sourcefit(parameters)
    sourcefit["fit"]["rough"] = {
        "position_km": np.array([30.0, -40.0]),
        "assignments": [
            {
                "accepted": True,
                "source_groups": 20,
                "span_s": 20.0,
                "satellite_index": satellite,
            }
            for satellite in (0, 2)
        ],
    }
    sourcefit["fit"]["score_leader"]["parameters"][:2] = [150.0, 160.0]
    observed_positions = []
    observed_initials = []

    def fake_profile(data, current_sourcefit, position, budget_s):
        assert current_sourcefit is sourcefit
        assert budget_s == 3.0
        position = np.asarray(position, dtype=float)
        observed_positions.append(position.copy())
        leader = np.asarray(current_sourcefit["fit"]["score_leader"]["parameters"])
        satellites = np.asarray(
            current_sourcefit["fit"]["score_leader"]["satellite_indices"], dtype=int
        )
        initial = leader.copy()
        initial[6:] = 0.0
        initial[6 + satellites] = leader[6 + satellites]
        observed_initials.append(np.r_[initial[2:6], initial[6 + satellites]])
        fitted = initial.copy()
        fitted[:2] = position
        objective = float((position[0] - 35.0) ** 2 + (position[1] + 35.0) ** 2)
        return {
            "parameters": fitted,
            "objective": objective,
            "success": int(position[0] + position[1]) % 2 == 0,
            "status": "synthetic",
        }

    def fake_refine(data, initial, satellites, support, likelihood, **options):
        likelihood.last_result = {
            "track_unknown_responsibility": np.asarray([0.2]),
            "group_count": 3,
        }
        objective = float(np.sum((np.asarray(initial[:2]) - [34.0, -36.0]) ** 2))
        return {
            "parameters": np.asarray(initial).copy(),
            "success": objective != 2.0,
            "status": "synthetic",
            "message": "synthetic",
            "satellite_indices": np.asarray(satellites).copy(),
            "catalog_numbers": np.asarray(data.numbers)[satellites],
            "satellite_count": len(satellites),
            "objective": objective,
            "selection_score": objective + 1.0,
            "entry_penalty": 1.0,
            "satellite_weights": np.asarray(support) / np.sum(support),
            "satellite_support": np.zeros(len(satellites)),
            "null_support": 3.0,
            "groups": 3,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "elapsed_s": 0.0,
            "evaluations": 1,
            "iterations": 0,
            "projected_gradient_inf_norm": 0.0,
            "gradient_method": "synthetic",
        }

    monkeypatch.setattr(profile_seed, "fit_nuisance_at_position", fake_profile)
    monkeypatch.setattr(profile_seed, "refine_bank", fake_refine)
    monkeypatch.setattr(
        profile_seed,
        "_position_error_km",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("solver must not access oracle coordinates")
        ),
    )
    result = profile_seed.run_profile_seed(data, sourcefit)

    expected = np.asarray(
        [
            [30.0 + east, -40.0 + north]
            for east in profile_seed.GRID_OFFSETS_KM
            for north in profile_seed.GRID_OFFSETS_KM
        ]
    )
    np.testing.assert_array_equal(observed_positions, expected)
    assert len(result["nodes"]) == 25
    assert all(node["attempted"] for node in result["nodes"])
    for initial in observed_initials[1:]:
        np.testing.assert_array_equal(initial, observed_initials[0])
    assert not np.any(np.all(expected == [150.0, 160.0], axis=1))
    assert [row["node_index"] for row in result["finalists"]] == [18, 13, 17]
    assert len(result["final_trials"]) == 3
    assert result["best_trial"]["fit"]["objective"] == min(
        trial["fit"]["objective"] for trial in result["final_trials"]
    )
    assert result["selected_trial_converged"] is False
    assert result["local_search_resolved"] is False
    assert result["success"] is False
    assert result["bank_selection_reevaluated"] is False
    assert result["bank_selection_rule"] == "sealed source score_leader"
    assert data.provenance["reference_truth_read"] is False


def test_source_provenance_validates_current_selection_and_bundle(monkeypatch, tmp_path):
    selection = tmp_path / "selection.json"
    selection.write_text("{}\n")
    scan = tmp_path / "scans" / "scan-1"
    scan.mkdir(parents=True)
    payload = scan / "bundle.npz"
    payload.write_bytes(b"payload")
    payload_sha256 = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest = scan / "bundle.json"
    manifest.write_text(
        json.dumps({"artifacts": {"bundle_npz_sha256": payload_sha256}}) + "\n"
    )
    receipt = {
        "selection_sha256": hashlib.sha256(selection.read_bytes()).hexdigest(),
        "inputs": {"scan-1": hashlib.sha256(manifest.read_bytes()).hexdigest()},
        "unit": {"unit_id": "DS10-S01", "session_ids": ["scan-1"]},
    }
    monkeypatch.setattr(profile_seed, "ROOT", tmp_path)

    validation = profile_seed._validate_source_provenance(receipt)
    assert validation["selection_sha256"] == receipt["selection_sha256"]
    assert validation["inputs"]["scan-1"]["bundle_npz_sha256"] == payload_sha256

    selection.write_text('{"changed": true}\n')
    with pytest.raises(ValueError, match="selection digest"):
        profile_seed._validate_source_provenance(receipt)
