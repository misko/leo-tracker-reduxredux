import json
import runpy
from pathlib import Path

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("pair_score.py")))


def row(index, start, *, receiver=0, channel=1):
    return dict(
        window_id=f"w{index}",
        acquisition_id=f"stream:sample:{index}",
        receiver=receiver,
        channel=channel,
        actual_rf_hz=11_000_000_000,
        edge="lower",
        support_start_ns=start,
        support_center_ns=start + 5,
        support_end_ns=start + 10,
    )


def test_chronological_pairing_no_orbit_fields_full_accounting():
    rows = [row(2, 200), row(0, 0), row(1, 100), row(3, 300), row(4, 400, receiver=1)]
    result = api["pair_rows"](rows)
    assert result["pairs"] == [(1, 2), (0, 3)]
    assert result["unpaired"] == [dict(index=4, reason="no-close-neighbour")]
    assert result["observations"] == 5
    reversed_result = api["pair_rows"](list(reversed(rows)))

    def physical(r, data):
        return [[data[i]["window_id"] for i in p] for p in r["pairs"]]

    assert physical(result, rows) == physical(reversed_result, list(reversed(rows)))


def test_repeated_overlapping_missing_windows_retained_unpaired():
    rows = [row(0, 0), row(1, 5, channel=2), row(2, 100), row(3, 200), row(4, 300)]
    rows[3]["acquisition_id"] = rows[2]["acquisition_id"]
    rows[4].pop("support_start_ns")
    result = api["pair_rows"](rows)
    assert not result["pairs"] and len(result["unpaired"]) == 5
    assert result["reason_counts"] == {
        "overlapping-support": 2,
        "repeated-acquisition": 2,
        "missing-support": 1,
    }


def test_boundaries_and_long_gaps_do_not_drop_observations():
    rows = [row(0, 0), row(1, 10), row(2, 3_000_000_000)]
    result = api["pair_rows"](rows)
    assert result["pairs"] == [(0, 1)] and result["unpaired"][0]["index"] == 2
    with pytest.raises(ValueError, match="Duplicate"):
        api["pair_rows"]([rows[0], rows[0]])


def test_soft_score_known_answer_clutter_and_no_hard_labels():
    weights = np.array([[0.6, 0.2], [0.3, 0.4], [0, 0]])
    z = np.array([[2, -1], [3, 4], [100, 100]])
    result = api["zero_score"](weights, z, [(0, 1)])
    assert result["pair_scores"] == pytest.approx([0.76])
    assert result["shared_label_mass"] == pytest.approx([0.26])
    assert result["unpaired_count"] == 1
    json.dumps(result, allow_nan=False)
    assert api["zero_score"](weights, z, [])["unpaired_count"] == 3
    assert api["zero_score"](weights, z, [(0, 2)])["score_sum"] == 0


def test_score_equals_finite_difference_of_normalized_pair_mixture():
    means = np.array([-0.5, 1.2])
    y = np.array([0.1, 0.8])
    pi = np.array([[0.3, 0.4], [0.2, 0.5]])
    clutter = np.array([0.3, 0.3]) / 20
    z = y[:, None] - means
    phi = np.exp(-0.5 * z * z) / np.sqrt(2 * np.pi)
    marginals = clutter + np.sum(pi * phi, axis=1)
    responsibilities = pi * phi / marginals[:, None]

    def density(rho):
        bivariate = np.exp(
            -(z[0] ** 2 - 2 * rho * z[0] * z[1] + z[1] ** 2) / (2 * (1 - rho * rho))
        ) / (2 * np.pi * np.sqrt(1 - rho * rho))
        return np.prod(marginals) + np.sum(pi[0] * pi[1] * (bivariate - phi[0] * phi[1]))

    step = 1e-5
    fd = (np.log(density(step)) - np.log(density(-step))) / (2 * step)
    assert api["zero_score"](responsibilities, z, [(0, 1)])["score_sum"] == pytest.approx(
        fd, abs=1e-10
    )


def test_invalid_responsibilities_or_pair_reuse_rejected():
    with pytest.raises(ValueError):
        api["zero_score"]([[0.7, 0.7], [0.2, 0.3]], [[1, 2], [3, 4]], [(0, 1)])
    with pytest.raises(ValueError, match="disjoint"):
        api["zero_score"]([[1], [1]], [[1], [1]], [(0, 1), (0, 1)])
    with pytest.raises(ValueError, match="integers"):
        api["zero_score"]([[1], [1]], [[1], [1]], [(0.5, 1)])


def test_known_zero_and_positive_products_pair_exchange_symmetry():
    weights = np.ones((4, 1))
    assert api["zero_score"](weights, [[1], [1], [1], [-1]], [(0, 1), (2, 3)])["score_sum"] == 0
    result = api["zero_score"](weights, np.ones((4, 1)), [(0, 1), (2, 3)])
    assert result["score_sum"] == 2 and result["shared_label_mass"] == [1, 1]
    assert api["zero_score"](weights, np.ones((4, 1)), [(1, 0), (3, 2)]) == result


def test_same_channel_different_rf_or_edge_never_pairs():
    rows = [row(i, i * 100) for i in range(4)]
    rows[1]["edge"] = "upper"
    rows[2]["actual_rf_hz"] += 1_000_000
    rows[3]["edge"] = "upper"
    rows[3]["actual_rf_hz"] += 1_000_000
    result = api["pair_rows"](rows)
    assert result["pairs"] == [] and len(result["unpaired"]) == 4
    rows[0]["edge"] = None
    with pytest.raises(ValueError, match="RF and edge"):
        api["pair_rows"](rows)
