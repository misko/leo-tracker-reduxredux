"""Component-owned checks for the bounded replay protocol."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recorded


def inventory():
    cases = []
    for split_index, split in enumerate(recorded.SPLITS):
        for rate_index, rate in enumerate(recorded.RATES):
            for visit in range(4):
                cases.append({"case_id": f"{split}-{rate}-{visit}", "origin": "real_ds5",
                              "split": split, "rate_hz": rate, "truth_status": "unknown",
                              "session_id": f"session-{split_index}-{rate_index}",
                              "visit_index": visit, "source_start_counter": visit * 120,
                              "source_end_counter_exclusive": (visit + 1) * 120})
    return {"cases": cases}


def test_outcome_independent_selection_and_order():
    payload = inventory()
    expected = recorded.select_cases(payload)
    payload["cases"].reverse()
    for case in payload["cases"]:
        case["detector_result"] = "invented outcome"
    selected, training = recorded.select_cases(payload)
    assert [c["case_id"] for c in selected] == [c["case_id"] for c in expected[0]]
    assert len(selected) == 24 and len(training) == 8
    assert all(c["visit_index"] < 2 for c in selected)
    assert all(c["visit_index"] >= 2 and c["split"] == "dev" for c in training)


def test_session_and_sample_leak_fail_loudly():
    payload = inventory()
    payload["cases"][16]["session_id"] = payload["cases"][0]["session_id"]
    with pytest.raises(ValueError, match="session leaks"):
        recorded.select_cases(payload)
    selected, training = recorded.select_cases(inventory())
    training = copy.deepcopy(training)
    training[0]["source_start_counter"] = 0
    with pytest.raises(ValueError, match="overlaps scored samples"):
        recorded.assert_disjoint(selected, training)
    training[0]["split"] = "holdout"
    with pytest.raises(ValueError, match="non-development"):
        recorded.assert_disjoint(selected, training)


def test_common_bank_receives_identical_immutable_arrays_and_preserves_scores():
    exact = np.ones((3, 64), dtype=complex)
    control = exact * .1
    exact.setflags(write=False)
    control.setflags(write=False)
    called = []
    def score(a, b):
        called.append((a, b))
        return {"a": {"score": 2., "cfo_hz": 3., "exact_score": 4.,
                      "control_score": 1., "control_cfo_hz": 5.},
                "b": {"score": 8., "cfo_hz": 3., "exact_score": 4.,
                      "control_score": 1., "control_cfo_hz": 5.}}
    bank = [{"candidate_id": i, "seed_cfo_hz": i * 80_000} for i in range(2)]
    results, _ = recorded.score_common_bank(bank, [(exact, control)] * 2, score)
    assert len(called) == 2 and all(a is exact and b is control for a, b in called)
    assert all(len(rows) == 2 for rows in results.values())
    assert results["a"][1]["cfo_hz"] == 80_003
    assert results["a"][0]["score"] == 2 and results["b"][0]["score"] == 8


def test_missing_method_and_nonfinite_error_are_not_silent_skips():
    bank = [{"candidate_id": i, "seed_cfo_hz": 0} for i in range(2)]
    pairs = [(np.ones((2, 64)), np.ones((2, 64)))] * 2
    calls = []
    def omitted(a, b):
        calls.append(1)
        r = {"score": 1., "cfo_hz": 0., "control_cfo_hz": 0.}
        return {"a": r, "b": r} if len(calls) == 1 else {"a": r}
    with pytest.raises(ValueError, match="omitted"):
        recorded.score_common_bank(bank, pairs, omitted)
    def nonfinite(a, b):
        return {"a": {"score": float("nan"), "cfo_hz": 0., "control_cfo_hz": 0.}}
    with pytest.raises(ValueError, match="nonfinite"):
        recorded.score_common_bank(bank, pairs, nonfinite)


def test_iq_hash_and_path_are_enforced(tmp_path):
    array = np.zeros((2, 2, 2), dtype="<i2")
    path = tmp_path / "raw.npy"
    np.save(path, array)
    case = {"case_id": "test", "raw_npy": {"path": "raw.npy", "shape": list(array.shape),
                                               "sha256": recorded.digest(path)}}
    np.testing.assert_array_equal(recorded.load_iq(tmp_path, case), array)
    case["raw_npy"]["sha256"] = "sha256:wrong"
    with pytest.raises(ValueError, match="hash mismatch"):
        recorded.load_iq(tmp_path, case)
    case["raw_npy"]["path"] = "../outside.npy"
    with pytest.raises(ValueError, match="escapes"):
        recorded.load_iq(tmp_path, case)


def test_freeze_prevents_configuration_or_selection_changes(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "cases.json").write_text(json.dumps(inventory()))
    output = tmp_path / "result"
    recorded.freeze(dataset, output)
    changed = json.loads((output / "selection.json").read_text())
    changed["config"]["fft_size"] = 1024
    (output / "selection.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="frozen selection/config differs"):
        recorded.freeze(dataset, output)


def test_cached_workspace_matrices_match_direct_numerical_helper():
    _, pm, templates = recorded.numerical_helpers()
    rng = np.random.default_rng(44)
    samples = rng.normal(size=10_000) + 1j * rng.normal(size=10_000)
    rate = 2_500_000
    edge = templates.StarlinkEdge.LOWER
    exact, control = recorded.matrices(pm, samples, rate, edge, 13, 80_000)
    symbols = np.asarray(recorded.CONFIG["symbols"])
    for actual, roll in ((exact, 0), (control, templates.CONTROL_SYMBOL_ROLL)):
        reference = pm._symbol_correlations(
            samples, rate, 13, 80_000, symbols, edge=edge, symbol_roll=roll,
        ).values
        np.testing.assert_allclose(actual, reference, atol=1e-10, rtol=1e-10)
        assert not actual.flags.writeable
