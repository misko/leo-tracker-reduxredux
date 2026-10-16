"""Prediction-only likelihood for trained position, timings and calibration."""

from dataclasses import dataclass

import numpy as np

from leo.analysis.frozen_group_calibration import FrozenGroupCalibration, readonly
from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.analysis.regional_position_score import zero_sum_basis


@dataclass(frozen=True)
class FrozenGroupPosition:
    catalogue_numbers: tuple[int, ...]
    position_km: np.ndarray
    satellite_shifts_s: np.ndarray
    correction: FrozenGroupCalibration

    def __post_init__(self):
        numbers = self.catalogue_numbers
        point, shifts = readonly(self.position_km), readonly(self.satellite_shifts_s)
        if (
            not numbers
            or len(set(numbers)) != len(numbers)
            or point.shape != (2,)
            or shifts.shape != (len(numbers),)
            or not np.isfinite(point).all()
            or not np.isfinite(shifts).all()
        ):
            raise ValueError("frozen position/timing/candidate dimensions differ")
        object.__setattr__(self, "position_km", point)
        object.__setattr__(self, "satellite_shifts_s", shifts)


def freeze_group_position(bank, fit, correction):
    numbers = tuple(map(int, bank.numbers))
    vector = np.asarray(fit["vector"])
    if vector.shape != (7 + len(numbers),):
        raise ValueError("trained vector does not belong to this candidate bank")
    return FrozenGroupPosition(
        numbers, vector[:2], vector[7] + zero_sum_basis(len(numbers)) @ vector[8:], correction
    )


def score_frozen_group_position(
    state, observations, bank, prior, score, *, candidate_diagnostics=False, likelihood_port=None
):
    """Score every held window; add no new fitted prior, offset or selection."""
    if tuple(map(int, bank.numbers)) != state.catalogue_numbers:
        raise ValueError("held propagation bank must preserve trained candidate identity/order")
    prediction, visible, _, _ = predict_orbits(
        bank, observations, prior, state.position_km, state.satellite_shifts_s, derivatives=False
    )
    prediction += state.correction.predict(
        observations.times_s, observations.rf_hz, observations.receiver, observations.channel >= 5
    )[:, None]
    scorer = likelihood if likelihood_port is None else likelihood_port
    terms = scorer(observations.measured_hz, prediction, visible, score)
    mass = float(terms.responsibilities.sum())
    cells = {}
    candidate_cells = {}
    for receiver in (0, 1):
        for label, high in (("low", False), ("high", True)):
            mask = (observations.receiver == receiver) & ((observations.channel >= 5) == high)
            count = int(mask.sum())
            signal = float(terms.responsibilities[mask].sum())
            cells[f"rx{receiver}-{label}"] = dict(
                windows=count,
                signal_windows=signal,
                signal_fraction=signal / count if count else None,
                clutter_windows=float(terms.clutter_probability[mask].sum()),
                posterior_rms_hz=float(
                    np.sqrt(
                        np.sum(terms.responsibilities[mask] * terms.residual_hz[mask] ** 2) / signal
                    )
                )
                if signal
                else None,
            )
            if candidate_diagnostics:
                candidate_cells[f"rx{receiver}-{label}"] = terms.responsibilities[mask].sum(axis=0)
    result = dict(
        windows=len(observations.window_ids),
        window_ids=observations.window_ids,
        frequency_nll=float(terms.nll),
        frequency_nll_per_window=float(terms.nll / len(observations.window_ids)),
        posterior_rms_hz=float(
            np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
        )
        if mass
        else None,
        signal_windows=mass,
        clutter_windows=float(terms.clutter_probability.sum()),
        visible_candidates_min=int(visible.sum(axis=1).min()),
        visible_candidates_max=int(visible.sum(axis=1).max()),
        fitted_held_parameters=0,
        prior_penalty=0.0,
        receiver_group_cells=cells,
    )
    if candidate_diagnostics:
        weights = terms.responsibilities
        totals = weights.sum(axis=0)
        result["candidate_diagnostics"] = dict(
            interpretation=(
                "Conditional frequency-model support; not independent satellite identity"
            ),
            posterior_threshold=0.5,
            windows_candidate_posterior_over_half=int((weights.max(axis=1) > 0.5).sum()),
            windows_signal_over_half_but_no_candidate_over_half=int(
                ((weights.sum(axis=1) > 0.5) & (weights.max(axis=1) <= 0.5)).sum()
            ),
            candidates=[
                dict(
                    catalogue_number=number,
                    signal_windows=float(total),
                    windows_posterior_over_half=int((weights[:, index] > 0.5).sum()),
                    posterior_rms_hz=float(
                        np.sqrt(
                            np.sum(weights[:, index] * terms.residual_hz[:, index] ** 2) / total
                        )
                    )
                    if total
                    else None,
                    receiver_group_signal_windows={
                        label: float(values[index]) for label, values in candidate_cells.items()
                    },
                )
                for index, (number, total) in enumerate(
                    zip(state.catalogue_numbers, totals, strict=True)
                )
            ],
        )
    return result
