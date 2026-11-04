"""Linear-track position evidence predicted from the curved-data posterior only."""

from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3.acceptance import extend_associations
from leo.analysis.localization_v3.conservative_recovery import retained_metrics
from leo.analysis.localization_v3.history_position import make_problem
from leo.analysis.localization_v3.marginal import absolute_phase_linearization
from leo.analysis.localization_v3.position import fit
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD, profile


def geometry_features(p, position, altitude_m):
    """Same three physical modes and absolute-phase design as JointMarginal."""
    if not np.isfinite(altitude_m) or p.variant == "empirical":
        raise ValueError("finite altitude and fixed physical prior scales required")
    coordinates = p.scan.search_region.latlon(np.asarray(position)[:2])

    def frequency(phase):
        return paired_phase_frequency(
            p.sky, p.flat_times, p.flat_labels, phase, *coordinates, altitude_m=altitude_m
        )

    f, elevation = frequency(p.reference)
    derivative = (frequency(p.reference + 0.01)[0] - frequency(p.reference - 0.01)[0]) / 0.02
    intercept = absolute_phase_linearization(f, derivative, p.reference[p.flat_labels])
    phase = np.zeros((len(f), len(p.labels)))
    phase[np.arange(len(f)), p.flat_labels] = p.q * derivative * p.phase_sigma[p.flat_labels]
    modes = paired_frequency_modes(
        p.sky,
        p.mode_bank,
        p.flat_times,
        p.flat_labels,
        p.reference,
        *coordinates,
        altitude_m=altitude_m,
    )
    orbital = np.zeros((len(f), 3 * len(p.supported)))
    for k, j in enumerate(p.supported_local):
        use = p.flat_labels == j
        orbital[use, 3 * k : 3 * k + 3] = p.q[use, None] * modes[use]
    hardware = p.hardware.copy()
    hardware[:, [4, 6]] *= 10
    features = np.column_stack((hardware, p.smooth * 200, phase, orbital, p.constants))
    return dict(
        features=features,
        elevation=elevation,
        scales=np.ones(3),
        frequency=f,
        intercept=intercept,
        derivative=derivative,
    )


def conditional_gaussian(
    raw, features, sigma, power, noise_precision, prior_precision, volume_weight
):
    """Integrate or profile the same fixed diagonal Gaussian nuisance prior."""
    y, u = np.asarray(raw, float), np.asarray(features, float)
    s, power, tau = (np.asarray(v, float) for v in (sigma, power, noise_precision))
    prior = np.asarray(prior_precision, float)
    if (
        y.ndim != 1
        or not len(y)
        or u.ndim != 2
        or u.shape[0] != len(y)
        or s.shape != y.shape
        or power.shape != y.shape
        or tau.shape != y.shape
        or prior.shape != (u.shape[1],)
        or volume_weight not in (0.0, 1.0)
    ):
        raise ValueError(
            "matching observations, design, positive precisions and volume weight 0 or 1 required"
        )
    if (
        not all(np.isfinite(v).all() for v in (y, u, s, power, tau, prior))
        or any(np.any(v <= 0) for v in (s, power, tau, prior))
        or np.any(power > 1)
    ):
        raise ValueError("finite values, positive scales and powers <=1 required")
    root_weight = np.sqrt(power * tau) / s
    a, b = u * root_weight[:, None], y * root_weight
    gram = np.diag(prior) + a.T @ a
    root = np.linalg.cholesky(gram)
    coefficient = np.linalg.solve(root.T, np.linalg.solve(root, a.T @ b))
    innovation = (y - u @ coefficient) * root_weight
    ridge = coefficient * np.sqrt(prior)
    volume = max(0.0, float(2 * np.log(np.diag(root)).sum() - np.log(prior).sum()))
    quadratic = float(innovation @ innovation + ridge @ ridge)
    normalization = float(np.sum(power * (np.log(2 * np.pi) + 2 * np.log(s) - np.log(tau))))
    residual = np.r_[innovation, ridge, np.sqrt(volume_weight * volume)]
    return dict(
        coefficient=coefficient,
        residual=residual,
        quadratic=quadratic,
        logvolume=volume,
        normalization_constant=normalization,
        objective=quadratic + volume_weight * volume + normalization,
        coefficient_prior_precision=prior.copy(),
        objective_kind="conditional_Gaussian_marginal"
        if volume_weight
        else "penalized_Gaussian_profile",
        is_generalized_evidence=bool(np.any(power != 1)),
        negative_twice_elbo=quadratic + volume_weight * volume + normalization,
    )


def predictive_residual(raw, design, curved_gram, sigma, groups, bias_sigma=300.0):
    y, u = np.asarray(raw, float), np.asarray(design, float)
    gram = np.asarray(curved_gram, float)
    g = np.asarray(groups)
    if (
        gram.shape != (u.shape[1], u.shape[1])
        or g.shape != y.shape
        or not np.issubdtype(g.dtype, np.integer)
        or np.any(g < 0)
    ):
        raise ValueError("matching curved precision and integer new-curve groups required")
    root = np.linalg.cholesky(gram)
    # If A=LL', theta uncertainty is L'^-1 z, z~N(0,I).
    uncertainty = np.linalg.solve(root, u.T).T
    biases = np.zeros((len(y), int(g.max()) + 1))
    biases[np.arange(len(y)), g] = bias_sigma
    features = np.column_stack((uncertainty, biases))
    result = conditional_gaussian(
        y,
        features,
        np.asarray(sigma, float),
        np.ones(len(y)),
        np.ones(len(y)),
        np.ones(features.shape[1]),
        1.0,
    )
    return result


def linear_geometry(p, entries):
    scan = p.scan
    members = [e["track_index"] for e in entries]
    counts = [len(scan.tracks[i]["times"]) for i in members]
    n = sum(counts)
    boundaries = np.r_[0, np.cumsum(counts)]
    slices = [slice(a, b) for a, b in zip(boundaries[:-1], boundaries[1:], strict=True)]
    times = np.concatenate([scan.tracks[i]["times"] for i in members])
    labels = np.repeat([p.labels.index(e["candidate_index"]) for e in entries], counts)
    q = np.concatenate(
        [
            np.full(count, scan.tracks[i]["rf_hz"] / 11.5e9)
            for i, count in zip(members, counts, strict=True)
        ]
    )
    hardware = np.zeros((n, p.hardware.shape[1]))
    smooth = np.zeros((n, p.smooth.shape[1]))
    width = smooth.shape[1] // 2
    for i, sl in zip(members, slices, strict=True):
        t = scan.tracks[i]
        rx = t["receiver"] - 1
        band = int(t["channel"] > 4)
        hardware[sl, 2 * rx + band] = PERIOD / np.sqrt(12)
        hardware[sl, 4 + 2 * rx] = t["times"] - 150
        hardware[sl, 5 + 2 * rx] = (t["times"] - 150) * (-1 if band == 0 else 1) * 0.5
        if p.fitted_c:
            hardware[sl, 8] = (t["rf_hz"] / 1e9 - 11.5) * 200000
        smooth[sl, rx * width : (rx + 1) * width] = q[sl, None] * scan.rx_basis[i]
    fields = dict(vars(p))
    fields.update(
        flat_times=times,
        flat_labels=labels,
        q=q,
        hardware=hardware,
        smooth=smooth,
        constants=np.zeros((n, len(p.members))),
    )
    view = SimpleNamespace(**fields)
    values = np.concatenate(
        [
            scan.tracks[i]["values"] + e["alias"] * PERIOD
            for i, e in zip(members, entries, strict=True)
        ]
    )
    ids = [o for i in members for o in scan.tracks[i]["observation_ids"]]
    meta = scan.fixed_window_noise
    by_id = meta["per_observation_noise_sigma_hz"]
    sigma = np.array(
        [by_id[o] if meta["extra_parameter_BIC_gain"] > 0 else scan.radio_sigma_hz for o in ids]
    )
    return view, values, sigma, np.repeat(np.arange(len(entries)), counts), slices


def attach_predictive_linear(p, entries, powers):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    curved_calculate = p.calculate

    def calculate(position):
        c = curved_calculate(position)
        g = p.noise_groups[p.keep]
        w = np.asarray(powers)[g] * c["noise_precision"][g] / p.point_noise[p.keep] ** 2
        u = c["features"][p.keep]
        gram = np.diag(c["coefficient_prior_precision"]) + u.T @ (u * w[:, None])
        geometry = geometry_features(view, position, 0.0)
        mean = view.q * geometry["intercept"] + geometry["features"] @ c["coefficient"]
        # Unseen Gamma(2,2) noise: E[1/tau]=2, not fitted from linear points.
        prediction = predictive_residual(
            values - mean, geometry["features"], gram, sigma * np.sqrt(2), groups
        )
        c["curved_negative_twice_elbo"] = c["negative_twice_elbo"]
        c["linear_predictive_objective"] = prediction["objective"]
        c["negative_twice_elbo"] += prediction["objective"]
        c["normalization_constant"] += prediction["normalization_constant"]
        c["residual"] = np.r_[c["residual"], prediction["residual"]]
        c["linear_raw_prediction_residual_hz"] = values - mean
        c["linear_elevation"] = geometry["elevation"]
        c["linear_calibration_coefficient_unchanged"] = True
        return c

    p.calculate = calculate
    p.linear_entries = entries
    p.linear_slices = slices
    p.curved_calculate = curved_calculate
    return p


def select_entries(p, x, original_metrics):
    extra = extend_associations(p, x, original_metrics)
    lookup = {t["key"]: i for i, t in enumerate(p.scan.tracks)}
    original_ids = {o for r in original_metrics["tracks"] for o in r["observation_ids"]}
    owners = {
        j: {
            p.scan.tracks[i]["receiver"]
            for i, row, sl in zip(p.members, p.rows, p.slices, strict=True)
            if row["candidate_index"] == j and p.keep[sl].any()
        }
        for j in p.labels
    }
    selected = []
    seen = set(original_ids)
    for r in extra["tracks"]:
        i = lookup[r["component"]]
        t = p.scan.tracks[i]
        if (
            r["association_source"] != "frozen_calibration_extension"
            or i in p.scan.curved
            or len(t["times"]) < 6
        ):
            continue
        ids = set(t["observation_ids"])
        if ids & seen:
            continue
        # Existing extension uses the exact physical phase; recover its integer
        # alias against the archived CFO and frozen mean receiver calibration.
        # build a zero-alias prediction through the same physical feature builder
        e = dict(
            track_index=i,
            component=t["key"],
            candidate_index=r["candidate_index"],
            norad=r["norad"],
            alias=0,
            points=len(t["times"]),
            cross_receiver_curved_support=len(owners[r["candidate_index"]]) == 2,
            observation_ids=t["observation_ids"],
        )
        view, values, _, _, _ = linear_geometry(p, [e])
        g = geometry_features(view, x, 0.0)
        mean = view.q * g["intercept"] + g["features"] @ p.calculate(x)["coefficient"]
        e["alias"] = int(np.rint(-np.mean(values - mean) / PERIOD))
        selected.append(e)
        seen |= ids
    return selected


def refit(scan, node, keep, powers, means, model, arm, entries, *, rounds=5, iterations=48):
    reference = np.zeros(len(means))
    x = np.zeros(2)
    history = []
    for _ in range(rounds):
        p = make_problem(
            scan, node, keep, arm, reference, powers, means, model["multiplier"], model["nu"]
        )
        attach_predictive_linear(p, entries, powers)
        r = fit(p, x, iterations=iterations)
        x = np.array(r["parameters"])
        next_phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
        history.append(dict(fit=r, phase_change_s=float(max(abs(next_phase - reference)))))
        reference = next_phase
    c = p.calculate(x)
    curved = p.curved_calculate(x) if entries else c
    linear_gates = []
    for e, sl in zip(entries, getattr(p, "linear_slices", []), strict=True):
        t = scan.tracks[e["track_index"]]
        residual = c["linear_raw_prediction_residual_hz"][sl]
        terms = profile(
            residual, np.zeros(len(residual)), *scan.white[e["track_index"]], bias_sigma=300.0
        )
        noise = batch_noise_screen(terms["innovations"], t["times"])
        valid = bool(
            terms["rms"][0] <= 450
            and abs(terms["bias"][0]) <= 3000
            and int(terms["alias"][0]) == 0
            and noise["noise_screen_pass"][0]
            and min(c["linear_elevation"][sl]) >= 0
        )
        linear_gates.append(
            dict(
                component=e["component"],
                compatible=valid,
                points=e["points"],
                rms_hz=float(terms["rms"][0]),
                bias_hz=float(terms["bias"][0]),
                observation_ids=e["observation_ids"],
            )
        )
    return dict(
        endpoint_east_north_km=x,
        endpoint_latlon=scan.search_region.latlon(x),
        history=history,
        phase_reference=p.reference,
        state=p.state(x),
        gates=retained_metrics(p, x),
        linear_gates=linear_gates,
        active_points=int(keep.sum()),
        additional_predictive_points=sum(e["points"] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep] ** 2))),
        negative_twice_elbo=c["negative_twice_elbo"],
        curved_negative_twice_elbo=curved["negative_twice_elbo"],
        linear_predictive_objective=c.get("linear_predictive_objective", 0.0),
        calibration_replay_max_coefficient_difference=float(
            max(abs(c["coefficient"] - curved["coefficient"]))
        ),
        final_phase_change_s=history[-1]["phase_change_s"],
    )
