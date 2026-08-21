from __future__ import annotations

import random

import numpy as np

from leo.analysis.starlink.seeded_alias_em import (
    SeededAliasObservation,
    SeedTrajectory,
    fit_seeded_alias_em,
)

_SPACING = 2_500_000 / 11


def _fixture(*, permute: bool = False):
    rng = np.random.default_rng(20260821)
    observations = []
    selected_ids = []
    for index, time_s in enumerate(np.arange(0.0, 4.0, 0.05)):
        expected = 72_000.0 - 4_800.0 * time_s + 24.0 * time_s**2
        alias_index = (-1, 0, 1, 0)[index % 4]
        good_id = f"good-{index:03d}"
        selected_ids.append(good_id)
        observations.append(
            SeededAliasObservation(
                good_id,
                index * 125_000,
                float(time_s),
                float(expected + alias_index * _SPACING + rng.normal(0.0, 80.0)),
                0.4,
            )
        )
        observations.append(
            SeededAliasObservation(
                f"weak-{index:03d}",
                index * 125_000,
                float(time_s),
                float(expected + 14_000.0),
                0.01,
            )
        )
    if permute:
        random.Random(42).shuffle(observations)
    seed = SeedTrajectory(
        trajectory_id="seed-a",
        polynomial_degree=2,
        reference_time_s=0.0,
        coefficients_hz=(24.0, -4_800.0, 72_000.0),
        start_s=0.0,
        end_s=3.95,
        observation_ids=tuple(
            item.observation_id
            for item in observations
            if item.observation_id.startswith(("good-", "weak-"))
        ),
    )
    return tuple(observations), seed, tuple(selected_ids)


def test_seeded_alias_em_recovers_integer_lifts_and_one_candidate_per_probe() -> None:
    observations, seed, expected_ids = _fixture()

    fit = fit_seeded_alias_em(observations, seed, alias_spacing_hz=_SPACING)

    assert fit.converged
    assert fit.selected_probe_count == 80
    assert tuple(item.observation_id for item in fit.points) == expected_ids
    assert len({item.sample_start for item in fit.points}) == len(fit.points)
    assert {item.alias_index for item in fit.points} == {-1, 0, 1}
    assert fit.residual_rms_hz < 120.0
    assert fit.maximum_absolute_residual_hz < 300.0
    assert np.allclose(fit.coefficients_hz, (24.0, -4_800.0, 72_000.0), atol=50.0)


def test_seeded_alias_em_is_deterministic_under_input_permutation() -> None:
    observations, seed, _ = _fixture()
    permuted, permuted_seed, _ = _fixture(permute=True)

    left = fit_seeded_alias_em(observations, seed, alias_spacing_hz=_SPACING)
    right = fit_seeded_alias_em(permuted, permuted_seed, alias_spacing_hz=_SPACING)

    assert left == right


def test_seeded_alias_em_does_not_absorb_observations_outside_seed_membership() -> None:
    observations, seed, _ = _fixture()
    foreign = SeededAliasObservation("foreign", 99, 1.0, 67_224.0, 100.0)

    fit = fit_seeded_alias_em(observations + (foreign,), seed, alias_spacing_hz=_SPACING)

    assert "foreign" not in {item.observation_id for item in fit.points}
    assert fit.seed_trajectory_id == seed.trajectory_id


def test_seeded_alias_em_fails_closed_on_missing_seed_evidence() -> None:
    observations, seed, _ = _fixture()

    try:
        fit_seeded_alias_em(observations[:-1], seed, alias_spacing_hz=_SPACING)
    except ValueError as error:
        assert "absent" in str(error)
    else:
        raise AssertionError("missing seed evidence was accepted")
