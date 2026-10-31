import json
import pytest
from report_ds27 import chosen_arms, distance, digest, verify_index, c_ablation


def test_geographic_distance():
    assert distance((0, 0), (0, 0)) == 0
    assert distance((0, 1), (0, 0)) == pytest.approx(111.19508, rel=1e-6)


def test_nested_fallback_and_chosen_result():
    baseline = dict(model_version="algo02-causal-family-v1", arms={"c0": "original"})
    v2 = dict(model_version="algo03-causal-predictive-v1", baseline=baseline, selected=None)
    v3 = dict(model_version="algo04-causal-numerical-v1", incumbent=v2, decision="ALGO03_fallback")
    assert chosen_arms(v3) == baseline["arms"]
    v3.update(decision="ALGO04_additive", candidate=dict(v2, selected={"arms": {"c0": "new"}}))
    assert chosen_arms(v3) == {"c0": "new"}


def test_seal_detects_changed_input(tmp_path):
    data = tmp_path/"data.json"
    data.write_text("[]")
    entry = dict(case="x", state="complete")
    for name in ("terminal", "observations", "tracks"):
        entry.update({name+"_path": str(data), name+"_sha256": digest(data)})
    index, seal = tmp_path/"index.json", tmp_path/"seal.json"
    index.write_text(json.dumps({"cases": [entry]}))
    seal.write_text(json.dumps({"analysis_index_sha256": digest(index)}))
    verify_index(index, seal)
    data.write_text("[1]")
    with pytest.raises(ValueError, match="Changed inference"):
        verify_index(index, seal)


def test_missing_unavailable_case_is_not_silent_denominator_change(tmp_path):
    raw, execution = tmp_path/"raw.json", tmp_path/"execution.json"
    raw.write_text("{}")
    execution.write_text(json.dumps(dict(manifest_path=str(raw), manifest_sha256=digest(raw),
        cases=[dict(case="DS27-0001", recording_id="a", recording_format="short_window_iq_recording")])) )
    index, seal = tmp_path/"index.json", tmp_path/"seal.json"
    index.write_text(json.dumps({"cases": []}))
    seal.write_text(json.dumps(dict(analysis_index_sha256=digest(index), dataset_execution_manifest_sha256=digest(execution))))
    with pytest.raises(ValueError, match="Missing or extra"):
        verify_index(index, seal, execution)


def test_frequency_comparison_excludes_changed_support_but_error_retains_it():
    rows = []
    for case, same in [("a", True), ("b", False)]:
        for arm, err, obj in [("c0", 1.0, 200), ("fitted_c", 2.0, 100)]:
            rows.append(dict(method="ALGO04", case=case, arm=arm, error_km=err,
                frequency_objective=obj, frequency_rms_hz=None, state="complete",
                support_sha256="same" if same or arm == "c0" else "different"))
    result = c_ablation(rows)["ALGO04"]
    assert result["paired_scans"] == 2
    assert result["identical_support_pairs"] == 1
    assert result["frequency_objective_comparable_pairs"] == 1
    assert result["mean_fitted_minus_c0_error_km"] == 1
    assert result["mean_fitted_minus_c0_frequency_objective"] == -100
