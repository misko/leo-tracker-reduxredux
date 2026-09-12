"""Offline PSS timing: Gaussian repetition peaks, broad contamination, causal tracking.

All units are seconds and nanoseconds. A branch index is an ambiguity label,
not a physical arrival-time identity. No storage, acquisition or production ports.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.special import logsumexp
from scipy.stats import t as student_t

REPEAT_NS = 128 / 240e6 * 1e9
BACKGROUND_SCALE_NS = 1500.0


@dataclass(frozen=True)
class PeakMixture:
    reference_s: float
    coefficients_ns: np.ndarray  # ascending powers of (t - reference)
    covariance_ns2: np.ndarray  # conditional curve covariance, not clock truth
    branches: np.ndarray
    spacing_ns: float
    sigma_ns: float
    weights: np.ndarray  # last entry is broad Student-t contamination
    training_log_likelihood: float
    coherence: float
    supported: bool
    iterations: int
    background_coefficients_ns: np.ndarray

    def predict(self, times_s):
        x = np.asarray(times_s, dtype=float) - self.reference_s
        return (
            self.coefficients_ns[0] + x * self.coefficients_ns[1] + x * x * self.coefficients_ns[2]
        )


def _validate(times_s, phases_ns):
    times, phases = np.asarray(times_s, dtype=float), np.asarray(phases_ns, dtype=float)
    if times.ndim != 1 or phases.shape != times.shape or len(times) < 12:
        raise ValueError("timing fit requires at least twelve paired one-dimensional observations")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(phases)):
        raise ValueError("timing observations must be finite")
    if np.any(np.diff(times) <= 0) or np.ptp(times) <= 0:
        raise ValueError("timing observations must be strictly increasing")
    return times, phases


def _design(times, reference):
    x = times - reference
    return np.column_stack((np.ones(len(times)), x, x * x))


def _components(
    residual, branches, spacing, sigma, weights, prediction_variance=0.0, background_offset_ns=0.0
):
    residual = np.atleast_1d(np.asarray(residual, dtype=float))
    variance = sigma * sigma + np.broadcast_to(prediction_variance, residual.shape)
    offsets = residual[:, None] - branches[None, :] * spacing
    gaussian = -0.5 * (
        offsets * offsets / variance[:, None] + np.log(2 * np.pi * variance[:, None])
    )
    broad = student_t.logpdf((residual - background_offset_ns) / BACKGROUND_SCALE_NS, df=3)
    broad -= np.log(BACKGROUND_SCALE_NS)
    values = np.column_stack((gaussian, broad)) + np.log(weights)[None, :]
    evidence = logsumexp(values, axis=1)
    probabilities = np.exp(values - evidence[:, None])
    return evidence, probabilities


def evaluate_mixture(model, times_s, phases_ns):
    """Frozen early-fit predictive density, including conditional curve uncertainty."""
    times, phases = np.asarray(times_s), np.asarray(phases_ns)
    if (
        times.ndim != 1
        or phases.shape != times.shape
        or not np.all(np.isfinite(times))
        or not np.all(np.isfinite(phases))
    ):
        raise ValueError("evaluation requires finite paired one-dimensional observations")
    design = _design(times, model.reference_s)
    variance = np.einsum("ni,ij,nj->n", design, model.covariance_ns2, design)
    evidence, probabilities = _components(
        phases - model.predict(times),
        model.branches,
        model.spacing_ns,
        model.sigma_ns,
        model.weights,
        np.maximum(variance, 0),
        design @ model.background_coefficients_ns - model.predict(times),
    )
    return evidence, probabilities


def _circular_seed(times, phases, design, period):
    origin = float(np.median(phases))
    baseline = np.linalg.lstsq(design, phases - origin, rcond=None)[0]
    baseline[0] += origin
    residual = phases - design @ baseline
    centers, angles = [], []
    for start in np.arange(times.min(), times.max() + 1e-9, 0.1):
        mask = (times >= start) & (times < start + 0.1)
        if np.any(mask):
            centers.append(np.mean(design[mask, 1]))
            angles.append(np.angle(np.mean(np.exp(2j * np.pi * residual[mask] / period))))
    seed = (
        np.polynomial.polynomial.polyfit(centers, np.unwrap(angles) * period / (2 * np.pi), 2)
        if len(centers) >= 3
        else np.zeros(3)
    )

    def objective(coef):
        angle = 2 * np.pi * (residual - design @ coef) / period
        return np.r_[np.cos(angle) - 1, np.sin(angle)]

    optimum = least_squares(objective, seed, max_nfev=200)
    # This is an initializer, not the fitted mixture. Weak/noise-like data may
    # exhaust this search; their final coherence is evaluated explicitly below.
    return baseline + (optimum.x if optimum.success else seed)


def fit_peak_mixture(times_s, phases_ns, *, mode="fixed", maximum_iterations=120):
    """Fit only the explicitly supplied training observations.

    mode='single': one broad-capable Gaussian peak plus contamination baseline.
    mode='fixed': repetition spacing fixed at 533.333 ns.
    mode='empirical': spacing learned within [480, 570] ns, not physical stretch.
    """
    times, phases = _validate(times_s, phases_ns)
    if mode not in ("single", "fixed", "empirical"):
        raise ValueError("unknown peak-mixture mode")
    if maximum_iterations < 1:
        raise ValueError("maximum iterations must be positive")
    reference = float((times[0] + times[-1]) / 2)
    design = _design(times, reference)
    origin = float(np.median(phases))
    background = np.linalg.lstsq(design, phases - origin, rcond=None)[0]
    background[0] += origin
    background_prediction = design @ background
    branches = np.arange(-6, 7, dtype=float) if mode != "single" else np.array([0.0])
    seeds = ((500.0, "circular"), (REPEAT_NS, "circular"), (560.0, "circular"))
    if mode == "fixed":
        seeds = ((REPEAT_NS, "circular"),)
    elif mode == "single":
        seeds = tuple((REPEAT_NS, name) for name in ("ordinary", "circular", "minus", "plus"))
    candidates = []
    for spacing, initialization in seeds:
        coef = _circular_seed(times, phases, design, spacing)
        if initialization == "ordinary":
            coef = background.copy()
        elif initialization == "minus":
            coef[0] -= spacing
        elif initialization == "plus":
            coef[0] += spacing
        residual = phases - design @ coef
        fold = residual - np.rint(residual / spacing) * spacing
        sigma = max(2.0, min(150.0, 1.4826 * np.median(abs(fold))))
        if initialization == "ordinary":
            sigma = max(2.0, float(np.std(residual)))
        weights = np.r_[np.repeat(0.8 / len(branches), len(branches)), 0.2]
        last_score = -np.inf
        for _iteration in range(maximum_iterations):
            _, probabilities = _components(
                phases - design @ coef,
                branches,
                spacing,
                sigma,
                weights,
                background_offset_ns=background_prediction - design @ coef,
            )
            signal = probabilities[:, :-1]
            occupancy = signal.sum(axis=1)
            # The broad component does not drag the narrow timing curve.
            if mode == "empirical":
                features = np.concatenate(
                    (
                        np.broadcast_to(design[:, None, :], (len(times), len(branches), 3)),
                        np.broadcast_to(branches[None, :, None], (len(times), len(branches), 1)),
                    ),
                    axis=2,
                )
                weighted = features * np.sqrt(signal)[:, :, None]
                target = np.broadcast_to(phases[:, None], signal.shape) * np.sqrt(signal)
                solution = np.linalg.lstsq(weighted.reshape(-1, 4), target.ravel(), rcond=None)[0]
                spacing = float(np.clip(solution[3], 480.0, 570.0))
            target = np.sum(signal * (phases[:, None] - branches[None, :] * spacing), axis=1)
            root = np.sqrt(np.maximum(occupancy, 1e-15))
            coef = np.linalg.lstsq(design * root[:, None], target / root, rcond=None)[0]
            errors = phases[:, None] - design @ coef[:, None] - branches[None, :] * spacing
            sigma = float(
                np.clip(
                    np.sqrt(np.sum(signal * errors**2) / max(signal.sum(), 1e-15)),
                    1.0,
                    2000.0 if mode == "single" else 160.0,
                )
            )
            # Small pseudocounts prevent unobserved branches from having zero probability.
            counts = probabilities.sum(axis=0) + 0.5
            weights = counts / counts.sum()
            updated, _ = _components(
                phases - design @ coef,
                branches,
                spacing,
                sigma,
                weights,
                background_offset_ns=background_prediction - design @ coef,
            )
            total = float(updated.sum() + 0.5 * np.log(weights).sum())
            if abs(total - last_score) < 1e-7 * len(times):
                break
            last_score = total
        evidence, probabilities = _components(
            phases - design @ coef,
            branches,
            spacing,
            sigma,
            weights,
            background_offset_ns=background_prediction - design @ coef,
        )
        occupancy = probabilities[:, :-1].sum(axis=1)
        covariance = sigma * sigma * np.linalg.pinv(design.T @ (design * occupancy[:, None]))
        coherence = float(abs(np.mean(np.exp(2j * np.pi * (phases - design @ coef) / spacing))))
        # Gauge: zero means the most occupied EARLY branch, never absolute truth.
        primary = branches[int(np.argmax(weights[:-1]))]
        coef[0] += primary * spacing
        labels = branches - primary
        supported = mode != "single" and coherence >= 0.25 and weights[-1] < 0.65 and sigma < 120
        candidates.append(
            PeakMixture(
                reference,
                coef,
                covariance,
                labels,
                spacing,
                sigma,
                weights,
                float(evidence.sum()),
                coherence,
                bool(supported),
                _iteration + 1,
                background.copy(),
            )
        )
    return max(candidates, key=lambda model: model.training_log_likelihood)


def _transition(dt, jerk_density):
    f = np.array([[1.0, dt, dt * dt / 2], [0.0, 1.0, dt], [0.0, 0.0, 1.0]])
    q = jerk_density * np.array(
        [
            [dt**5 / 20, dt**4 / 8, dt**3 / 6],
            [dt**4 / 8, dt**3 / 3, dt * dt / 2],
            [dt**3 / 6, dt * dt / 2, dt],
        ]
    )
    return f, q


def track_peak_mixture(
    model,
    times_s,
    phases_ns,
    *,
    start_s,
    jerk_density=1e6,
    minimum_branch_probability=0.95,
    maximum_coast_s=0.25,
):
    """Predict before observing; update only a well-supported single branch.

    Peak weights, spacing and scatter are frozen from training. Rejected points
    do not update timing. A coast expiry terminates this replay's lock; no oracle
    reacquisition. Posterior branch uncertainty and raw observations are retained.
    """
    times, phases = np.asarray(times_s, float), np.asarray(phases_ns, float)
    if times.ndim != 1 or phases.shape != times.shape or not np.all(np.isfinite(times)):
        raise ValueError("invalid tracking observations")
    if not np.all(np.isfinite(phases)) or np.any(np.diff(times) <= 0):
        raise ValueError("tracking observations must be finite and ordered")
    if np.any(times < start_s) or jerk_density < 0 or not np.isfinite(jerk_density):
        raise ValueError("invalid tracking start or process variance")
    dt = start_s - model.reference_s
    transform = np.array([[1.0, dt, dt * dt], [0.0, 1.0, 2 * dt], [0.0, 0.0, 2.0]])
    state = transform @ model.coefficients_ns
    covariance = transform @ model.covariance_ns2 @ transform.T
    last_time = start_s
    last_update = start_s
    active = model.supported
    records = []
    for time, observed in zip(times, phases, strict=True):
        transition, noise = _transition(time - last_time, jerk_density)
        state = transition @ state
        covariance = transition @ covariance @ transition.T + noise
        last_time = float(time)
        if time - last_update > maximum_coast_s:
            active = False
        raw_innovation = observed - state[0]
        evidence, probability = _components(
            raw_innovation,
            model.branches,
            model.spacing_ns,
            model.sigma_ns,
            model.weights,
            covariance[0, 0],
            float(
                _design(np.array([time]), model.reference_s)[0] @ model.background_coefficients_ns
                - state[0]
            ),
        )
        p = probability[0]
        best = int(np.argmax(p[:-1]))
        branch = int(model.branches[best])
        innovation = raw_innovation - branch * model.spacing_ns
        accepted = bool(active and p[best] >= minimum_branch_probability)
        records.append(
            dict(
                time_s=float(time),
                observed_ns=float(observed),
                prediction_ns=float(state[0]),
                prediction_std_ns=float(np.sqrt(covariance[0, 0])),
                raw_innovation_ns=float(raw_innovation),
                branch=branch,
                branch_probability=float(p[best]),
                outlier_probability=float(p[-1]),
                branch_innovation_ns=float(innovation),
                log_density=float(evidence[0]),
                accepted=accepted,
                active=bool(active),
            )
        )
        if accepted:
            gain = covariance[:, 0] / (covariance[0, 0] + model.sigma_ns**2)
            state = state + gain * innovation
            identity = np.eye(3)
            identity[:, 0] -= gain
            covariance = (
                identity @ covariance @ identity.T + np.outer(gain, gain) * model.sigma_ns**2
            )
            last_update = float(time)
    return records
