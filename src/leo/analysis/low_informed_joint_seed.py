"""Low-fit initialization for the existing joint free-contrast objective."""

import numpy as np

from leo.analysis.channel_group_calibration import project_calibration_seed
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.sequential_group_calibration import physical_shift_seed


def low_informed_joint_seed(low_model, low_fit, high_correction, high_observations,
                            target_model, *, arm):
    """Transport a stationary own-arm low fit, without retaining it as a prior.

    The physical high-minus-low contrast is only an initializer. The caller fits
    the existing joint model with geometry, common correction, timings and
    contrasts free. No low observations or precision are appended to that model.
    """
    if arm not in {"fitted-c", "zero-c"}:
        raise ValueError("unknown RF arm")
    if not low_fit.get("converged"):
        raise ValueError("stationary own-arm low fit required")
    if low_model.group_count or np.any(low_model.observations.channel >= 5):
        raise ValueError("common-only low-channel source required")
    if target_model.group_count != len(target_model.frame.receivers):
        raise ValueError("existing constant free-contrast target required")
    if not set(target_model.frame.receivers) <= set(low_model.observations.receiver):
        raise ValueError("target receiver lacks low-stage support")
    low_vector = np.asarray(low_fit["vector"], float)
    if arm == "zero-c" and low_vector[6] != 0:
        raise ValueError("zero-c requires its own exact zero-c low fit")
    frozen = freeze_group_calibration(low_model, low_fit)
    shifts_hz = physical_shift_seed(
        high_correction, frozen, high_observations, target_model.frame.receivers
    )
    obs = target_model.observations
    correction = frozen.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
    for receiver, shift in zip(target_model.frame.receivers, shifts_hz, strict=True):
        correction += (obs.receiver == receiver) * (obs.channel >= 5) * shift
    projected = project_calibration_seed(target_model, correction - target_model.base.baseline)
    coefficients = projected["coefficients"].copy()
    if arm == "zero-c":
        coefficients[4] = 0.0
    numbers = low_model.bank.numbers.tolist()
    if len(numbers) != len(set(numbers)) or set(numbers) != set(target_model.bank.numbers):
        raise ValueError("low and joint candidate identities differ")
    timings = low_vector[7] + low_model.basis @ low_vector[8:]
    by_number = dict(zip(numbers, timings, strict=True))
    timings = np.asarray([by_number[int(number)] for number in target_model.bank.numbers])
    vector = np.r_[low_vector[:2], coefficients[:5], timings.mean(),
                   target_model.basis.T @ (timings - timings.mean())]
    nuisance = coefficients[5:]
    residual = target_model.correction(vector, nuisance) - correction
    return dict(
        vector=vector, nuisance=nuisance,
        initializer=dict(
            source="stationary-own-arm-low-fit-and-original-high-physical-proposal",
            receivers=list(target_model.frame.receivers), physical_shift_seed_hz=shifts_hz,
            projection_rms_hz=float(np.sqrt(np.mean(residual**2))),
            projection_maximum_abs_hz=float(np.max(abs(residual))),
            projection_active_bounds=projected["active_bounds"],
            low_used_as_prior=False, low_covariance_used=False,
        ),
    )
