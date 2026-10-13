"""Alias-aware sparse GLRT frequency likelihood with shared hardware nuisance.

Frequency aliases live on the pilot's circle. Activity weights are shared across
all receiver/windows; receiver/band offsets, receiver drift, and an optional RF
coefficient are fitted jointly. This is a conditional composite likelihood,
pending calibration of detector marks and observation dependence.
"""

from dataclasses import dataclass

import numpy as np

from leo.analysis.sparse_glrt_likelihood import fit_weights, select_sparse

PILOT_ALIAS_HZ = 1 / 4.4e-6


@dataclass(frozen=True)
class WrappedConfig:
    scale_hz: float = 250.0
    period_hz: float = PILOT_ALIAS_HZ
    satellite_penalty: float = 30.0
    maximum_satellites: int = 40
    iterations: int = 8
    em_iterations: int = 50
    nuisance_iterations: int = 40
    drift_sigma_hz_s: float = 10.0
    coefficient_sigma_hz_ghz: float = 2000.0
    common_phase_sigma_s: float = 3.0
    relative_phase_sigma_s: float | None = None
    band_drift_sigma_hz_s: float | None = None
    satellite_bias_sigma_hz: float | None = None
    nuisance_solver: str = "irls"

    def __post_init__(self):
        if self.satellite_bias_sigma_hz is not None and (
            not np.isfinite(self.satellite_bias_sigma_hz) or self.satellite_bias_sigma_hz <= 0
        ):
            raise ValueError("positive finite satellite bias scale required")
        if self.band_drift_sigma_hz_s is not None and (
            not np.isfinite(self.band_drift_sigma_hz_s) or self.band_drift_sigma_hz_s <= 0
        ):
            raise ValueError("positive finite band drift scale required")
        if self.nuisance_solver not in ("irls", "lbfgs"):
            raise ValueError("unknown nuisance solver")
        if self.relative_phase_sigma_s is not None and (
            not np.isfinite(self.relative_phase_sigma_s) or self.relative_phase_sigma_s <= 0
        ):
            raise ValueError("positive finite relative phase scale required")
        if any(
            not np.isfinite(v) or v <= 0
            for v in (
                self.scale_hz,
                self.period_hz,
                self.drift_sigma_hz_s,
                self.coefficient_sigma_hz_ghz,
                self.common_phase_sigma_s,
            )
        ):
            raise ValueError("positive finite frequency scales required")
        if (
            self.satellite_penalty < 0
            or min(
                self.maximum_satellites,
                self.iterations,
                self.em_iterations,
                self.nuisance_iterations,
            )
            < 1
        ):
            raise ValueError("invalid sparse search parameters")


def circular(value, period=PILOT_ALIAS_HZ):
    return (np.asarray(value) + period / 2) % period - period / 2


def smooth_visibility(elevation_deg, transition_deg=5.0):
    """C1 opportunity taper above the geometric horizon, zero below it.

    The transition width is a declared model assumption, not learned from site
    position error. It removes the previous abrupt signal/clutter jump at zero.
    """
    elevation = np.asarray(elevation_deg, dtype=float)
    if not np.isfinite(elevation).all() or transition_deg <= 0:
        raise ValueError("finite elevation and positive transition required")
    x = np.clip(elevation / transition_deg, 0, 1)
    return x * x * (3 - 2 * x)


def nuisance_design(evidence, rf_hz, *, coefficient=False, band_drift=False):
    rf = np.asarray(rf_hz, dtype=float)
    groups = int(evidence.group.max()) + 1
    if groups % 2 or rf.shape != evidence.time_s.shape or not np.isfinite(rf).all():
        raise ValueError("paired receiver/band groups and finite RF required")
    labels = [f"offset-g{g}-hz" for g in range(groups)]
    columns = [evidence.group == g for g in range(groups)]
    center = (evidence.time_s.min() + evidence.time_s.max()) / 2
    span = max(1.0, (evidence.time_s.max() - evidence.time_s.min()) / 2)
    for rx in range(groups // 2):
        columns.append((evidence.group // 2 == rx) * (evidence.time_s - center) / span)
        labels.append(f"drift-rx{rx}-hz-per-half-scan")
    if band_drift:
        for rx in range(groups // 2):
            columns.append((evidence.group == 2 * rx + 1) * (evidence.time_s - center) / span)
            labels.append(f"upper-minus-lower-drift-rx{rx}-hz-per-half-scan")
    if coefficient:
        frequency = np.zeros_like(rf)
        for g in range(groups):
            mask = evidence.group == g
            if not mask.any():
                raise ValueError("all receiver/band groups require observations")
            frequency[mask] = (rf[mask] - np.mean(np.unique(rf[mask]))) / 1e9
        columns.append(frequency)
        labels.append("coefficient-hz-per-ghz")
    design = np.column_stack(columns).astype(float)
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise ValueError("hardware nuisance design is unidentifiable")
    return design, labels, span


def wrapped_ratios(evidence, prediction_hz, opportunity, design, beta, config, derivative=False):
    prediction = np.asarray(prediction_hz, dtype=float)
    opportunity = np.asarray(opportunity, dtype=float)
    design, beta = np.asarray(design, float), np.asarray(beta, float)
    if (
        prediction.ndim != 2
        or prediction.shape[0] != len(evidence.ids)
        or opportunity.shape != prediction.shape
        or design.shape[0] != len(evidence.ids)
        or beta.shape != (design.shape[1],)
        or np.any(opportunity < 0)
        or np.any(opportunity > 1)
        or any(not np.isfinite(x).all() for x in (prediction, opportunity, design, beta))
    ):
        raise ValueError("invalid alias-model arrays")
    value = np.zeros_like(prediction)
    if derivative:
        gradient, information = np.zeros_like(value), np.zeros_like(value)
    a = 2 * np.pi * config.scale_hz / config.period_hz
    rho = np.exp(-a)
    numerator = -np.expm1(-2 * a)
    base = np.expm1(-a) ** 2
    mean = prediction + (design @ beta)[:, None]
    for k in range(evidence.frequency_hz.shape[1]):
        residual = evidence.frequency_hz[:, k, None] - mean
        z = np.pi * residual / config.period_hz
        denominator = base + 4 * rho * np.sin(z) ** 2
        term = evidence.candidate_weight[:, k, None] * numerator / denominator
        value += term
        if derivative:
            gradient += term * (4 * rho * np.pi / config.period_hz) * np.sin(2 * z) / denominator
            wrapped_residual = circular(residual, config.period_hz)
            information += term * 2 / (config.scale_hz**2 + wrapped_residual**2)
    q = evidence.signal_probability[:, None] * opportunity
    return (
        (1 + q * (value - 1), q * gradient, q * information) if derivative else 1 + q * (value - 1)
    )


def fit_wrapped(
    evidence,
    prediction,
    opportunity,
    rf_hz,
    seeds,
    *,
    coefficient=False,
    config=None,
    orbit_provider=None,
):
    config = WrappedConfig() if config is None else config
    base_prediction, base_opportunity = prediction, opportunity
    bias_precision = (
        0.0 if config.satellite_bias_sigma_hz is None else 1 / config.satellite_bias_sigma_hz**2
    )
    # An additive source CFO is distinct from the within-band RF-c slope.
    bias_rf = np.ones(len(evidence.ids))
    design, labels, span = nuisance_design(
        evidence,
        rf_hz,
        coefficient=coefficient,
        band_drift=config.band_drift_sigma_hz_s is not None,
    )
    groups = int(evidence.group.max()) + 1
    precision = np.zeros(design.shape[1])
    relative_precision = (
        0.0 if config.relative_phase_sigma_s is None else 1 / config.relative_phase_sigma_s**2
    )
    if relative_precision and orbit_provider is None:
        raise ValueError("relative phase requires an orbital provider")
    precision[groups : groups + groups // 2] = 1 / (config.drift_sigma_hz_s * span) ** 2
    if config.band_drift_sigma_hz_s is not None:
        precision[groups + groups // 2 : 2 * groups] = (
            1 / (config.band_drift_sigma_hz_s * span) ** 2
        )
    if coefficient:
        precision[-1] = 1 / config.coefficient_sigma_hz_ghz**2
    results = []
    for seed in seeds:
        beta = np.zeros(design.shape[1])
        values = seed.get("beta", seed.get("offsets_hz")) if isinstance(seed, dict) else seed
        values = np.asarray(values, dtype=float)
        if values.size == groups:
            beta[:groups] = values
        elif values.shape == beta.shape:
            beta[:] = values
        else:
            raise ValueError("nuisance seed dimension mismatch")
        active = list(seed.get("active", ())) if isinstance(seed, dict) else []
        weights = seed.get("weights") if isinstance(seed, dict) else None
        phase = float(seed.get("phase_s", 0.0)) if isinstance(seed, dict) else 0.0
        shifts = np.zeros(prediction.shape[1])
        biases = np.zeros(prediction.shape[1])
        if isinstance(seed, dict) and bias_precision and seed.get("satellite_bias_hz") is not None:
            values = np.asarray(seed["satellite_bias_hz"], dtype=float)
            if values.shape != biases.shape:
                raise ValueError("satellite bias seed dimension mismatch")
            biases[:] = values
        if not np.isfinite(biases).all() or (
            bias_precision and np.max(np.abs(biases)) > 10 * config.satellite_bias_sigma_hz
        ):
            raise ValueError("finite bounded satellite bias seed required")
        if (
            isinstance(seed, dict)
            and relative_precision
            and seed.get("satellite_phase_s") is not None
        ):
            shifts[:] = seed["satellite_phase_s"]
        if not np.isfinite(shifts).all() or np.max(np.abs(shifts)) > 10:
            raise ValueError("finite bounded satellite phase seed required")

        def predict(current_phase, current_shifts, indices=None, *, current_biases):
            idx = np.arange(len(current_shifts)) if indices is None else np.asarray(indices, int)
            if orbit_provider is not None:
                output = orbit_provider.predict(
                    current_phase + current_shifts[idx] if relative_precision else current_phase,
                    indices,
                )
            else:
                output = (
                    base_prediction[:, idx],
                    base_opportunity[:, idx],
                    np.zeros((len(evidence.ids), len(idx))),
                    np.zeros((len(evidence.ids), len(idx))),
                )
            if bias_precision:
                return (output[0] + bias_rf[:, None] * current_biases[idx], *output[1:])
            return output

        def selection(ratio, incumbent, current_shifts, current_weights, current_biases):
            return select_sparse(
                ratio,
                config,
                incumbent,
                penalties=(
                    config.satellite_penalty
                    + 0.5 * relative_precision * current_shifts**2
                    + 0.5 * bias_precision * current_biases**2
                ),
                initial_weights=current_weights,
            )

        if len(active) > config.maximum_satellites or any(
            s < 0 or s >= prediction.shape[1] for s in active
        ):
            raise ValueError("invalid satellite seed")
        history, converged, previous = [], False, -np.inf
        for iteration in range(config.iterations):
            if orbit_provider is not None or bias_precision:
                prediction, opportunity, _, _ = predict(phase, shifts, current_biases=biases)
            ratio = wrapped_ratios(evidence, prediction, opportunity, design, beta, config)
            active, weights, raw, curve = selection(ratio, active, shifts, weights, biases)
            shifts[np.setdiff1d(np.arange(len(shifts)), active)] = 0.0
            biases[np.setdiff1d(np.arange(len(biases)), active)] = 0.0
            score = raw - 0.5 * np.dot(precision * beta, beta)
            if orbit_provider is not None:
                score -= 0.5 * (phase / config.common_phase_sigma_s) ** 2
            history.append(float(score))
            if not active or (iteration and abs(score - previous) < 1e-4):
                converged = True
                break
            previous = score
            if config.nuisance_solver == "lbfgs":
                from leo.analysis.wrapped_glrt_refinement import refine_wrapped

                beta, phase, shifts, weights, score, biases = refine_wrapped(
                    evidence,
                    base_prediction if bias_precision and orbit_provider is None else prediction,
                    opportunity,
                    design,
                    precision,
                    config,
                    active,
                    orbit_provider,
                    beta,
                    phase,
                    shifts,
                    weights,
                    biases=biases,
                )
                continue
            for _ in range(config.nuisance_iterations):
                if orbit_provider is not None or bias_precision:
                    local_prediction, local_opportunity, timing, opportunity_rate = predict(
                        phase, shifts, active, current_biases=biases
                    )
                else:
                    local_prediction, local_opportunity = (
                        prediction[:, active],
                        opportunity[:, active],
                    )
                ratio, gradient, information = wrapped_ratios(
                    evidence,
                    local_prediction,
                    local_opportunity,
                    design,
                    beta,
                    config,
                    True,
                )
                mixture = weights[0] + ratio @ weights[1:]
                grad = design.T @ ((gradient @ weights[1:]) / mixture) - precision * beta
                row_information = (information @ weights[1:]) / mixture
                normal = design.T @ (row_information[:, None] * design) + np.diag(precision)
                mass_information = information * weights[None, 1:] / mixture[:, None]
                if orbit_provider is not None:
                    coupling = design.T @ np.sum(mass_information * timing, axis=1)
                    opportunity_gradient = np.divide(
                        (ratio - 1) * opportunity_rate,
                        local_opportunity,
                        out=np.zeros_like(ratio),
                        where=local_opportunity > 0,
                    )
                    phase_gradient = np.sum(
                        (gradient * timing + opportunity_gradient)
                        * weights[None, 1:]
                        / mixture[:, None]
                    )
                    phase_gradient -= phase / config.common_phase_sigma_s**2
                    phase_information = (
                        np.sum(mass_information * timing**2) + 1 / config.common_phase_sigma_s**2
                    )
                    normal = np.block(
                        [
                            [normal, coupling[:, None]],
                            [coupling[None, :], np.array([[phase_information]])],
                        ]
                    )
                    grad = np.append(grad, phase_gradient)
                    if relative_precision:
                        local_gradient = (
                            np.sum(
                                (gradient * timing + opportunity_gradient)
                                * weights[None, 1:]
                                / mixture[:, None],
                                axis=0,
                            )
                            - relative_precision * shifts[active]
                        )
                        local_information = np.sum(mass_information * timing**2, axis=0)
                        local_coupling = design.T @ (mass_information * timing)
                        shared_coupling = np.vstack((local_coupling, local_information))
                        normal = np.block(
                            [
                                [normal, shared_coupling],
                                [
                                    shared_coupling.T,
                                    np.diag(local_information + relative_precision),
                                ],
                            ]
                        )
                        grad = np.concatenate((grad, local_gradient))
                if bias_precision:
                    local_bias_information = np.sum(
                        mass_information * bias_rf[:, None] ** 2, axis=0
                    )
                    bias_coupling = design.T @ (mass_information * bias_rf[:, None])
                    if orbit_provider is not None:
                        time_bias = np.sum(mass_information * timing * bias_rf[:, None], axis=0)
                        bias_coupling = np.vstack((bias_coupling, time_bias))
                        if relative_precision:
                            bias_coupling = np.vstack((bias_coupling, np.diag(time_bias)))
                    normal = np.block(
                        [
                            [normal, bias_coupling],
                            [bias_coupling.T, np.diag(local_bias_information + bias_precision)],
                        ]
                    )
                    bias_gradient = (
                        np.sum(
                            gradient * weights[None, 1:] / mixture[:, None] * bias_rf[:, None],
                            axis=0,
                        )
                        - bias_precision * biases[active]
                    )
                    grad = np.r_[grad, bias_gradient]
                informed = np.diag(normal) > 1e-18
                step = np.zeros_like(grad)
                step[informed] = np.linalg.solve(normal[np.ix_(informed, informed)], grad[informed])
                bias_step = np.zeros_like(biases)
                if bias_precision:
                    bias_step[active] = step[-len(active) :]
                    step = step[: -len(active)]
                shift_step = np.zeros_like(shifts)
                if relative_precision:
                    shift_step[active] = step[-len(active) :]
                    step = step[: -len(active)]
                phase_step = step[-1] if orbit_provider is not None else 0.0
                if orbit_provider is not None:
                    step = step[:-1]
                damping_bound = min(
                    1.0,
                    2000 / max(1.0, np.max(np.abs(design @ step))),
                    0.5 / max(0.5, abs(phase_step)),
                    0.5 / max(0.5, np.max(np.abs(shift_step))),
                    1000 / max(1000, np.max(np.abs(bias_step))),
                )
                step *= damping_bound
                phase_step *= damping_bound
                shift_step *= damping_bound
                bias_step *= damping_bound
                accepted = False
                for damping in (1.0, 0.5, 0.25, 0.125, 0.0625):
                    trial = beta + damping * step
                    trial_phase = float(np.clip(phase + damping * phase_step, -10.0, 10.0))
                    trial_shifts = np.clip(shifts + damping * shift_step, -10.0, 10.0)
                    trial_biases = (
                        np.clip(
                            biases + damping * bias_step,
                            -10 * config.satellite_bias_sigma_hz,
                            10 * config.satellite_bias_sigma_hz,
                        )
                        if bias_precision
                        else biases
                    )
                    trial[:groups] = circular(trial[:groups], config.period_hz)
                    if orbit_provider is not None or bias_precision:
                        trial_prediction, trial_opportunity, _, _ = predict(
                            trial_phase, trial_shifts, active, current_biases=trial_biases
                        )
                    else:
                        trial_prediction, trial_opportunity = local_prediction, local_opportunity
                    ratio_new = wrapped_ratios(
                        evidence,
                        trial_prediction,
                        trial_opportunity,
                        design,
                        trial,
                        config,
                    )
                    w, ll = fit_weights(ratio_new, config.em_iterations, weights)
                    proposed = (
                        ll
                        - config.satellite_penalty * len(active)
                        - 0.5 * np.dot(precision * trial, trial)
                        - 0.5 * relative_precision * np.dot(trial_shifts, trial_shifts)
                        - 0.5 * bias_precision * np.dot(trial_biases, trial_biases)
                    )
                    if orbit_provider is not None:
                        proposed -= 0.5 * (trial_phase / config.common_phase_sigma_s) ** 2
                    if proposed > score + 1e-9:
                        beta, weights, score, accepted = trial, w, proposed, True
                        phase = trial_phase
                        shifts = trial_shifts
                        biases = trial_biases
                        break
                if not accepted or (
                    np.max(np.abs(design @ step)) < 0.02
                    and abs(phase_step) < 1e-5
                    and np.max(np.abs(shift_step)) < 1e-5
                    and np.max(np.abs(bias_step)) < 0.02
                ):
                    break
        if orbit_provider is not None or bias_precision:
            prediction, opportunity, _, _ = predict(phase, shifts, current_biases=biases)
        ratio = wrapped_ratios(evidence, prediction, opportunity, design, beta, config)
        active, weights, raw, curve = selection(ratio, active, shifts, weights, biases)
        shifts[np.setdiff1d(np.arange(len(shifts)), active)] = 0.0
        biases[np.setdiff1d(np.arange(len(biases)), active)] = 0.0
        score = raw - 0.5 * np.dot(precision * beta, beta)
        if orbit_provider is not None:
            score -= 0.5 * (phase / config.common_phase_sigma_s) ** 2
        mixture = weights[0] + ratio[:, active] @ weights[1:]
        q = evidence.signal_probability[:, None] * opportunity[:, active]
        mass = weights[None, 1:] * (ratio[:, active] - (1 - q)) / mixture[:, None]
        results.append(
            dict(
                score=float(score),
                log_ratio=float(np.log(mixture).sum()),
                beta=beta.tolist(),
                phase_s=phase,
                satellite_phase_s=shifts.tolist() if relative_precision else None,
                relative_phase_prior_cost=float(0.5 * relative_precision * np.dot(shifts, shifts)),
                satellite_bias_hz=biases.tolist() if bias_precision else None,
                satellite_bias_prior_cost=float(0.5 * bias_precision * np.dot(biases, biases)),
                labels=labels,
                offsets_hz=beta[:groups].tolist(),
                drift_hz_s=(beta[groups : groups + groups // 2] / span).tolist(),
                band_drift_hz_s=(beta[groups + groups // 2 : 2 * groups] / span).tolist()
                if config.band_drift_sigma_hz_s is not None
                else None,
                coefficient_hz_ghz=float(beta[-1]) if coefficient else 0.0,
                active=active,
                weights=weights.tolist(),
                signal_support=mass.sum(axis=0).tolist(),
                effective_background=float(np.mean(1 - mass.sum(axis=1))),
                converged=converged,
                iterations=iteration + 1,
                history=history,
                cardinality_curve=curve,
                at_satellite_cap=len(active) == config.maximum_satellites,
            )
        )
    if not results:
        raise ValueError("at least one seed required")
    if max(r["score"] for r in results) < 0:
        null = {
            **results[0],
            "score": 0.0,
            "log_ratio": 0.0,
            "beta": [0.0] * design.shape[1],
            "phase_s": 0.0,
            "satellite_phase_s": [0.0] * len(shifts) if relative_precision else None,
            "relative_phase_prior_cost": 0.0,
            "satellite_bias_hz": [0.0] * len(biases) if bias_precision else None,
            "satellite_bias_prior_cost": 0.0,
            "offsets_hz": [0.0] * groups,
            "drift_hz_s": [0.0] * (groups // 2),
            "band_drift_hz_s": [0.0] * (groups // 2)
            if config.band_drift_sigma_hz_s is not None
            else None,
            "coefficient_hz_ghz": 0.0,
            "active": [],
            "weights": [1.0],
            "signal_support": [],
            "effective_background": 1.0,
            "converged": True,
            "iterations": 0,
            "history": [0.0],
            "cardinality_curve": [dict(satellites=0, log_ratio=0.0, penalized=0.0)],
            "at_satellite_cap": False,
        }
        results.append(null)
    best = max(results, key=lambda x: x["score"])
    return {
        **best,
        "starts": [
            {
                k: r[k]
                for k in ("score", "beta", "phase_s", "satellite_phase_s", "active", "converged")
            }
            for r in results
        ],
        "search_exact": False,
        "coefficient_enabled": coefficient,
    }
