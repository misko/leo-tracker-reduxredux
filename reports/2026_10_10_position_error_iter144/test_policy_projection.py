import numpy as np
from catalogue_policy import DAY_NS, select_earlier_changed
from projection import decompose


def test_shared_causal_first_changed_rule_and_missing_accounting():
    original = dict(provider="p", collected_utc_ns=2 * DAY_NS, sha256="original")
    refs = [dict(provider="p", collected_utc_ns=2 * DAY_NS - i, sha256=str(i)) for i in (1, 2, 3)]
    refs += [dict(provider="other", collected_utc_ns=2 * DAY_NS - 1, sha256="other")]
    records = {
        "1": {1: ("one", "two")},
        "2": {1: ("new", "two"), 2: None},
        "3": {1: ("older", "two"), 2: ("a", "b")},
    }
    result = select_earlier_changed(
        original, {1: ("one", "two"), 2: ("a", "b")}, [1, 2], refs, records
    )
    assert result["selected"]["sha256"] == "2"
    assert result["inspected"][0]["candidates"]["missing"] == [2]
    assert result["inspected"][1]["candidates"]["malformed"] == [2]


def test_ten_distinct_payload_and_24h_caps():
    original = dict(provider="p", collected_utc_ns=2 * DAY_NS, sha256="original")
    refs = [
        dict(provider="p", collected_utc_ns=2 * DAY_NS - i, sha256=str(i)) for i in range(1, 12)
    ]
    refs += [dict(provider="p", collected_utc_ns=DAY_NS - 1, sha256="too-old")]
    records = {str(i): {1: ("a", "b")} for i in range(1, 11)}
    records["11"] = {1: ("changed", "b")}
    result = select_earlier_changed(original, {1: ("a", "b")}, [1], refs, records)
    assert result["selected"] is None and len(result["inspected"]) == 10


def test_weighted_orthogonal_energy_and_rescaling():
    basis = np.eye(4)
    nuisance, spatial = basis[:, :1], basis[:, 1:3]
    delta = basis @ np.array([2, 3, 4, 5])
    result = decompose(delta, spatial, nuisance, np.ones(4))
    assert result["nuisance_energy"] == 4
    assert result["spatial_conditional_energy"] == 25
    assert result["outside_energy"] == 25
    other = decompose(delta, spatial, nuisance * 1e-30, np.ones(4))
    assert result == other


def test_confounded_spatial_and_zero_weight_rows():
    spatial = np.array([[1, 1], [1, 1], [0, 0.0]])
    nuisance = np.array([[1], [1], [0.0]])
    result = decompose([2, 2, 999], spatial, nuisance, [1, 1, 0])
    assert result["positive_weight_rows"] == 2
    assert result["outside_energy"] < 1e-28
    assert result["spatial_conditional_energy"] < 1e-28
    zero = decompose([2, 2, 999], spatial, nuisance, [0, 0, 0])
    assert zero["total_weighted_energy"] == 0


def test_partial_rows_keep_original_rank_tolerance():
    result = decompose([1, 2], np.eye(2), np.zeros((2, 0)), [1, 1], original_row_count=10000)
    assert result["rtol"] == np.finfo(float).eps * 10000
    assert result["original_row_count"] == 10000 and result["retained_rows"] == 2
