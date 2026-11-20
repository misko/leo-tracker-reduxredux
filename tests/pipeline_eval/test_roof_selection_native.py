from copy import deepcopy

import pytest

from tools.pipeline_eval import corpus
from tools.pipeline_eval.qualification import roof_selection_native as trial
from tools.pipeline_eval.qualification import roof_selection_native_results as results


def test_complement_selection_reads_no_reference_outcomes(monkeypatch):
    def unexpected(_):
        raise AssertionError("replay roster cannot depend on references")

    monkeypatch.setattr(corpus, "references", unexpected)
    inputs, common, order, _ = trial.roster()
    assert len(order) == len(set(order)) == 32
    assert len(set(inputs)) == 159
    assert set(inputs) - set(common) == set(order)


def test_absent_native_record_preserves_original_tile_and_two_empty_arms():
    inputs, _, _, _ = trial.roster()
    query = trial.bound_query(inputs["DS26-0172"])
    row = trial.unavailable(query)
    results.validate_native(row, query, fresh=True)
    assert row["result"]["reason"] == "no_native_run"
    assert row["result"]["status"] == "unavailable"
    assert not row["worker_attempted"]
    assert row["tile"] == inputs["DS26-0172"]["regions"][0]
    assert row["input_sha256"] is row["catalog_sha256"] is row["native_sha256"] is None
    assert all(arm["latlon"] is None for arm in row["result"]["arms"].values())
    forged = deepcopy(row)
    forged["result"]["reason"] = "invented"
    with pytest.raises(ValueError, match="frozen absent-native reason"):
        results.validate_native(forged, query, fresh=True)


def test_original_timeout_cannot_be_a_paired_accuracy_success():
    assert results.proximity(0.0, None) is False
    assert results.proximity(None, 1.0) is False
    assert results.proximity(1.11, 1.0) is False
    assert results.proximity(1.1, 1.0) is True
