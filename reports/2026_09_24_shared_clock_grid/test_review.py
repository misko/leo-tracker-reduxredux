"""Independent semantic checks for shared receive-time sensitivity selection."""

import importlib.util
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    "shared_clock_review", Path(__file__).with_name("run.py")
)
RUN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN)


def test_flat_profile_uses_zero_centered_deterministic_tie():
    taus = np.arange(-5.0, 5.1, 1.0)
    losses = np.ones_like(taus)
    assert taus[RUN.select_tau(losses, taus)] == 0.0


class _Search:
    REFERENCE_RF_HZ = 1.0
    LIGHT_KM_S = 1.0

    @staticmethod
    def receiver_ecef(_latitude, _longitude):
        return np.zeros(3), np.array([0.0, 0.0, 1.0])


def _engine(moving):
    engine = RUN.Engine.__new__(RUN.Engine)
    engine.search = _Search()
    grid = np.arange(-10.0, 11.0, 1.0)
    times = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    if moving:
        position = np.stack([grid, np.zeros_like(grid), np.full_like(grid, 10.0)], axis=1)
        velocity = np.tile(np.array([1.0, 0.0, 0.0]), (len(grid), 1))
        target_tau = 1.5
        query = times + target_tau
        predicted = -query / np.sqrt(query**2 + 100.0)
    else:
        position = np.tile(np.array([0.0, 0.0, 10.0]), (len(grid), 1))
        velocity = np.zeros((len(grid), 3))
        target_tau = 0.0
        predicted = np.zeros_like(times)
    track = {
        "track_id": "synthetic-track",
        "times": times,
        "measured": predicted + 17.0,
        "train": np.array([True, True, True, False, False]),
        "weight": 5,
    }
    engine.sessions = [
        {
            "session_id": "synthetic-session",
            "candidate_ids": np.array([42]),
            "grid": grid,
            "position": position[None, :, :],
            "velocity": velocity[None, :, :],
            "tracks": [track],
        }
    ]
    return engine, target_tau


def test_engine_profile_recovers_curved_shift_after_training_cfo():
    engine, expected_tau = _engine(moving=True)
    taus = np.arange(-5.0, 5.1, 0.25)
    training, _held, _assignments = engine.profile(0.0, 0.0, taus, held=True, assignments=True)
    assert taus[RUN.select_tau(training, taus)] == expected_tau


def test_actual_held_measurement_mutation_cannot_change_profiled_tau():
    engine, _expected_tau = _engine(moving=True)
    taus = np.arange(-5.0, 5.1, 0.25)
    before, _held, _assignments = engine.profile(0.0, 0.0, taus, held=True, assignments=True)
    engine.sessions[0]["tracks"][0]["measured"][~engine.sessions[0]["tracks"][0]["train"]] += 1e6
    after, _held, _assignments = engine.profile(0.0, 0.0, taus, held=True, assignments=True)
    np.testing.assert_allclose(after, before)
    assert RUN.select_tau(after, taus) == RUN.select_tau(before, taus)


def test_constant_doppler_profile_is_cfo_degenerate_and_prefers_zero():
    engine, _expected_tau = _engine(moving=False)
    taus = np.arange(-5.0, 5.1, 0.25)
    training, _held, _assignments = engine.profile(0.0, 0.0, taus, held=True, assignments=True)
    np.testing.assert_allclose(training, training[0])
    assert taus[RUN.select_tau(training, taus)] == 0.0


def test_sensitivity_boundary_is_preserved_not_relabelled_as_interior():
    taus = np.arange(-5.0, 5.1, 1.0)
    losses = (taus - 7.0) ** 2
    chosen = float(taus[RUN.select_tau(losses, taus)])
    assert chosen == 5.0
    assert chosen in (-5.0, 5.0)


def test_search_source_has_no_reference_coordinate_constant():
    source = Path(__file__).with_name("run.py").read_text()
    assert "REFERENCE =" not in source
    assert "reference_latitude" not in source
