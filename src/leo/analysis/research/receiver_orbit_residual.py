"""Frozen-position receiver-versus-satellite residual diagnostic.

This module compares two descriptive residual models after a blind position and
soft satellite identities have already been frozen.  It does not update either
quantity.  Candidate identities are alternatives for one episode and are
averaged with their frozen, unconditional probability mass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class ResidualCandidate:
    catalog_number: int
    soft_weight: float
    residual_hz: np.ndarray
    satellite_design_hz_per_unit: np.ndarray


@dataclass(frozen=True)
class ResidualEpisode:
    episode_id: str
    receiver_drift_group: str
    time_s: np.ndarray
    training: np.ndarray
    candidates: tuple[ResidualCandidate, ...]
    null_probability: float
    omitted_probability_mass: float


@dataclass(frozen=True)
class ResidualDiagnosticConfig:
    robust_scale_hz: float = 250.0
    receiver_slope_sigma_hz_h: float = 500.0
    satellite_rate_sigma_unit: float = 0.09176615913014215
    effective_rows_per_episode: float = 6.0
    max_iterations: int = 400

    def __post_init__(self) -> None:
        values = (
            self.robust_scale_hz,
            self.receiver_slope_sigma_hz_h,
            self.satellite_rate_sigma_unit,
            self.effective_rows_per_episode,
        )
        if not np.all(np.isfinite(values)) or any(value <= 0 for value in values):
            raise ValueError("diagnostic scales must be finite and positive")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")


@dataclass(frozen=True)
class ResidualModelResult:
    model: str
    receiver_slopes_normalized_hz_h: dict[str, float]
    satellite_rates: dict[int, float]
    training_loss: float
    heldout_loss: float
    converged: bool
    iterations: int


@dataclass(frozen=True)
class ResidualDiagnosticResult:
    models: tuple[ResidualModelResult, ...]
    design_rank: int
    design_columns: int
    design_condition: float | None
    maximum_receiver_satellite_correlation: float
    recurring_satellites: dict[int, int]
    episodes: int
    training_rows: int
    heldout_rows: int
    retained_signal_mass: float
    null_probability_mass: float
    omitted_probability_mass: float
    reasons: tuple[str, ...]
    method: str = (
        "frozen-position soft-identity expected robust loss; episode-balanced; "
        "training-only coefficients"
    )


def _validate(episodes: tuple[ResidualEpisode, ...]) -> None:
    if not episodes:
        raise ValueError("at least one residual episode is required")
    ids: set[str] = set()
    for episode in episodes:
        if not episode.episode_id or episode.episode_id in ids:
            raise ValueError("episode identifiers must be nonempty and unique")
        ids.add(episode.episode_id)
        time = np.asarray(episode.time_s, float)
        training = np.asarray(episode.training)
        if time.ndim != 1 or len(time) < 4 or training.shape != time.shape:
            raise ValueError("episode time and training arrays are incompatible")
        if (
            training.dtype != bool
            or np.count_nonzero(training) < 2
            or np.count_nonzero(~training) < 2
        ):
            raise ValueError("each episode requires at least two training and heldout rows")
        if not np.all(np.isfinite(time)) or np.any(np.diff(time) <= 0):
            raise ValueError("episode times must be finite and strictly increasing")
        if not episode.receiver_drift_group or not episode.candidates:
            raise ValueError("receiver group and candidates are required")
        probability = episode.null_probability + episode.omitted_probability_mass
        if not np.isfinite(probability) or min(
            episode.null_probability, episode.omitted_probability_mass
        ) < -1e-12:
            raise ValueError("probability masses must be finite and nonnegative")
        norads: set[int] = set()
        for candidate in episode.candidates:
            if candidate.catalog_number <= 0 or candidate.catalog_number in norads:
                raise ValueError("candidate catalogue numbers must be positive and unique")
            norads.add(candidate.catalog_number)
            residual = np.asarray(candidate.residual_hz, float)
            design = np.asarray(candidate.satellite_design_hz_per_unit, float)
            if residual.shape != time.shape or design.shape != time.shape:
                raise ValueError("candidate row arrays must match episode time")
            if not np.all(np.isfinite(residual)) or not np.all(np.isfinite(design)):
                raise ValueError("candidate arrays must be finite")
            if not np.isfinite(candidate.soft_weight) or candidate.soft_weight < 0:
                raise ValueError("candidate weights must be finite and nonnegative")
            probability += candidate.soft_weight
        if probability > 1.0 + 1e-8:
            raise ValueError("candidate, null, and omitted probability exceeds one")


def _center(values: np.ndarray, training: np.ndarray, weights: np.ndarray) -> np.ndarray:
    selected = training & (weights > 0)
    if not np.any(selected):
        return values.copy()
    return values - np.average(values[selected], weights=weights[selected])


def diagnose_receiver_orbit_residuals(
    episodes: tuple[ResidualEpisode, ...],
    config: ResidualDiagnosticConfig | None = None,
) -> ResidualDiagnosticResult:
    """Fit nested residual models without changing frozen position or identities."""
    config = config or ResidualDiagnosticConfig()
    _validate(episodes)
    receiver_groups = sorted({episode.receiver_drift_group for episode in episodes})
    satellites = sorted(
        {
            candidate.catalog_number
            for episode in episodes
            for candidate in episode.candidates
            if candidate.soft_weight > 0
        }
    )
    if not satellites:
        raise ValueError("at least one candidate must have positive soft weight")
    receiver_index = {value: index for index, value in enumerate(receiver_groups)}
    satellite_index = {value: index for index, value in enumerate(satellites)}
    # Each episode contributes at most its retained signal probability, regardless
    # of its sample density. Candidate rows split rather than multiply that mass.
    prepared = []
    occurrence = {value: 0 for value in satellites}
    for episode in episodes:
        training = np.asarray(episode.training)
        time_h = (np.asarray(episode.time_s) - np.asarray(episode.time_s)[training].mean()) / 3600
        candidates = []
        for candidate in episode.candidates:
            if candidate.soft_weight == 0:
                continue
            occurrence[candidate.catalog_number] += 1
            residual = _center(np.asarray(candidate.residual_hz), training, np.ones(len(training)))
            design = _center(
                np.asarray(candidate.satellite_design_hz_per_unit),
                training,
                np.ones(len(training)),
            )
            candidates.append((candidate, residual, design))
        prepared.append((episode, training, time_h, candidates))

    def fit(name: str, receiver: bool, satellite: bool) -> ResidualModelResult:
        nr = len(receiver_groups) if receiver else 0
        ns = len(satellites) if satellite else 0
        parameter_scales = np.asarray(
            [config.receiver_slope_sigma_hz_h] * nr
            + [config.satellite_rate_sigma_unit] * ns
        )

        def evaluate(
            parameters: np.ndarray, training_rows: bool, *, gradient: bool
        ) -> tuple[float, np.ndarray]:
            total = 0.0
            derivative = np.zeros_like(parameters)
            for episode, _, time_h, candidates in prepared:
                episode_loss = 0.0
                mask = episode.training if training_rows else ~episode.training
                for candidate, residual, design in candidates:
                    if candidate.soft_weight == 0:
                        continue
                    prediction = np.zeros(len(mask))
                    receiver_column = receiver_index[episode.receiver_drift_group]
                    satellite_column = nr + satellite_index[candidate.catalog_number]
                    if receiver:
                        prediction += (
                            parameters[receiver_column]
                            * parameter_scales[receiver_column]
                            * time_h
                        )
                    if satellite:
                        prediction += (
                            parameters[satellite_column]
                            * parameter_scales[satellite_column]
                            * design
                        )
                    z = (residual[mask] - prediction[mask]) / config.robust_scale_hz
                    mass = config.effective_rows_per_episode * candidate.soft_weight
                    episode_loss += mass * float(np.mean(np.sqrt(1.0 + z * z) - 1.0))
                    if gradient:
                        score = -z / (config.robust_scale_hz * np.sqrt(1.0 + z * z))
                        if receiver:
                            derivative[receiver_column] += mass * float(
                                np.mean(score * time_h[mask])
                                * parameter_scales[receiver_column]
                            )
                        if satellite:
                            derivative[satellite_column] += mass * float(
                                np.mean(score * design[mask])
                                * parameter_scales[satellite_column]
                            )
                total += episode_loss
            return total, derivative

        def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
            value, derivative = evaluate(parameters, True, gradient=True)
            if receiver:
                value += 0.5 * float(np.sum(parameters[:nr] ** 2))
                derivative[:nr] += parameters[:nr]
            if satellite:
                value += 0.5 * float(np.sum(parameters[nr:] ** 2))
                derivative[nr:] += parameters[nr:]
            return value, derivative

        if nr + ns:
            answer = minimize(
                objective,
                np.zeros(nr + ns),
                method="L-BFGS-B",
                jac=True,
                options={"maxiter": config.max_iterations, "ftol": 1e-12},
            )
            parameters = answer.x
            converged = bool(answer.success)
            iterations = int(answer.nit)
        else:
            parameters = np.empty(0)
            converged = True
            iterations = 0
        physical = parameters * parameter_scales
        return ResidualModelResult(
            model=name,
            receiver_slopes_normalized_hz_h={
                value: float(physical[index]) for value, index in receiver_index.items()
            }
            if receiver
            else {},
            satellite_rates={
                value: float(physical[nr + index]) for value, index in satellite_index.items()
            }
            if satellite
            else {},
            training_loss=float(evaluate(parameters, True, gradient=False)[0]),
            heldout_loss=float(evaluate(parameters, False, gradient=False)[0]),
            converged=converged,
            iterations=iterations,
        )

    # Diagnose receiver/satellite confounding after per-episode constant removal.
    rows = []
    row_weights = []
    for episode, training, time_h, candidates in prepared:
        for candidate, _, design in candidates:
            if candidate.soft_weight == 0:
                continue
            for row in np.flatnonzero(training):
                vector = np.zeros(len(receiver_groups) + len(satellites))
                vector[receiver_index[episode.receiver_drift_group]] = time_h[row]
                column = len(receiver_groups) + satellite_index[candidate.catalog_number]
                vector[column] = design[row]
                rows.append(vector)
                row_weights.append(candidate.soft_weight / np.count_nonzero(training))
    matrix = np.asarray(rows)
    weights = np.sqrt(np.asarray(row_weights))
    prior_scales = np.asarray(
        [config.receiver_slope_sigma_hz_h] * len(receiver_groups)
        + [config.satellite_rate_sigma_unit] * len(satellites)
    )
    weighted = matrix * weights[:, None] * prior_scales[None, :]
    singular = np.linalg.svd(weighted, compute_uv=False)
    tolerance = singular[0] * max(weighted.shape) * np.finfo(float).eps if singular.size else 0
    rank = int(np.count_nonzero(singular > tolerance))
    condition = (
        float(singular[0] / singular[-1])
        if singular.size and singular[-1] > tolerance
        else None
    )
    correlations = []
    for left in range(len(receiver_groups)):
        for right in range(len(receiver_groups), weighted.shape[1]):
            a, b = weighted[:, left], weighted[:, right]
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            if denom:
                correlations.append(abs(float(np.dot(a, b) / denom)))
    reasons = []
    if rank < weighted.shape[1]:
        reasons.append("receiver-satellite-design-rank-deficient")
    if correlations and max(correlations) > 0.95:
        reasons.append("receiver-satellite-design-highly-confounded")
    if not any(value >= 2 for value in occurrence.values()):
        reasons.append("no-satellite-support-recurs-across-episodes")
    return ResidualDiagnosticResult(
        models=(
            fit("offset_only", False, False),
            fit("receiver_drift", True, False),
            fit("satellite_proxy", False, True),
            fit("joint", True, True),
        ),
        design_rank=rank,
        design_columns=weighted.shape[1],
        design_condition=condition,
        maximum_receiver_satellite_correlation=max(correlations, default=0.0),
        recurring_satellites={key: value for key, value in occurrence.items() if value >= 2},
        episodes=len(episodes),
        training_rows=sum(int(np.count_nonzero(item.training)) for item in episodes),
        heldout_rows=sum(int(np.count_nonzero(~item.training)) for item in episodes),
        retained_signal_mass=float(
            sum(candidate.soft_weight for item in episodes for candidate in item.candidates)
        ),
        null_probability_mass=float(sum(item.null_probability for item in episodes)),
        omitted_probability_mass=float(
            sum(max(0.0, item.omitted_probability_mass) for item in episodes)
        ),
        reasons=tuple(reasons),
    )
