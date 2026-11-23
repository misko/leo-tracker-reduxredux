"""Exactly reproject the frozen Gaussian owner-oracle profile at each location."""

from time import process_time_ns

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from centre_oracle_step import CENTRE, exact_readout


class Profile:
    def __init__(self, curved, entries, means):
        from leo.analysis.localization_v3.predictive_linear import linear_geometry

        self.curved = curved
        self.predictive, linear_values, noise, groups, _ = linear_geometry(curved, entries)
        self.nuisance_mean = np.zeros(self.width)
        self.phase_start = curved.hardware.shape[1] + curved.smooth.shape[1]
        self.nuisance_mean[self.phase_start:self.phase_start + len(means)] = means / curved.phase_sigma
        self.values = np.r_[curved.values[curved.keep], linear_values]
        self.noise = np.r_[curved.point_noise[curved.keep], np.sqrt(2.) * noise]
        self.predictive_bias = np.vstack((
            np.zeros((curved.keep.sum(), len(entries))),
            300. * np.eye(len(entries))[groups],
        ))
        self.means = means

    @property
    def width(self):
        p = self.curved
        return p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels) + 3 * len(p.supported) + len(p.members)

    def __call__(self, point):
        from leo.analysis.localization_v3.marginal import JointMarginal
        from leo.analysis.localization_v3.predictive_linear import geometry_features

        p = self.curved
        c = JointMarginal.calculate(p, point, geometry_only=True)
        linear = geometry_features(self.predictive, point, 0.)
        nominal = np.r_[
            (p.q * c["intercept"])[p.keep],
            self.predictive.q * linear["intercept"],
        ]
        shared = np.vstack((c["features"][p.keep], linear["features"]))
        response = (self.values - nominal - shared @ self.nuisance_mean) / self.noise
        shared[:, -len(p.members):] *= .3
        design = np.column_stack((shared, self.predictive_bias)) / self.noise[:, None]
        gram = np.eye(design.shape[1]) + design.T @ design
        coefficient = cho_solve(cho_factor(gram), design.T @ response)
        residual = np.r_[response - design @ coefficient, coefficient]
        phase = self.means + p.phase_sigma * coefficient[
            self.phase_start:self.phase_start + len(self.means)]
        return residual, {
            "phase_s": dict(zip((int(p.scan.norads[i]) for i in p.labels), phase, strict=True)),
            "c_hz_per_ghz": float(coefficient[8] * 200_000) if p.fitted_c else 0.,
        }


def trust_fit(profile, low, high):
    from tools.pipeline_eval.variants.compact_cavity_optimizer import (
        INITIAL_RADIUS_KM,
        MAX_RADIUS_KM,
        MIN_DECREASE,
        STOP_KM,
        TRIALS,
        _box_step,
        _forward_points,
    )

    evaluations, accepted = [], []

    def evaluate(point, role, iteration):
        start = process_time_ns()
        vector, nuisance = profile(point)
        cost = float(vector @ vector)
        if not np.isfinite(cost):
            raise ValueError("Expected a finite profiled objective throughout the bounded trial")
        evaluations.append(dict(point=point, role=role, iteration=iteration,
                                objective=cost, cpu_ns=process_time_ns()-start))
        return vector, nuisance, cost

    point = CENTRE.copy()
    residual, nuisance, cost = evaluate(point, "centre", 0)
    accepted.append(dict(point=point, objective=cost, **nuisance))
    radius = INITIAL_RADIUS_KM
    reason = "iteration_budget"
    full_move = None
    for iteration in range(1, 7):
        j = np.column_stack([
            (evaluate(nearby, "derivative", iteration)[0] - residual) / distance
            for _, nearby, distance in _forward_points(point, low, high, 1e-3)
        ])
        gram = j.T @ j
        gram += 1e-8 * np.diag(np.maximum(np.diag(gram), 1e-6))
        gradient = j.T @ residual
        full_move = float(np.linalg.norm(_box_step(gram, gradient, low-point, high-point)))
        if full_move <= STOP_KM:
            reason = "small_bounded_step"
            break
        for _ in range(TRIALS):
            delta = _box_step(gram, gradient, np.maximum(low-point, -radius),
                              np.minimum(high-point, radius))
            next_point = np.clip(point + delta, low, high)
            trial, nuisance, next_cost = evaluate(next_point, "trial", iteration)
            improvement = cost - next_cost
            if improvement <= MIN_DECREASE:
                evaluations[-1]["accepted"] = False
                radius *= .5
                continue
            approximation = residual + j @ (next_point-point)
            expected = cost - float(approximation @ approximation)
            ratio = improvement / expected if expected > 0 else 0.
            evaluations[-1]["accepted"] = True
            accepted.append(dict(point=next_point, objective=next_cost, radius_km=radius,
                                 ratio=ratio, **nuisance))
            if ratio < .25:
                radius *= .5
            elif ratio > .75 and np.max(abs(delta)) >= .8 * radius:
                radius = min(MAX_RADIUS_KM, 2 * radius)
            point, residual, cost = next_point, trial, next_cost
            break
        else:
            reason = "no_accepted_trial"
            break
    return dict(history=accepted, evaluations=evaluations, stopped=reason,
                last_tested_full_step_km=full_move, accepted_steps=len(accepted)-1)


def arm_iterative(scan, node, keep, entries, means, model, arm):
    from leo.analysis.localization_v3.event_position import attach_event_predictive, make_event_problem

    start = process_time_ns()
    powers = np.ones(len(node["seed"]["rows"]))
    reference = np.clip(means, -15., 15.)
    if not np.array_equal(reference, means):
        raise ValueError("The iterative trial requires the same causal phase chart")
    p = make_event_problem(scan, node, keep, arm, reference, powers, means, model, [])
    profile = Profile(p, entries, means)
    prepare_ns = process_time_ns() - start
    start = process_time_ns()
    result = trust_fit(profile, p.lower, p.upper)
    fitting_ns = process_time_ns() - start
    evaluations = {}
    start = process_time_ns()
    attach_event_predictive(p, entries, powers)
    for stage, point in (("centre", CENTRE), ("first", result["history"][min(1, result["accepted_steps"])]["point"]),
                         ("final", result["history"][-1]["point"])):
        key = tuple(point)
        if key not in evaluations:
            evaluations[key] = exact_readout(p.calculate(point), keep)
        result[stage] = dict(point_km=point, latlon=scan.search_region.latlon(point),
                             authoritative=evaluations[key])
    result["clocks_ns"] = dict(preparation=prepare_ns, fit=fitting_ns,
                               authoritative_checks=process_time_ns()-start)
    return result
