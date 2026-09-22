"""Truth-free paired-receiver Doppler factor with explicit nuisance offsets.

The factor uses no phase, gain, beam, or installed-orientation calibration.
Simultaneous receiver copies share one visit's total weight.  Its useful
location information therefore comes from additional temporal Doppler shape,
not from counting a copied signal as another independent observation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_REFERENCE_RF_HZ = 11_200_000_000.0
_LIGHT_KM_S = 299_792.458


def differential_doppler_upper_bound_hz(
    carrier_hz: float, baseline_m: float, relative_speed_m_s: float, slant_range_m: float
) -> float:
    """First-order far-field bound; a mechanical baseline is not a measured phase baseline."""
    values = (carrier_hz, baseline_m, relative_speed_m_s, slant_range_m)
    if not np.all(np.isfinite(values)) or min(values) <= 0:
        raise ValueError("geometry bound inputs must be positive and finite")
    return carrier_hz / 299_792_458.0 * baseline_m * relative_speed_m_s / slant_range_m


@dataclass(frozen=True, slots=True)
class PairedDopplerFactor:
    observed_hz: np.ndarray
    receiver_id: np.ndarray
    visit_id: np.ndarray
    training: np.ndarray
    pairing_authority: str

    def __post_init__(self) -> None:
        observed = np.asarray(self.observed_hz, dtype=float)
        receiver = np.asarray(self.receiver_id)
        visit = np.asarray(self.visit_id)
        training = np.asarray(self.training)
        object.__setattr__(self, "observed_hz", observed)
        object.__setattr__(self, "receiver_id", receiver)
        object.__setattr__(self, "visit_id", visit)
        object.__setattr__(self, "training", training)
        arrays = (receiver, visit, training)
        if observed.ndim != 1 or len(observed) < 4 or any(
            np.asarray(value).shape != observed.shape for value in arrays
        ):
            raise ValueError("paired factor arrays must be matching nonempty vectors")
        if np.asarray(self.training).dtype != bool or not np.all(np.isfinite(observed)):
            raise ValueError("observations must be finite and training must be boolean")
        if min(np.sum(self.training), np.sum(~self.training)) < 1:
            raise ValueError("paired factor needs training and held-out visits")
        if not self.pairing_authority:
            raise ValueError("explicit shared-source pairing authority is required")
        for visit in np.unique(self.visit_id):
            selected = np.asarray(self.visit_id) == visit
            if len(np.unique(np.asarray(self.training)[selected])) != 1:
                raise ValueError("one paired visit cannot cross the training boundary")
        for receiver in np.unique(self.receiver_id):
            if not np.any((np.asarray(self.receiver_id) == receiver) & self.training):
                raise ValueError("every receiver path needs training support for its offset")


def _visit_weights(factor: PairedDopplerFactor) -> np.ndarray:
    weights = np.empty(len(factor.observed_hz), dtype=float)
    for visit in np.unique(factor.visit_id):
        selected = np.asarray(factor.visit_id) == visit
        weights[selected] = 1.0 / np.sum(selected)
    return weights


def _profile_receiver_offsets(factor, residual, weights):
    receivers = np.unique(factor.receiver_id)
    centered = np.asarray(residual, dtype=float).copy()
    offsets = np.empty((len(centered), len(receivers)), dtype=float)
    for column, receiver in enumerate(receivers):
        selected = (factor.receiver_id == receiver) & factor.training
        offsets[:, column] = np.sum(centered[:, selected] * weights[selected], axis=1) / np.sum(
            weights[selected]
        )
        centered[:, factor.receiver_id == receiver] -= offsets[:, column, None]
    return centered, offsets, receivers


def score_paired_doppler_factor(
    factor: PairedDopplerFactor,
    predicted_hz: np.ndarray,
    *,
    sigma_hz: float,
    effective_count: float = 6.0,
    visible: np.ndarray | None = None,
    position_jacobian_hz_km: np.ndarray | None = None,
) -> dict[str, object]:
    """Score candidate/location templates and optionally report local information.

    ``predicted_hz`` is candidate by observation.  ``position_jacobian_hz_km``
    has candidate by observation by position-coordinate shape and is projected
    through the same receiver-offset nuisance space before forming information.
    Scores are visit-balanced composite log scores, not calibrated likelihoods.
    """
    prediction = np.asarray(predicted_hz, dtype=float)
    count = len(factor.observed_hz)
    if prediction.ndim != 2 or prediction.shape[1] != count or len(prediction) == 0:
        raise ValueError("predictions must be candidate by observation")
    if (
        not np.all(np.isfinite(prediction))
        or not np.all(np.isfinite((sigma_hz, effective_count)))
        or min(sigma_hz, effective_count) <= 0
    ):
        raise ValueError("predictions and positive noise scale must be finite")
    if visible is None:
        visible_array = np.ones(len(prediction), dtype=bool)
    else:
        visible_array = np.asarray(visible)
        if visible_array.shape != (len(prediction),) or visible_array.dtype != bool:
            raise ValueError("visibility must be one boolean per candidate")
    weights = _visit_weights(factor)
    centered, offsets, receivers = _profile_receiver_offsets(
        factor, factor.observed_hz[None, :] - prediction, weights
    )

    def likelihood(selected):
        visit_count = len(np.unique(factor.visit_id[selected]))
        count = min(effective_count, visit_count)
        mean_energy = np.sum(weights[selected] * centered[:, selected] ** 2, axis=1) / visit_count
        return -0.5 * count * mean_energy / sigma_hz**2 - count * np.log(sigma_hz)

    training_ll = np.where(visible_array, likelihood(factor.training), -np.inf)
    heldout_ll = np.where(visible_array, likelihood(~factor.training), -np.inf)
    best = int(np.argmax(training_ll)) if np.any(visible_array) else -1
    training_visit_count = len(np.unique(factor.visit_id[factor.training]))
    joint_training_energy_score = -0.5 * min(effective_count, training_visit_count) * np.sum(
        weights[factor.training] * centered[:, factor.training] ** 2, axis=1
    ) / (training_visit_count * sigma_hz**2)
    joint_training_energy_score = np.where(visible_array, joint_training_energy_score, -np.inf)
    independent_choices = []
    independent_training_score = 0.0
    for receiver in receivers:
        selected = factor.training & (factor.receiver_id == receiver)
        receiver_energy = np.sum(weights[selected] * centered[:, selected] ** 2, axis=1)
        receiver_visits = len(np.unique(factor.visit_id[selected]))
        receiver_ll = (
            -0.5
            * min(effective_count, receiver_visits)
            * receiver_energy
            / (receiver_visits * sigma_hz**2)
        )
        receiver_ll = np.where(visible_array, receiver_ll, -np.inf)
        choice = int(np.argmax(receiver_ll)) if np.any(visible_array) else -1
        independent_choices.append(choice)
        independent_training_score += float(receiver_ll[choice]) if choice >= 0 else -np.inf
    result: dict[str, object] = {
        "training_log_likelihood": training_ll,
        "heldout_log_likelihood": heldout_ll,
        "training_selected_candidate": best,
        "training_selected_heldout_log_likelihood": (
            float(heldout_ll[best]) if best >= 0 else float("-inf")
        ),
        "receiver_ids": receivers,
        "receiver_offset_hz": offsets,
        "pairing_authority": factor.pairing_authority,
        "independent_receiver_selected_candidate": np.asarray(independent_choices),
        "shared_minus_independent_training_log_score": (
            float(np.max(joint_training_energy_score)) - independent_training_score
            if np.any(visible_array)
            else float("-inf")
        ),
        "visit_weight": weights,
        "training_visit_count": len(np.unique(factor.visit_id[factor.training])),
        "heldout_visit_count": len(np.unique(factor.visit_id[~factor.training])),
    }
    if position_jacobian_hz_km is not None:
        jacobian = np.asarray(position_jacobian_hz_km, dtype=float)
        if jacobian.ndim != 3 or jacobian.shape[:2] != prediction.shape:
            raise ValueError("position Jacobian must be candidate by observation by coordinate")
        if not np.all(np.isfinite(jacobian)):
            raise ValueError("position Jacobian must be finite")
        projected = jacobian.copy()
        for receiver in receivers:
            selected = (factor.receiver_id == receiver) & factor.training
            mean = np.sum(
                projected[:, selected] * weights[selected][None, :, None], axis=1
            ) / np.sum(weights[selected])
            projected[:, factor.receiver_id == receiver] -= mean[:, None, :]
        selected = factor.training
        information = np.einsum(
            "n,knd,kne->kde",
            weights[selected] / sigma_hz**2,
            projected[:, selected],
            projected[:, selected],
        )
        result["nuisance_projected_position_information"] = information
        result["nuisance_projected_information_eigenvalues"] = np.linalg.eigvalsh(information)
    return result


def score_paired_states(
    factor: PairedDopplerFactor,
    positions_km: np.ndarray,
    velocities_km_s: np.ndarray,
    grid,
    catalogue_size: int,
    *,
    signal_sigma_hz: float = 250.0,
    null_sigma_hz: float = 30_000.0,
    signal_prior: float = 0.5,
    effective_count: float = 6.0,
    minimum_elevation_deg: float = -1.0,
) -> dict[str, np.ndarray]:
    """Project states in bounded grid batches and apply the paired identity mixture."""
    position = np.asarray(positions_km)
    velocity = np.asarray(velocities_km_s)
    if position.shape != velocity.shape or position.shape[1:] != (
        len(factor.observed_hz),
        3,
    ):
        raise ValueError("states must be candidate by paired observation by xyz")
    if catalogue_size < len(position) or not 0 < signal_prior < 1:
        raise ValueError("full catalogue denominator and signal prior are invalid")
    null = score_paired_doppler_factor(
        factor,
        np.zeros((1, len(factor.observed_hz))),
        sigma_hz=null_sigma_hz,
        effective_count=effective_count,
    )
    null_train = float(np.asarray(null["training_log_likelihood"])[0])
    null_heldout = float(np.asarray(null["heldout_log_likelihood"])[0])
    outputs = []
    horizon = np.sin(np.deg2rad(minimum_elevation_deg))
    first_training = np.flatnonzero(factor.training)[0]
    for start in range(0, len(grid.ecef_km), 12):
        receiver = grid.ecef_km[start : start + 12]
        up = grid.up[start : start + 12]
        first_delta = position[None, :, first_training] - receiver[:, None, :]
        first_distance = np.linalg.norm(first_delta, axis=-1)
        first_elevation = np.sum(first_delta * up[:, None, :], axis=-1) / first_distance
        candidates = np.flatnonzero(np.any(first_elevation >= horizon, axis=0))
        if not len(candidates):
            outputs.append(
                {
                    "train_logbf": np.zeros(len(receiver)),
                    "heldout_logbf": np.zeros(len(receiver)),
                }
            )
            continue
        p, v = position[candidates], velocity[candidates]
        shape = (len(receiver), len(candidates), len(factor.observed_hz))
        receiver_dot_position = (receiver @ p.reshape(-1, 3).T).reshape(shape)
        distance = np.sqrt(
            np.maximum(
                np.sum(p * p, axis=-1)[None]
                + np.sum(receiver * receiver, axis=-1)[:, None, None]
                - 2 * receiver_dot_position,
                1e-12,
            )
        )
        numerator = np.sum(p * v, axis=-1)[None] - (
            receiver @ v.reshape(-1, 3).T
        ).reshape(shape)
        prediction = (
            -_REFERENCE_RF_HZ
            / _LIGHT_KM_S
            * numerator
            / distance
        )
        elevation = (
            (up @ p.reshape(-1, 3).T).reshape(shape)
            - np.sum(receiver * up, axis=-1)[:, None, None]
        ) / distance
        visible = np.min(elevation[..., factor.training], axis=-1) >= horizon
        flat = score_paired_doppler_factor(
            factor,
            prediction.reshape(-1, prediction.shape[-1]),
            sigma_hz=signal_sigma_hz,
            effective_count=effective_count,
            visible=visible.ravel(),
        )
        train = np.asarray(flat["training_log_likelihood"]).reshape(prediction.shape[:2])
        heldout = np.asarray(flat["heldout_log_likelihood"]).reshape(prediction.shape[:2])
        prior = np.log(signal_prior / catalogue_size)
        null_prior = np.log1p(-signal_prior)
        signal = np.asarray([_logsumexp(row + prior) for row in train])
        evidence = np.logaddexp(signal, null_train + null_prior)
        joint = np.asarray(
            [_logsumexp(row + prior) for row in train + heldout]
        )
        joint = np.logaddexp(joint, null_train + null_heldout + null_prior)
        outputs.append(
            {
                "train_logbf": evidence - (null_train + null_prior),
                "heldout_logbf": joint - evidence - null_heldout,
            }
        )
    return {
        key: np.concatenate([value[key] for value in outputs])
        for key in ("train_logbf", "heldout_logbf")
    }


def _logsumexp(values: np.ndarray) -> float:
    maximum = np.max(values)
    if not np.isfinite(maximum):
        return float(maximum)
    return float(maximum + np.log(np.sum(np.exp(values - maximum))))
