"""Training-only coherent track identity proposals; production-score acceptance.

This research model gives each disjoint automatic carrier segment one latent
satellite identity, with independent point clutter inside that segment. Its
trajectory likelihood is a proposal objective, not the production scoring rule.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
from scipy.optimize import linear_sum_assignment, minimize
from scipy.sparse import csr_matrix
from scipy.special import logsumexp

ALIAS_HZ = 1 / 4.4e-6


def circular(value):
    return (np.asarray(value) + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def training_observations(context):
    """Select before reading measured CFO, including during track construction."""
    obs, mask = context.observations, np.asarray(context.train_mask)
    if mask.dtype != bool or mask.shape != np.asarray(obs.times_s).shape or not mask.any():
        raise ValueError("A nonempty full-length boolean training mask is required")
    return SimpleNamespace(**{name: np.asarray(getattr(obs, name))[mask].copy()
        for name in ("times_s", "measured_hz", "rf_hz", "receiver", "channel")})


def build_tracklets(observations, *, gate_hz=450.0, maximum_duration_s=45.0,
                    maximum_points=24):
    """Disjoint RX/channel carrier segments with velocity-aware crossing links.

    Match simultaneous points jointly. Large temporal gaps, frequency breaks,
    and the finite segment duration permit a different source identity later.
    No candidate identities or held observations participate in construction.
    """
    t, y = observations.times_s, observations.measured_hz
    output = []
    groups = sorted(set(zip(observations.receiver, observations.channel)))
    for receiver, channel in groups:
        rows = np.flatnonzero((observations.receiver == receiver) &
                              (observations.channel == channel))
        rows = rows[np.argsort(t[rows], kind="stable")]
        delta = np.diff(np.unique(t[rows]))
        maximum_gap = max(2.0, min(30.0, 5.0 * float(np.median(delta)))) if len(delta) else 2.0
        consecutive_dt = np.diff(t[rows])
        sequential = consecutive_dt > 0
        # Receiver chirps can exceed the orbital slope by orders of magnitude.
        # Estimate their robust common drift from training data before linking;
        # a fixed small raw-frequency gate otherwise makes every row a singleton.
        rates = circular(np.diff(y[rows]))[sequential] / consecutive_dt[sequential]
        common_velocity = float(np.clip(np.median(rates), -20000., 20000.)) if len(rates) else 0.
        tracks = []
        for stamp in np.unique(t[rows]):
            batch = rows[t[rows] == stamp]
            active = [tr for tr in tracks if stamp - t[tr[-1]] <= maximum_gap
                      and stamp - t[tr[0]] <= maximum_duration_s
                      and len(tr) < maximum_points]
            matched = set()
            if active:
                prediction = []
                for tr in active:
                    velocity = common_velocity
                    if len(tr) > 1:
                        velocity = np.clip(circular(y[tr[-1]] - y[tr[-2]]) /
                                           (t[tr[-1]] - t[tr[-2]]),
                                           common_velocity - 600., common_velocity + 600.)
                    prediction.append(y[tr[-1]] + velocity * (stamp - t[tr[-1]]))
                cost = abs(circular(y[batch][None, :] - np.asarray(prediction)[:, None]))
                aa, bb = linear_sum_assignment(cost)
                for a, b in zip(aa, bb):
                    if cost[a, b] <= gate_hz:
                        active[a].append(int(batch[b]))
                        matched.add(int(batch[b]))
            tracks.extend([[int(row)] for row in batch if int(row) not in matched])
        output.extend(np.asarray(tr, dtype=int) for tr in tracks)
    labels = np.empty(len(t), dtype=int)
    for index, rows in enumerate(output):
        labels[rows] = index
    # The one-row/one-segment invariant prevents overlapping evidence counting.
    flattened = np.concatenate(output)
    if len(flattened) != len(t) or not np.array_equal(np.sort(flattened), np.arange(len(t))):
        raise ValueError("Tracklets must partition training observations exactly once")
    return labels


class TrajectoryLikelihood:
    """Robust shared latent identity with a segment-level all-clutter option."""

    def __init__(self, labels, sigma_hz, candidate_prior, visibility, *, clutter_fraction=.12):
        self.labels = np.asarray(labels, int)
        if not len(self.labels) or np.any(self.labels < 0):
            raise ValueError("Nonempty contiguous segment labels required")
        self.count = int(self.labels.max()) + 1
        self.membership = csr_matrix((np.ones(len(labels)), (self.labels, np.arange(len(labels)))),
                                     shape=(self.count, len(labels)))
        self.lengths = np.asarray(self.membership.sum(axis=1)).ravel()
        if np.any(self.lengths == 0):
            raise ValueError("Contiguous nonempty segment labels required")
        self.sigma = np.broadcast_to(np.asarray(sigma_hz, float), (len(labels),))
        prior = np.asarray(candidate_prior, float)
        self.visibility = np.asarray(visibility, float)
        if self.visibility.shape != (len(labels), len(prior)) or np.any(prior <= 0):
            raise ValueError("Aligned visibility and positive fixed-bank candidate priors required")
        self.logprior = np.log(.9 * prior / prior.sum())
        self.epsilon = float(clutter_fraction)
        if not 0 < self.epsilon < 1 or np.any(self.sigma <= 0):
            raise ValueError("Positive sigma and interior point-clutter fraction required")

    def evaluate(self, residual):
        residual = circular(residual)
        signal = ((1 - self.epsilon) * self.visibility *
                  np.exp(-.5 * (residual / self.sigma[:, None]) ** 2) /
                  (np.sqrt(2 * np.pi) * self.sigma[:, None]))
        total = signal + self.epsilon / ALIAS_HZ
        candidate_log = self.membership @ np.log(total) + self.logprior
        clutter_log = np.log(.1) - self.lengths * np.log(ALIAS_HZ)
        lognormal = logsumexp(np.column_stack((candidate_log, clutter_log)), axis=1)
        posterior = np.exp(candidate_log - lognormal[:, None])
        weights = posterior[self.labels] * signal / total
        # Gradient with respect to a change in prediction, rather than residual.
        prediction_gradient = -weights * residual / self.sigma[:, None] ** 2
        return -float(lognormal.sum()), prediction_gradient, posterior, weights


def fit(context, *, max_evaluations=180, max_seconds=120):
    """Spend a bounded part of the shared budget on a coherent timing proposal."""
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.hard60_bounded_fit import _Problem
    from common import refit

    started = time.monotonic()
    deadline = min(started + max_seconds, getattr(context, "deadline", float("inf")))
    model = context.model
    vector, nuisance = np.asarray(context.vector).copy(), np.asarray(context.nuisance).copy()
    obs = training_observations(context)
    if not np.array_equal(model.mask, context.train_mask):
        raise ValueError("Shared objective and proposal training masks differ")
    labels = build_tracklets(obs)
    initial, details = model.evaluate_details(vector, nuisance)
    residual = initial[3].residual_hz.copy()
    tau = vector[7] + model.basis @ vector[8:]
    _, _, _, derivative = predict_orbits(context.bank, model.scored_observations,
        context.prior, vector[:2], tau)
    likelihood = TrajectoryLikelihood(labels, details["sigma_hz"],
        details["detection_probability"], details["visibility_weight"])
    fixed_c = bool(getattr(context, "fixed_c", False))
    # The existing calibration design contains actual-RF scaling, not channel IDs.
    calibration_design = model.original.design[context.train_mask]
    scales = np.array([100., 1., 100., 1., 100.])
    if fixed_c:
        scales[-1] = 0.
    design = calibration_design * scales[None, :]
    candidate_count = len(tau)
    proposal_budget = min(48, max(1, max_evaluations // 3))
    calls = 0
    best = [float("inf"), np.zeros(candidate_count + 5)]
    initial_trajectory, _, posterior, _ = likelihood.evaluate(residual)

    class BudgetReached(Exception):
        pass

    def objective(change):
        nonlocal calls
        if (calls >= proposal_budget or time.monotonic() >= deadline or
                time.monotonic() - started >= max_seconds * .40):
            raise BudgetReached
        calls += 1
        timing_change, calibration = change[:candidate_count], change[candidate_count:]
        rr = residual - derivative * timing_change[None, :] - (design @ calibration)[:, None]
        value, gradient, _, _ = likelihood.evaluate(rr)
        # Match the original absolute common/relative timing priors in proposals.
        target = tau + timing_change
        common = target.mean()
        relative = target - common
        value += .5 * (common / model.score.common_sigma_s) ** 2
        value += .5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
        value += .5 * float(calibration @ calibration)
        timing_gradient = np.sum(gradient * derivative, axis=0)
        timing_gradient += common / (candidate_count * model.score.common_sigma_s ** 2)
        timing_gradient += relative / model.score.relative_sigma_s ** 2
        grad = np.r_[timing_gradient, design.T @ gradient.sum(axis=1) + calibration]
        if value < best[0]:
            best[:] = [float(value), change.copy()]
        return value, grad

    try:
        minimize(objective, np.zeros(candidate_count + 5), jac=True, method="L-BFGS-B",
                 bounds=[(-3., 3.)] * candidate_count + [(-2., 2.)] * 5,
                 options={"maxfun": proposal_budget, "maxiter": proposal_budget,
                          "ftol": 1e-8, "gtol": 1e-4, "maxls": 12})
    except BudgetReached:
        pass
    change = best[1]
    proposal = vector.copy()
    target = tau + change[:candidate_count]
    proposal[7] = target.mean()
    proposal[8:] = model.basis.T @ (target - proposal[7])
    proposal[2:7] += scales * change[candidate_count:]
    proposal = _Problem(model, proposal, rf_arm="zero-c" if fixed_c else "fitted-c").start
    remaining_time = max(.1, deadline - time.monotonic())
    result = refit(context, proposal, nuisance,
                   max_evaluations=max(1, max_evaluations - calls - 2),
                   max_seconds=remaining_time, fixed_c=fixed_c)
    final_vector, final_nuisance = np.asarray(result["vector"]), np.asarray(result["nuisance"])
    final_score = float(result["diagnostics"]["objective"])
    accepted = bool(np.isfinite(final_score) and final_score <= initial[0])
    if not accepted:
        final_vector, final_nuisance = vector, nuisance
    alternatives = []
    sizes = np.bincount(labels)
    for label in np.argsort(-sizes, kind="stable")[:24]:
        rows = np.flatnonzero(labels == label)
        order = np.argsort(-posterior[label])[:3]
        alternatives.append(dict(points=len(rows), receiver=int(obs.receiver[rows[0]]),
            channel=int(obs.channel[rows[0]]), start_s=float(obs.times_s[rows].min()),
            end_s=float(obs.times_s[rows].max()),
            clutter_probability=float(1. - posterior[label].sum()),
            candidates=[dict(satellite=int(context.bank.numbers[k]),
                             posterior=float(posterior[label, k])) for k in order]))
    refinement = result.get("diagnostics", {})
    diagnostics = dict(method="disjoint-track-shared-latent-identity", training_only=True,
        tracklets=len(np.unique(labels)), points=len(labels),
        multi_point_tracklets=int(np.sum(np.bincount(labels) > 1)),
        largest_tracklet=int(np.bincount(labels).max()), proposal_evaluations=calls + 1,
        proposal_optimizer_evaluations=calls,
        orbit_projection_calls=1, common_objective_evaluations=1 + refinement.get("evaluations", 0),
        evaluations=2 + calls + refinement.get("evaluations", 0),
        candidate_alternatives=alternatives,
        initial_trajectory_nll=float(initial_trajectory),
        initial_mean_track_identity_posterior=float(posterior.max(axis=1).mean()),
        proposal_surrogate_with_priors=float(best[0]),
        common_initial_objective=float(initial[0]), common_refit_objective=final_score,
        accepted_by_common_objective=accepted, fixed_c=fixed_c,
        refit=refinement, elapsed_seconds=time.monotonic() - started,
        qualification="Trajectory likelihood proposes only; final endpoint acceptance and "
        "reported associations use the unchanged common production objective. Linearized "
        "timing proposals are re-evaluated with exact orbit predictions during common refit.")
    return dict(vector=final_vector, nuisance=final_nuisance, diagnostics=diagnostics)
