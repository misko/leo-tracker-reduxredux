import copy

import numpy as np
import pytest
from finite_set_family_bias import fit_models, reconstruct_geometry, validate_geometry_receipt
from test_finite_set_alias_family import source_data


def family_source():
    return {
        "representative_row_count": 2,
        "grouping": {"families": [
            {"representative_candidate_id": "b", "lineage": [
                {"candidate_id": "a", "input_row_index": 0},
                {"candidate_id": "b", "input_row_index": 1},
                {"candidate_id": "c", "input_row_index": 2},
            ]},
            {"representative_candidate_id": "d", "lineage": [
                {"candidate_id": "d", "input_row_index": 3},
            ]},
        ]},
    }


def test_grouping_reconstruction_preserves_original_median_and_lineage():
    source = family_source()
    frozen = copy.deepcopy(source)
    data = reconstruct_geometry(source_data(), source)
    np.testing.assert_array_equal(data.original_rows, [1, 3])
    np.testing.assert_array_equal(data.times, [1, 20])
    assert source == frozen


def test_geometry_receipt_binds_representative_order_and_values():
    source = family_source()
    data = reconstruct_geometry(source_data(), source)
    source["geometry_receipt"] = copy.deepcopy(data.geometry_receipt)
    validate_geometry_receipt(data, source)
    source["geometry_receipt"]["fitted_array_hashes"]["measured"] = "changed"
    with pytest.raises(ValueError, match="sealed geometry"):
        validate_geometry_receipt(data, source)


def test_legacy_receipt_requires_hash_bound_correction():
    source = family_source()
    data = reconstruct_geometry(source_data(), source)
    source["geometry_receipt"] = data.geometry_receipt["preselection_geometry"]
    with pytest.raises(ValueError, match="explicit postseal"):
        validate_geometry_receipt(data, source)
    correction = {
        "fitted_row_hashes": data.geometry_receipt["fitted_array_hashes"],
        "original_rows_sha256": data.geometry_receipt["original_rows_sha256"],
        "fitted_row_count": 2, "fitted_group_count": 2,
    }
    validate_geometry_receipt(data, source, correction)
    correction["original_rows_sha256"] = "reordered"
    with pytest.raises(ValueError, match="sealed correction"):
        validate_geometry_receipt(data, source, correction)


@pytest.mark.parametrize("corruption", ["duplicate", "missing", "cross_group", "count"])
def test_invalid_families_rejected(corruption):
    source = family_source()
    families = source["grouping"]["families"]
    if corruption == "duplicate":
        families[0]["lineage"][0]["input_row_index"] = 1
    elif corruption == "missing":
        families[0]["representative_candidate_id"] = "absent"
    elif corruption == "cross_group":
        families[0]["lineage"][0]["input_row_index"] = 3
        families[1]["lineage"][0]["input_row_index"] = 0
    else:
        source["representative_row_count"] = 3
    with pytest.raises(ValueError):
        reconstruct_geometry(source_data(), source)


def test_matched_seed_objectives_and_frozen_mass_for_entire_ladder():
    calls = []

    def fitter(data, source, likelihood, **options):
        calls.append(likelihood.detection_probability)
        penalty = 0.5 * (len(source["satellite_indices"]) - 1) * np.log(2)
        return {
            **source, "initial_objective": source["objective"],
            "objective": source["objective"] - 1,
            "selection_score": source["selection_score"] - 1 + penalty,
            "model": "bias", "success": False,
        }

    source = {"full_bank": [0, 1], "finite_set_trials": [
        {"satellite_indices": [0], "objective": 10., "selection_score": 10. + 0.5 * np.log(2),
         "entry_penalty": 0.5 * np.log(2), "success": True},
        {"satellite_indices": [0, 1], "objective": 8., "selection_score": 8. + np.log(2),
         "entry_penalty": np.log(2), "success": True},
    ]}
    result = fit_models(reconstruct_geometry(source_data(), family_source()), source, fitter=fitter)
    assert calls == [0.4, 0.4]
    assert len(result["baseline_trials"]) == 2
    assert not result["combined_selection"]["selection_resolved"]
    assert result["combined_selection"]["score_leader"]["model"] == "bias"


def test_mismatched_zero_bias_seed_is_rejected():
    def fitter(data, source, likelihood, **options):
        return {"initial_objective": 100., "objective": 99.}

    source = {"full_bank": [0], "finite_set_trials": [
        {"satellite_indices": [0], "objective": 1., "entry_penalty": 0.5 * np.log(2),
         "selection_score": 1. + 0.5 * np.log(2)},
    ]}
    with pytest.raises(ValueError, match="reproduce"):
        fit_models(reconstruct_geometry(source_data(), family_source()), source, fitter=fitter)
