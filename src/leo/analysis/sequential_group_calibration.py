"""Training-only low -> high shift -> all-channel calibration experiment.

The high stage locks the entire low correction function and geometry. Only
satellite timings and one physical high-minus-low offset per supported receiver
move. The final stage holds that offset exactly, rather than using it as a seed
for a freely refitted group model. No location reference enters these functions.
"""

from copy import copy
from dataclasses import dataclass

import numpy as np

from leo.analysis.channel_group_calibration import (
    GroupCalibrationFrame,
    GroupCalibrationObjective,
    fit_group_calibration,
    project_calibration_seed,
)
from leo.analysis.frozen_group_calibration import freeze_group_calibration, readonly
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ, circular


@dataclass(frozen=True)
class SequentialShift:
    """Alias-branch-fixed receiver offsets, learned with low geometry held fixed."""

    receivers: tuple[int, ...]
    offsets_hz: np.ndarray

    def __post_init__(self):
        offsets = readonly(self.offsets_hz)
        if (
            len(set(self.receivers)) != len(self.receivers)
            or not set(self.receivers) <= {0, 1}
            or offsets.shape != (len(self.receivers),)
            or not np.isfinite(offsets).all()
            or np.any(abs(offsets) > ALIAS_HZ / 2 + 1e-7)
        ):
            raise ValueError("invalid supported high-minus-low shift")
        object.__setattr__(self, "offsets_hz", offsets)

    def predict(self, receiver, high_group):
        rx, high = np.asarray(receiver), np.asarray(high_group)
        if rx.ndim != 1 or high.shape != rx.shape or high.dtype != bool:
            raise ValueError("aligned receiver and boolean channel-group rows required")
        if not set(rx) <= {0, 1} or not set(rx[high]) <= set(self.receivers):
            raise ValueError("high-group receiver has no learned low/high shift support")
        return sum(
            (rx == r) * high * offset
            for r, offset in zip(self.receivers, self.offsets_hz, strict=True)
        ) if self.receivers else np.zeros(len(rx))


@dataclass(frozen=True)
class FrozenSequentialCalibration:
    common: object
    shift: SequentialShift

    def predict(self, times_s, rf_hz, receiver, high_group):
        return self.common.predict(times_s, rf_hz, receiver, high_group) + self.shift.predict(
            receiver, high_group
        )


class SequentialHighObjective(GroupCalibrationObjective):
    """Private fit adapter: uncentred high offsets, with common correction locked.

    The core design is zero: the legacy calibration coordinates therefore have
    no physical effect or derivatives. Satellite responsibilities and timing
    remain independent of the low-stage assignments.
    """

    def __init__(self, high_base, frozen_low, low_receivers, *, sigma_hz=50_000.0):
        obs = high_base.observations
        if np.any(obs.channel < 5):
            raise ValueError("high stage requires CH5-8 observations")
        receivers = tuple(sorted(set(obs.receiver)))
        if not set(receivers) <= set(low_receivers):
            raise ValueError("high-group receiver lacks low-stage correction support")
        baseline = frozen_low.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
        base = Hard60Objective(
            obs, high_base.bank, high_base.prior, high_base.score,
            receiver_baseline_hz=baseline,
        )
        base.design = np.zeros_like(base.design)
        super().__init__(base, obs.channel >= 5, sigma_hz=sigma_hz, enabled=False)
        # This adapter's coefficients are physical offsets, not centred contrasts.
        self.frame = GroupCalibrationFrame(receivers, tuple(0.5 for _ in receivers))
        self.offset_count = self.group_count = len(receivers)
        self.group_design = np.column_stack([obs.receiver == r for r in receivers]).astype(float)
        self.group_scales = np.full(len(receivers), 5000.0)
        self.group_limits = np.full(len(receivers), ALIAS_HZ / 2)
        self.group_precision = self.precision = np.eye(len(receivers)) / sigma_hz**2
        self.initial_nuisance = np.zeros(len(receivers))


def physical_shift_seed(high_correction, low_correction, observations, receivers):
    """Initialize from functions at original high rows, never subtract intercepts.

    An overall alias gauge is reduced to the declared principal branch. A circular
    mean is used so values straddling that branch do not average to zero.
    """
    args = (
        observations.times_s, observations.rf_hz, observations.receiver,
        observations.channel >= 5,
    )
    difference = circular(high_correction.predict(*args) - low_correction.predict(*args))
    offsets = []
    for receiver in receivers:
        phase = difference[observations.receiver == receiver] * (2 * np.pi / ALIAS_HZ)
        if not len(phase):
            raise ValueError("shift seed receiver has no high observations")
        phasor = np.mean(np.exp(1j * phase))
        if abs(phasor) < 1e-8:
            raise ValueError("physical high/low seed difference has no resolved alias gauge")
        offsets.append(float(np.angle(phasor) * ALIAS_HZ / (2 * np.pi)))
    return np.asarray(offsets)


def offset_timing_diagnostic(model, fit):
    """Report likelihood-only local offset/timing confounding, excluding priors.

    Satellite timing columns have disjoint candidate responsibility rows. Their
    weighted projection therefore needs no large dense design or factorization.
    A fraction near one means timing can imitate the receiver offset locally.
    It is a diagnostic, never a new inference/model-selection criterion.
    """
    vector = np.asarray(fit["vector"])
    _, _, _, timing = predict_orbits(
        model.bank, model.observations, model.prior, vector[:2],
        vector[7] + model.basis @ vector[8:],
    )
    _, _, _, terms = model.evaluate_joint(vector, fit["nuisance"])
    weight = terms.responsibilities / model.score.sigma_hz**2
    norms = np.sum(weight * timing**2, axis=0)
    result = {}
    for receiver in model.frame.receivers:
        mask = model.observations.receiver == receiver
        mass = float(terms.responsibilities[mask].sum())
        cross = np.sum(weight[mask] * timing[mask], axis=0)
        norm = float(weight[mask].sum())
        explained = np.sum(np.divide(cross**2, norms, out=np.zeros_like(norms), where=norms > 0))
        result[f"rx{receiver}"] = dict(
            windows=int(mask.sum()), signal_windows=mass,
            offset_information_hz_minus_2=norm,
            timing_explained_offset_fraction=float(np.clip(explained / norm, 0, 1))
            if norm else None,
        )
    return result


def fixed_shift_objective(all_base, shift):
    """Free common calibration/position/timing while keeping learned contrast fixed."""
    base = copy(all_base)
    obs = base.observations
    base.baseline = np.asarray(base.baseline) + shift.predict(obs.receiver, obs.channel >= 5)
    return GroupCalibrationObjective(base, obs.channel >= 5, enabled=False)


def freeze_sequential_calibration(model, fit, shift):
    """Export common and fixed contrast separately and prove original-row closure."""
    if model.group_count:
        raise ValueError("sequential final model must have no free contrast parameters")
    common_base = copy(model.base)
    obs = model.observations
    common_base.baseline = model.base.baseline - shift.predict(
        obs.receiver, obs.channel >= 5
    )
    common_model = GroupCalibrationObjective(common_base, obs.channel >= 5, enabled=False)
    result = FrozenSequentialCalibration(freeze_group_calibration(common_model, fit), shift)
    np.testing.assert_allclose(
        result.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5),
        model.correction(fit["vector"], fit["nuisance"]), atol=1e-6, rtol=0,
    )
    return result


def fit_sequential_path(
    low_model, high_base, all_base, low_seed, high_seed, all_seed, *,
    arm="fitted-c", seconds=20.0, iterations=600,
    low_nuisance=None, high_shift_seed=None, local_center=None, local_radius_km=None,
    high_correction_seed=None, stage_fit=None,
):
    """One matched training geometry hypothesis; require stationary stages.

    Call for every declared training-only geometry start, then choose the lowest
    stationary final objective. Failed stages are explicit failures, never donors.
    """
    if np.any(low_model.observations.channel >= 5) or low_model.group_count:
        raise ValueError("low stage requires a CH1-4 common-only calibration model")
    if not np.array_equal(low_model.bank.numbers, high_base.bank.numbers) or not np.array_equal(
        low_model.bank.numbers, all_base.bank.numbers
    ):
        raise ValueError("sequential stages require the same ordered candidate bank")
    options = dict(arm=arm, seconds=seconds, iterations=iterations)
    local = dict(local_center=local_center, local_radius_km=local_radius_km)

    def run(stage, model, vector, nuisance, **kwargs):
        if stage_fit is not None:
            return stage_fit(stage, model, vector, nuisance, kwargs)
        return fit_group_calibration(model, vector, nuisance, **kwargs)

    low = run("low", low_model, low_seed, low_nuisance, **options, **local)
    if not low["converged"]:
        return dict(status="low-nonstationary", low=low)
    frozen_low = freeze_group_calibration(low_model, low)
    high_model = SequentialHighObjective(
        high_base, frozen_low, set(low_model.observations.receiver)
    )
    seed = np.asarray(high_seed, float).copy()
    seed[:2], seed[2:7] = low["vector"][:2], 0
    shift_seed = high_model.initial_nuisance if high_shift_seed is None else high_shift_seed
    if high_correction_seed is not None:
        shift_seed = physical_shift_seed(
            high_correction_seed, frozen_low, high_base.observations, high_model.frame.receivers
        )
    high = run("high", high_model, seed, shift_seed, fixed_position=True, **options)
    high["offset_parameterization"] = "uncentred-high-minus-low"
    high["training_high_fractions"] = None
    if not high["converged"]:
        return dict(status="high-nonstationary", low=low, high=high)
    high["offset_timing_diagnostic"] = offset_timing_diagnostic(high_model, high)
    shift = SequentialShift(high_model.frame.receivers, high["group_offsets_hz"])
    final_model = fixed_shift_objective(all_base, shift)
    obs = all_base.observations
    target = frozen_low.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
    # Projection excludes the fixed shift, which is already in final baseline.
    target = target - all_base.baseline
    carried = project_calibration_seed(final_model, target)
    final_seed = np.asarray(all_seed, float).copy()
    final_seed[:2] = low["vector"][:2]
    final_seed[2:7] = carried["coefficients"][:5]
    final_seed[7:] = high["vector"][7:]
    nuisance = carried["coefficients"][5:]
    final = run("final", final_model, final_seed, nuisance, **options, **local)
    frozen = freeze_sequential_calibration(final_model, final, shift)
    return dict(
        status="complete" if final["converged"] else "final-nonstationary",
        low=low, high=high, final=final, shift=shift, frozen=frozen,
        final_model=final_model, calibration_projection=carried,
    )
