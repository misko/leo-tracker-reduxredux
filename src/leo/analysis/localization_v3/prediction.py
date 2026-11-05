"""Causal predictive recovery with explicit context and no worker dependencies.

Targets never enter the calibration equations in this annotation stage.
Training uses fixed noise and unit family weights; prediction integrates
receiver uncertainty, per-track bias and causal orbit/phase uncertainty.
"""

import copy

import numpy as np
from scipy.linalg import cho_solve
from scipy.stats import norm
from scipy.stats import t as student

from leo.analysis.localization_v3 import numerical_policy as numerics
from leo.analysis.localization_v3.event_position import (
    attach_event_predictive,
    cached,
    make_event_problem,
    track_events,
)
from leo.analysis.localization_v3.history_position import forecast_phase_mean, make_problem
from leo.analysis.localization_v3.orbit_modes import build_modes
from leo.analysis.localization_v3.phase_reference import phase_refresh, reference_domain
from leo.analysis.localization_v3.position import fit
from leo.analysis.localization_v3.predictive_linear import geometry_features, linear_geometry
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.predictive_track import receiver_design
from leo.analysis.research.track_recovery_diagnostics import shortlist

ARMS = ("c0", "fitted_c")
PHASES = np.arange(-15.0, 15.1, 3.0)


def prior_means(d, node):
    p, _ = d["problems"]["c0"]
    old = dict(zip(p.labels, d["means"], strict=True))
    labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    new = [j for j in labels if j not in old]
    receipts = []
    if new:
        _, receipts = phase_widths(d["scan"], new)
        old.update(zip(new, forecast_phase_mean(receipts, d["model"]["shrinkage"]), strict=True))
    return (np.array([old[j] for j in labels]), receipts)


def training_factory(d, orbital_policy=None, target_family=None):

    def factory(*args, **kwargs):
        p = d.get("problem_factory", make_problem)(*args, **kwargs)
        if orbital_policy is not None and (
            orbital_policy != "target_uncertainty" or target_family is not None
        ):
            constants = p.constants.copy()
            config = (
                {"support_policy": d["support_policy"], "extra_orbital_families": [target_family]}
                if orbital_policy == "target_uncertainty"
                else {"support_policy": orbital_policy}
            )
            p = make_problem(*args, **kwargs, **config)
            p.constants[:] = constants
        p.point_noise = np.full(len(p.values), 150.0)
        return p

    return factory


def fit_training(
    d,
    node,
    keep,
    arm,
    *,
    start=(0.0, 0.0),
    predictive=False,
    orbital_policy=None,
    target_family=None,
    events=None,
    reference_limit_s=15.0,
    record_optimizer=False,
):
    if not 15 <= reference_limit_s <= 30:
        raise ValueError("reference-limit experiment is bounded to 15..30 seconds")
    means, receipts = prior_means(d, node)
    reference = np.zeros(len(means))
    x = np.asarray(start, float)
    history = []
    factory = training_factory(d, orbital_policy, target_family)
    powers = np.ones(len(d["powers"]))
    for _epoch in range(5):
        p = make_event_problem(
            d["scan"],
            node,
            keep,
            arm,
            reference,
            powers,
            means,
            d["model"],
            events or [],
            base_problem_factory=factory,
        )
        numerics.check_problem(d, p)
        if predictive:
            attach_event_predictive(p, d["entries"], powers)
        cached(p)
        f = fit(p, x, iterations=48)
        x = np.asarray(f["parameters"])
        policy = d.get("numerical_policy")
        if policy is None:
            phase, check = phase_refresh(
                p.state(x)["phases"][p.labels], reference, limit_s=reference_limit_s
            )
        else:
            phase, check = policy.refresh(
                p, p.state(x)["phases"][p.labels], reference, limit_s=reference_limit_s
            )
        if reference_limit_s > 15:
            domain = reference_domain(p.sky["time_s"], p.flat_times, p.flat_labels, phase)
            if not domain["in_domain"]:
                raise ValueError("training reference leaves existing orbit bank")
            if predictive and d["entries"]:
                view, *_ = linear_geometry(p, d["entries"])
                domain["predictive"] = reference_domain(
                    p.sky["time_s"], view.flat_times, view.flat_labels, phase
                )
                if not domain["predictive"]["in_domain"]:
                    raise ValueError("predictive training reference leaves existing orbit bank")
            check["next_reference_domain"] = domain
        delta = check["phase_change_s"]
        history.append(dict(endpoint=x, **check))
        if record_optimizer:
            history[-1]["optimizer"] = copy.deepcopy(f)
        reference = phase
    return (
        p,
        x,
        dict(
            history=history,
            new_prior_receipts=receipts,
            training_objective=p.calculate(x)["negative_twice_elbo"],
            final_phase_change_s=delta,
            phase_reference_check=check,
            endpoint_east_north_km=x,
        ),
    )


def corrected(p, x, i):
    t = p.scan.tracks[i]
    s = p.state(x)
    return (
        t["values"]
        - p.scan.hardware(t, s["beta"])
        - t["rf_hz"] / 11500000000.0 * p.scan.rx_basis[i] @ s["smooth"][t["receiver"] - 1]
    )


def training_record(d, keep, arm):
    """Portable final-problem recipe after the unchanged five-round fit."""
    if d.get('numerical_policy') is not None:
        raise ValueError('Stateful numerical training requires its original serial execution')
    p, x, meta = fit_training(d, d['node'], keep, arm)
    return dict(arm=arm, keep=np.asarray(keep).copy(), reference=p.reference.copy(),
                endpoint=x.copy(), metadata=meta)


def restore_training(d, keep, arm, record):
    """Reconstruct this invocation's fitted likelihood, never transport closures."""
    if record['arm'] != arm or not np.array_equal(record['keep'], keep):
        raise ValueError('Training recipe belongs to another arm or observation mask')
    means, _ = prior_means(d, d['node'])
    p = make_event_problem(
        d['scan'], d['node'], keep, arm, record['reference'].copy(),
        np.ones(len(d['powers'])), means, d['model'], [],
        base_problem_factory=training_factory(d))
    cached(p)
    x, meta = record['endpoint'].copy(), copy.deepcopy(record['metadata'])
    if p.calculate(x)['negative_twice_elbo'] != meta['training_objective']:
        raise ValueError('Reconstructed training likelihood differs')
    return p, x, meta


def nominate(d, base, target_index, target_train, max_candidates):
    track = d["scan"].tracks[target_index]
    available = np.flatnonzero(target_train)
    pick = available[
        np.unique(np.linspace(0, len(available) - 1, min(16, len(available))).astype(int))
    ]
    times = track["times"][pick]
    positions = {"center": np.zeros(2)}
    for a, (_, x, _) in base.items():
        positions["trained_" + a] = x
    for e in (-10.0, 0.0, 10.0):
        for n in (-10.0, 0.0, 10.0):
            positions[f"{e}_{n}"] = np.array([e, n])
    ys = {a: corrected(p, x, target_index)[pick] for a, (p, x, _) in base.items()}
    offers = []
    for _name, x in positions.items():
        ff = []
        ee = []
        for phi in PHASES:
            f, e = phase_frequency_grid(
                d["scan"].sky, times, *d["scan"].search_region.latlon(x), phase_seconds=phi
            )
            ff.append(f)
            ee.append(e)
        for arm in ARMS:
            for q in shortlist(
                ys[arm],
                times,
                track["rf_hz"] / 11500000000.0,
                np.array(ff),
                np.array(ee),
                times,
                PHASES,
                top=3,
            ):
                offers.append(dict(q, position=x, arm=arm))
    offers.sort(key=lambda q: q["cost"])
    selected = {}
    for offer in offers:
        selected.setdefault(offer["candidate_index"], offer)
        if len(selected) >= max_candidates:
            break
    return (
        list(selected.values()),
        dict(training_indices=pick, offers=offers, nomination_uses_held_points=False),
    )


def calibration_covariance(p, x):
    c = p.calculate(x)
    u = c["features"][p.keep]
    g = p.noise_groups[p.keep]
    w = c["noise_precision"][g] / p.point_noise[p.keep] ** 2
    gram = np.diag(c["coefficient_prior_precision"]) + u.T @ (u * w[:, None])
    return (c, cho_solve((np.linalg.cholesky(gram), True), np.eye(len(gram))))


def prediction_design(p, track, label, base, width):
    """Include receiver events in predictive means and their full covariance."""
    base = np.asarray(base, float)
    events = getattr(p, "events", [])
    boundary = p.event_start if events else width
    if base.ndim != 2 or base.shape[0] != len(track["times"]) or base.shape[1] > boundary:
        raise ValueError("predictive base overlaps event coordinates")
    result = np.zeros((len(track["times"]), width))
    result[:, : base.shape[1]] = base
    if events:
        if boundary + len(events) != width:
            raise ValueError("event posterior width mismatch")
        result[:, boundary:] = track_events(track, label, events)
    return result


def prediction_models(
    d,
    p,
    x,
    i,
    j,
    *,
    phase_step=0.1,
    uncalibrated_phase_mixture=False,
    return_frozen_covariance=False,
):
    """Mean/covariance mixture with original calibration coefficients untouched."""
    c, covcoef = calibration_covariance(p, x)
    before = c["coefficient"].copy()
    track = d["scan"].tracks[i]
    times = track["times"]
    n = len(times)
    q = track["rf_hz"] / 11500000000.0
    fixed = np.eye(n) * 150.0**2 * 2 + 300.0**2
    active = any(
        (
            r["candidate_index"] == j and p.keep[sl].any()
            for r, sl in zip(p.rows, p.slices, strict=True)
        )
    )
    if j in p.labels and (not (uncalibrated_phase_mixture and (not active))):
        if return_frozen_covariance:
            raise ValueError(
                "frozen receiver decomposition requires an uncalibrated satellite family"
            )
        view, *_ = linear_geometry(p, [dict(track_index=i, candidate_index=j, alias=0)])
        geometry = geometry_features(view, x, 0.0)
        h = prediction_design(p, track, j, geometry["features"], len(before))
        means = (q * geometry["intercept"] + h @ c["coefficient"])[None]
        covariance = (fixed + h @ covcoef @ h.T)[None]
        phases = np.array([p.state(x)["phases"][j]])
        logprior = np.zeros(1)
        elevations = np.array([geometry["elevation"].min()])
        receipt = dict(
            kind="existing_shared_posterior", candidate_index=j, active_curved_family=active
        )
    else:
        receiver = receiver_design(
            times,
            track["rf_hz"],
            track["receiver"],
            track["channel"],
            d["scan"].rx_basis[i],
            fitted_c=p.fitted_c,
        )
        h = prediction_design(p, track, j, receiver, len(before))
        calibration_mean = h @ before
        frozen_covariance = h @ covcoef @ h.T
        fixed += frozen_covariance
        widths, history = phase_widths(d["scan"], [j])
        mean = float(forecast_phase_mean(history, d["model"]["shrinkage"])[0])
        sigma = float(widths[0] * d["model"]["multiplier"])
        nu = d["model"]["nu"]
        phases = np.linspace(-15, 15, int(round(30 / phase_step)) + 1)
        distribution = (
            norm(loc=mean, scale=sigma) if nu is None else student(nu, loc=mean, scale=sigma)
        )
        logprior = distribution.logpdf(phases)
        logprior[[0, -1]] -= np.log(2)
        bank = {key: d["scan"].sky[key][[j]] for key in ["position_km", "velocity_km_s"]}
        bank["time_s"] = d["scan"].sky["time_s"]
        modes, metadata = build_modes(d["scan"], [j], [j], "physical")
        means = []
        covariance = []
        elevations = []
        for phase in phases:
            f, e = paired_phase_frequency(
                bank, times, np.zeros(n, int), np.array([phase]), *d["scan"].search_region.latlon(x)
            )
            u = q * paired_frequency_modes(
                bank,
                modes,
                times,
                np.zeros(n, int),
                np.array([phase]),
                *d["scan"].search_region.latlon(x),
            )
            means.append(calibration_mean + q * f)
            covariance.append(fixed + u @ u.T)
            elevations.append(e.min())
        means = np.asarray(means)
        covariance = np.asarray(covariance)
        elevations = np.asarray(elevations)
        receipt = dict(
            kind="new_family_causal_phase_mixture"
            if j not in p.labels
            else "uncalibrated_family_causal_phase_mixture",
            candidate_index=j,
            active_curved_family=active,
            phase_prior_mean_s=mean,
            phase_prior_sigma_s=sigma,
            phase_prior_nu=nu,
            prior_mass_in_phase_box=float(distribution.cdf(15) - distribution.cdf(-15)),
            phase_step_s=float(phases[1] - phases[0]),
            history=history,
            orbital_prior=metadata,
        )
    logprior[elevations < 0] = -np.inf
    np.testing.assert_array_equal(before, p.calculate(x)["coefficient"])
    result = (means, covariance, logprior, phases, elevations, receipt)
    return result + (frozen_covariance,) if return_frozen_covariance else result


def check_predictive_role(p, track_index, allow_inactive_member=False):
    if track_index not in p.members:
        return
    if not allow_inactive_member:
        raise ValueError("use curved annotation for a calibration member")
    k = p.members.index(track_index)
    if p.keep[p.slices[k]].any():
        raise ValueError("predictive-role target already has active calibration observations")
