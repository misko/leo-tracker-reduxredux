import math

import pytest

from tools.rx_empirical_background import fit, log_density

ROWS = [
    {"counts": [0, 0], "frequencies": [[], []], "rate_hz": 5_000_000},
    {"counts": [1, 0], "frequencies": [[0.1], []], "rate_hz": 5_000_000},
    {"counts": [0, 2], "frequencies": [[], [0.2, 0.8]], "rate_hz": 10_000_000},
    {"counts": [1, 1], "frequencies": [[0.9], [0.4]], "rate_hz": 10_000_000},
]


def _count_mass(model, maximum):
    total = 0.0
    for left in range(maximum + 1):
        for right in range(maximum + 1):
            row = {
                "counts": [left, right],
                "frequencies": [[0.0] * left, [0.0] * right],
                "rate_hz": 7,
            }
            log_set_density = log_density(model, row)
            total += math.exp(log_set_density - math.lgamma(left + 1) - math.lgamma(right + 1))
    return total


@pytest.mark.parametrize("mode", ["joint", "rate_joint"])
def test_count_mass_and_infinite_tail_normalize(mode) -> None:
    model = fit(ROWS, mode)
    assert _count_mass(model, 80) == pytest.approx(1.0, abs=1e-12)


def test_poisson_set_density_matches_independent_formula() -> None:
    model = fit(ROWS, "poisson")
    row = {"counts": [3, 2], "frequencies": [[0.1] * 3, [0.4] * 2], "rate_hz": 123}
    expected = sum(
        -mean + count * math.log(mean)
        for mean, count in zip(model["pooled_means"], row["counts"], strict=True)
    )
    assert log_density(model, row) == pytest.approx(expected)


@pytest.mark.parametrize(
    "mode", ["poisson", "joint", "joint_frequency", "rate_joint", "rate_joint_frequency"]
)
def test_zero_and_large_counts_have_finite_density(mode) -> None:
    model = fit(ROWS, mode)
    empty = {"counts": [0, 0], "frequencies": [[], []], "rate_hz": 5_000_000}
    large = {
        "counts": [750, 610],
        "frequencies": [[0.25] * 750, [0.75] * 610],
        "rate_hz": 5_000_000,
    }
    assert math.isfinite(log_density(model, empty))
    assert math.isfinite(log_density(model, large))


def test_frequency_density_wraps_circle_and_ignores_candidate_order() -> None:
    model = fit(ROWS, "joint_frequency")
    first = {"counts": [2, 0], "frequencies": [[0.1, 0.9], []], "rate_hz": 1}
    permuted = {"counts": [2, 0], "frequencies": [[1.9, -0.9], []], "rate_hz": 1}
    assert log_density(model, first) == pytest.approx(log_density(model, permuted))


def test_receiver_symmetric_data_give_symmetric_density() -> None:
    symmetric = [
        {"counts": [1, 0], "frequencies": [[0.2], []], "rate_hz": 5},
        {"counts": [0, 1], "frequencies": [[], [0.2]], "rate_hz": 5},
    ]
    model = fit(symmetric, "joint_frequency")
    left = {"counts": [1, 0], "frequencies": [[0.2], []], "rate_hz": 5}
    right = {"counts": [0, 1], "frequencies": [[], [0.2]], "rate_hz": 5}
    assert log_density(model, left) == pytest.approx(log_density(model, right))


def test_unseen_rate_falls_back_to_pooled_count_and_frequency() -> None:
    rate_model = fit(ROWS, "rate_joint_frequency")
    pooled_model = fit(ROWS, "joint_frequency")
    row = {"counts": [1, 1], "frequencies": [[0.1], [0.8]], "rate_hz": 99_000_000}
    assert log_density(rate_model, row) == pytest.approx(log_density(pooled_model, row))


def test_fit_is_deterministic_json_data() -> None:
    assert fit(list(reversed(ROWS)), "rate_joint_frequency") == fit(ROWS, "rate_joint_frequency")
