"""Local joint receiver-position/shared-rate MAP with uncertain identities.

Full supplied candidate mixtures are refreshed at each trial. This does not
certify a global mode or the supplied interpolation/support; exact finalist
replay remains the caller's responsibility.
"""

import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.orbit_rate_states import doppler_and_rate_derivative
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region, ScoreConfig
from leo.analysis.research.robust_track_location import profile_pseudo_huber
from leo.analysis.research.shared_gaussian_orbit import (
    SharedGaussianEpisode,
    SharedGaussianEvaluation,
    evaluate_shared_gaussian_mixture,
)


@dataclass(frozen=True)
class JointOrbitResult:
    east_north_km: np.ndarray
    rate_norad: np.ndarray
    rate_s_h: np.ndarray
    objective: float
    projected_gradient_max: float
    converged: bool
    evaluations: int
    message: str
    diagnostics: object


class JointOrbitObjective:
    """Analytic Doppler gradients; finite differences only for map coordinates."""

    def __init__(
        self, episodes, region: Region, prior_sigma_s_h, config=None, loss="gaussian",
        training_only=False,
    ):
        if not episodes or not np.isfinite(prior_sigma_s_h) or prior_sigma_s_h <= 0:
            raise ValueError("episodes and finite positive rate prior required")
        self.episodes = episodes
        self.region = region
        self.sigma = float(prior_sigma_s_h)
        self.config = config or ScoreConfig()
        if loss not in ("gaussian", "pseudo_huber"):
            raise ValueError("unknown residual loss")
        self.loss = loss
        if not isinstance(training_only, (bool, np.bool_)):
            raise ValueError("training_only must be boolean")
        self.training_only = bool(training_only)
        self.norads = np.unique(np.concatenate([ep.candidate_norad for ep in episodes]))
        lookup = {int(n): i for i, n in enumerate(self.norads)}
        self.indices = [np.array([lookup[int(n)] for n in ep.candidate_norad]) for ep in episodes]

    def evaluate(self, x, *, gradient=True, diagnostics=False):
        """x has position in 10 km units and rates in prior-sigma units."""
        x = np.asarray(x, float)
        if x.shape != (2 + len(self.norads),) or not np.all(np.isfinite(x)):
            raise ValueError("invalid joint parameter vector")
        position = x[:2] * 10
        rates = x[2:] * self.sigma
        grid = self.region.points([position[0]], [position[1]])
        receiver, up = grid.ecef_km[0], grid.up[0]
        receiver_derivatives = []
        if gradient:
            step_km = 0.01
            for axis in range(2):
                low, high = position.copy(), position.copy()
                limit = (self.region.width_km if axis == 0 else self.region.height_km) / 2
                low[axis] = max(-limit, low[axis] - step_km)
                high[axis] = min(limit, high[axis] + step_km)
                receiver_derivatives.append(
                    (
                        self.region.points([high[0]], [high[1]]).ecef_km[0]
                        - self.region.points([low[0]], [low[1]]).ecef_km[0]
                    )
                    / (high[axis] - low[axis])
                )

        prior_gradient = rates / self.sigma**2
        prior_objective = 0.5 * float(np.sum((rates / self.sigma) ** 2))
        objective = prior_objective
        rate_gradient = prior_gradient.copy()
        position_gradient = np.zeros(2)
        episode_results = []
        training_weights = []
        for ep, idx in zip(self.episodes, self.indices, strict=True):
            state = ep.state_grid.evaluate(rates[idx])
            predicted, rate_derivative = doppler_and_rate_derivative(receiver, *state)
            delta = state[0] - receiver
            sine = np.sum(delta * up, axis=-1) / np.linalg.norm(delta, axis=-1)
            visible = np.all(
                sine[:, ep.training] >= np.sin(np.deg2rad(self.config.minimum_elevation_deg)),
                axis=1,
            )
            supplied = SharedGaussianEpisode(
                ep.episode_id,
                ep.observed_hz,
                predicted,
                rate_derivative,
                ep.candidate_norad,
                ep.segment,
                ep.training,
                visible,
                ep.full_catalogue_size,
            )
            evaluated = evaluate_shared_gaussian_mixture(
                rates,
                self.norads,
                [supplied],
                prior_sigma_s_h=self.sigma,
                config=self.config,
                return_diagnostics=diagnostics,
                loss=self.loss,
                training_only=self.training_only,
            )
            objective += evaluated.negative_log_posterior - prior_objective
            rate_gradient += evaluated.gradient - prior_gradient
            weights = evaluated.training_candidate_weights[0]
            training_weights.append(weights)
            if diagnostics:
                episode_results.extend(evaluated.episodes)
            if gradient:
                velocity = state[1]
                radius = np.linalg.norm(delta, axis=-1)
                radial = np.sum(delta * velocity, axis=-1)
                ecef_gradient = (
                    REFERENCE_RF_HZ
                    / LIGHT_KM_S
                    * (
                        velocity / radius[..., None]
                        - radial[..., None] * delta / radius[..., None] ** 3
                    )
                )
                residual = ep.observed_hz[None, :] - predicted
                groups = np.unique(ep.segment)
                for axis, receiver_derivative in enumerate(receiver_derivatives):
                    prediction_derivative = ecef_gradient @ receiver_derivative
                    candidate_derivative = np.zeros(len(weights))
                    for group in groups:
                        mask = (ep.segment == group) & ep.training
                        centred = residual[:, mask] - np.mean(
                            residual[:, mask], axis=1
                        )[:, None]
                        score = centred / self.config.signal_sigma_hz**2
                        if self.loss == "pseudo_huber":
                            _, _, score = profile_pseudo_huber(
                                residual[:, mask],
                                np.ones(np.sum(mask), dtype=bool),
                                self.config.signal_sigma_hz,
                            )
                        candidate_derivative += (
                            self.config.effective_count
                            * np.mean(score * prediction_derivative[:, mask], axis=1)
                            / len(groups)
                        )
                    position_gradient[axis] -= 10 * float(weights @ candidate_derivative)
            # Do not retain large candidate x observation state arrays between episodes.
            if gradient:
                del velocity
            del state, supplied, evaluated

        answer = SharedGaussianEvaluation(
            float(objective),
            rate_gradient,
            tuple(episode_results),
            tuple(training_weights),
        )
        if not gradient:
            return answer
        derivative = np.empty_like(x)
        derivative[:2] = position_gradient
        derivative[2:] = answer.gradient * self.sigma
        return answer.negative_log_posterior, derivative


def fit_joint_orbit_position(
    episodes,
    region,
    initial_east_north_km,
    *,
    prior_sigma_s_h=0.09176615913014215,
    local_half_width_km=100.0,
    maximum_iterations=80,
    maximum_evaluations=160,
    fit_rates=True,
    progress_callback=None,
    maximum_seconds=None,
    resume_state=None,
    loss="gaussian",
    training_only=False,
):
    """One deterministic local start; callers compare independently sealed basins."""
    if local_half_width_km <= 0 or maximum_iterations < 1 or maximum_evaluations < 1:
        raise ValueError("positive local search and resource bounds required")
    model = JointOrbitObjective(
        episodes, region, prior_sigma_s_h, loss=loss, training_only=training_only
    )
    initial = np.asarray(initial_east_north_km, float)
    if initial.shape != (2,) or not np.all(np.isfinite(initial)):
        raise ValueError("finite initial east/north required")
    lower_rate = max(ep.state_grid.rate_nodes_s_h[0] for ep in episodes)
    upper_rate = min(ep.state_grid.rate_nodes_s_h[-1] for ep in episodes)
    if not lower_rate < 0 < upper_rate:
        raise ValueError("common rate bounds must contain zero")
    limits = np.array([region.width_km, region.height_km]) / 2
    bounds = list(
        zip(
            np.maximum(initial - local_half_width_km, -limits) / 10,
            np.minimum(initial + local_half_width_km, limits) / 10,
            strict=True,
        )
    )
    rate_bound = (lower_rate / model.sigma, upper_rate / model.sigma) if fit_rates else (0.0, 0.0)
    bounds += [rate_bound] * len(model.norads)
    x = np.r_[initial / 10, np.zeros(len(model.norads))]
    if resume_state is not None:
        if not np.array_equal(resume_state["rate_norad"], model.norads):
            raise ValueError("resume NORAD ordering/support mismatch")
        x = np.r_[
            np.asarray(resume_state["east_north_km"]) / 10,
            np.asarray(resume_state["rate_s_h"]) / model.sigma,
        ]
        if (
            x.shape != (2 + len(model.norads),)
            or not np.all(np.isfinite(x))
            or np.any(x < np.array(bounds)[:, 0])
            or np.any(x > np.array(bounds)[:, 1])
        ):
            raise ValueError("resume state outside original bounds")
    started = time.monotonic()

    def callback(intermediate_result):
        if progress_callback is not None:
            progress_callback(
                {
                    "east_north_km": (intermediate_result.x[:2] * 10).tolist(),
                    "rate_norad": model.norads.tolist(),
                    "rate_s_h": (intermediate_result.x[2:] * model.sigma).tolist(),
                    "negative_log_posterior": float(intermediate_result.fun),
                    "elapsed_s": time.monotonic() - started,
                }
            )
        if maximum_seconds is not None and time.monotonic() - started >= maximum_seconds:
            raise StopIteration

    answer = minimize(
        model.evaluate,
        x,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        callback=callback,
        options={
            # Five-scan fits move more than 100 shared orbital rates. The
            # default ten correction pairs discard useful coupled curvature.
            "maxcor": 50,
            "maxiter": maximum_iterations,
            "maxfun": maximum_evaluations,
            "ftol": 1e-11,
            "gtol": 1e-5,
        },
    )
    _, grad = model.evaluate(answer.x)
    projected = answer.x - np.clip(answer.x - grad, np.array(bounds)[:, 0], np.array(bounds)[:, 1])
    final = model.evaluate(answer.x, gradient=False, diagnostics=True)
    return JointOrbitResult(
        answer.x[:2] * 10,
        model.norads,
        answer.x[2:] * model.sigma,
        float(answer.fun),
        float(np.max(np.abs(projected))),
        bool(answer.success),
        int(answer.nfev),
        str(answer.message),
        final,
    )
