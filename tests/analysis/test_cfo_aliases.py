from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.cfo_aliases import (
    CfoAliasObservation,
    fit_cfo_alias_trajectory,
    select_cfo_alias_degree,
)


def _duplicated_quadratic(*, with_noise: bool = False) -> tuple[CfoAliasObservation, ...]:
    spacing = 1.0 / 4.4e-6
    result = []
    for index, time_s in enumerate(np.linspace(0.0, 10.0, 101)):
        physical = 250_000.0 - 2_600.0 * time_s - 130.0 * time_s**2
        alias = spacing if index % 2 else 0.0
        noise = 25.0 * np.sin(index * 1.7) if with_noise else 0.0
        result.append(
            CfoAliasObservation(f"o-{index:03d}", float(time_s), physical + alias + noise)
        )
    return tuple(result)


def test_symbol_rate_duplicate_collapses_to_one_quadratic() -> None:
    spacing = 1.0 / 4.4e-6
    fit = fit_cfo_alias_trajectory(
        _duplicated_quadratic(),
        alias_spacing_hz=spacing,
        polynomial_degree=2,
    )

    assert fit.residual_rms_hz < 1e-6
    assert set(fit.alias_indices) == {0, 1}
    assert fit.coefficients_hz == pytest.approx((-130.0, -2_600.0, 250_000.0))


def test_alias_fit_is_permutation_invariant() -> None:
    observations = _duplicated_quadratic()
    forward = fit_cfo_alias_trajectory(
        observations,
        alias_spacing_hz=1.0 / 4.4e-6,
        polynomial_degree=2,
    )
    reverse = fit_cfo_alias_trajectory(
        tuple(reversed(observations)),
        alias_spacing_hz=1.0 / 4.4e-6,
        polynomial_degree=2,
    )

    assert reverse == forward


def test_degree_selection_prefers_quadratic_truth() -> None:
    selected, fits = select_cfo_alias_degree(
        _duplicated_quadratic(with_noise=True), alias_spacing_hz=1.0 / 4.4e-6
    )

    assert tuple(item.polynomial_degree for item in fits) == (1, 2, 3)
    assert selected.polynomial_degree == 2


@pytest.mark.parametrize("spacing", [0.0, -1.0, float("nan")])
def test_invalid_alias_spacing_rejects(spacing: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        fit_cfo_alias_trajectory(
            _duplicated_quadratic(),
            alias_spacing_hz=spacing,
            polynomial_degree=2,
        )
