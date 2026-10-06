"""T1-AT discovery/selection at an inferred regional calibration hypothesis."""

import time
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from leo.analysis.regional_position_score import predict_orbits, zero_sum_basis
from leo.analysis.t1_at import select_timing_modes
from leo.analysis.t1_at_discovery import discover_window_modes


@dataclass(frozen=True)
class AssociationWindow:
    candidate_id: int
    window_id: str
    receiver_id: int
    channel: int
    receive_time_s: float


@dataclass(frozen=True)
class RegionalAssociation:
    selected_indices: tuple[int, ...]
    initial_vector: np.ndarray
    selection: dict
    mode_count: int


def associate_calibration(observations, bank, prior, calibration, *, maximum_seconds=60.0):
    """Freeze one fitted-c association for both final score models and RF arms.

    The zero-c arm is a final-score ablation. Upstream calibration and discrete
    selection retain fitted c; this is recorded by the eventual result contract.
    """
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("invalid association time budget")
    begun = time.monotonic()
    point = calibration.postfit.vector[:2]
    coefficient = calibration.postfit.vector[6]
    correction = (
        calibration.receiver_baseline_hz
        + coefficient * (observations.rf_hz - observations.rf_center_hz) / 1e9
    )

    @lru_cache(maxsize=4)
    def selected_bank(indices):
        return bank.select(list(indices))

    def predict(arm, indices, offset):
        subset = selected_bank(tuple(int(i) for i in indices))
        prediction, visible, _, timing = predict_orbits(
            subset, observations, prior, point, np.full(len(indices), offset)
        )
        # Upstream calibration remains fitted-c for the final-score ablation.
        return prediction + correction[:, None], visible, timing

    ids = tuple(range(len(observations.window_ids)))
    pool = discover_window_modes(
        observations.measured_hz,
        observations.window_ids,
        ids,
        bank.numbers,
        predict,
        maximum_seconds=maximum_seconds,
        arms=("fitted-c",),
    )
    windows = tuple(
        AssociationWindow(
            i,
            window,
            int(observations.receiver[i]),
            int(observations.channel[i]),
            float(observations.times_s[i]),
        )
        for i, window in enumerate(observations.window_ids)
    )
    remaining = maximum_seconds - (time.monotonic() - begun)
    if remaining <= 0:
        raise TimeoutError("regional discovery consumed association time budget")
    modes = pool["fitted-c"]
    selection = select_timing_modes(windows, modes, maximum_seconds=remaining)
    satellites = sorted(selection["final"]["satellites"], key=lambda s: s["catalog_number"])
    if len(satellites) < 2:
        raise ValueError("fewer than two selected satellites for C0/V16 comparison")
    lookup = {int(number): i for i, number in enumerate(bank.numbers)}
    indices = tuple(lookup[s["catalog_number"]] for s in satellites)
    shifts = np.array([s["absolute_timing_s"] for s in satellites])
    vector = np.zeros(8 + len(indices) - 1)
    vector[:2], vector[6] = point, coefficient
    common = float(np.clip(shifts.mean(), -10, 10))
    shifts += common - shifts.mean()
    shifts *= min(1, 20 / max(20, float(np.max(abs(shifts)))))
    vector[7], vector[8:] = shifts.mean(), zero_sum_basis(len(indices)).T @ shifts
    return RegionalAssociation(indices, vector, selection, len(modes))
