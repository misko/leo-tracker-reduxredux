"""Profile the released shared design against covariance-weighted track shapes."""

from time import process_time_ns

import numpy as np
from scipy.linalg import qr


TOLERANCE = 1e-8
ARC_BIAS_HZ = 300.


class TrackNoise:
    def __init__(self, groups, noise):
        keys, self.index = np.unique(np.asarray(groups), return_inverse=True)
        sigma = np.asarray(noise, float)
        if not len(keys) or sigma.shape != self.index.shape or not np.isfinite(sigma).all() or np.any(sigma <= 0.):
            raise ValueError("Require ordered track groups and positive finite noise")
        self.inverse = 1. / sigma
        self.weight = self.inverse**2
        self.total = np.bincount(self.index, weights=self.weight)

    def apply(self, rows, *, track_means):
        """Represent whitened adjacent differences isometrically in original row space."""
        data = np.asarray(rows, float)
        total = np.zeros((len(self.total), data.shape[1]))
        np.add.at(total, self.index, self.weight[:, None] * data)
        means = total / self.total[:, None]
        centered = (data - means[self.index]) * self.inverse[:, None]
        if track_means:
            # Independent mean channel under a per-track common random intercept.
            affine_noise = np.sqrt(ARC_BIAS_HZ**2 + 1. / self.total)
            return np.vstack((centered, means / affine_noise[:, None]))
        return centered


def profile_space(design, original_norm):
    norms = np.linalg.norm(design, axis=0)
    live = norms > TOLERANCE * np.asarray(original_norm)
    # Trim constant and numerically empty columns before normalizing.
    if not live.any():
        return np.empty((len(design), 0)), live, np.empty(0)
    orthogonal, upper, _ = qr(design[:, live] / norms[live], mode="economic", pivoting=True, check_finite=True)
    diagonal = np.abs(np.diag(upper))
    rank = int(np.count_nonzero(diagonal > TOLERANCE*diagonal[0]))
    return orthogonal[:, :rank], live, diagonal


def project(space, rows):
    return rows - space @ (space.T @ rows)


class Geometry:
    def __init__(self, problem, entries):
        from leo.analysis.localization_v3.predictive_linear import linear_geometry

        p = problem
        self.p = p
        self.linear, values, noise, groups, _ = linear_geometry(p, entries)
        self.values = np.r_[p.values[p.keep], values]
        independent_sigma = np.r_[p.point_noise[p.keep], np.sqrt(2.)*noise]
        group = np.r_[p.noise_groups[p.keep], len(p.members)+groups]
        self.noise = TrackNoise(group, independent_sigma)

    def state(self, point):
        from leo.analysis.localization_v3.marginal import JointMarginal
        from leo.analysis.localization_v3.predictive_linear import geometry_features

        p = self.p
        a = JointMarginal.calculate(p, point, geometry_only=True)
        b = geometry_features(self.linear, point, 0.)
        frequency = np.r_[(p.q * a["intercept"])[p.keep], self.linear.q*b["intercept"]]
        design = np.vstack((a["features"][p.keep], b["features"]))[:, :-len(p.members)]
        return frequency, design


def information(tangent):
    eigenvalues, axes = np.linalg.eigh(tangent.T @ tangent)
    return dict(eigenvalues=eigenvalues, weaker_axis_east_north=axes[:, 0],
                weaker_1sigma_km=None if eigenvalues[0] <= 0. else float(1./np.sqrt(eigenvalues[0])),
                numerical_rank=int(np.count_nonzero(eigenvalues > TOLERANCE * max(1., eigenvalues[-1]))))


def estimate(geometry, half, *, track_means):
    from centre_oracle_iterative import trust_fit

    noise, centre = geometry.noise, np.zeros(2)
    f0, design0 = geometry.state(centre)
    derivatives = np.column_stack([(geometry.state(step)[0] - geometry.state(-step)[0]) / .020
                                  for step in np.eye(2)*.010])
    transformed = noise.apply(np.column_stack((design0, derivatives)), track_means=track_means)
    baseline_norm = np.linalg.norm(design0 * noise.inverse[:, None], axis=0)
    design, tangent = transformed[:, :-2], transformed[:, -2:]
    space, live, diagonal = profile_space(design, baseline_norm)
    rank = space.shape[1]
    shaped = information(tangent)
    profiled = information(project(space, tangent))
    if profiled["numerical_rank"] < 2:
        return dict(status="insufficient_rank", nominal=shaped, profiled=profiled, nuisance_rank=rank)

    def profile(point):
        nominal, raw_design = geometry.state(point)
        prepared = noise.apply(np.column_stack((raw_design, geometry.values-nominal)), track_means=track_means)
        scale = np.linalg.norm(raw_design * noise.inverse[:, None], axis=0)
        basis, _, _ = profile_space(prepared[:, :-1], scale)
        if basis.shape[1] != rank:
            raise np.linalg.LinAlgError("The shared contrast design changes numerical rank within the bounded fit")
        return project(basis, prepared[:, -1]), {}

    start = process_time_ns()
    try:
        result = trust_fit(profile, np.full(2, -half), np.full(2, half))
    except np.linalg.LinAlgError as error:
        return dict(status="unstable_profile_rank", reason=str(error), nominal=shaped, profiled=profiled, nuisance_rank=rank,
                    trust_cpu_ns=process_time_ns()-start)
    point = result["history"][-1]["point"]
    nominal_at_fit, fitted_columns = geometry.state(point)
    # The Moore-Penrose c estimate exists only when its column survives alone
    # and independently of all other nuisance columns.
    calibration = None
    conditional_c_column = None
    if geometry.p.fitted_c:
        values = noise.apply(np.column_stack((fitted_columns, geometry.values-nominal_at_fit)), track_means=track_means)
        remaining = np.arange(len(baseline_norm)) != 8
        nuisance, _, _ = profile_space(values[:, :-1][:, remaining], baseline_norm[remaining])
        column, response = project(nuisance, values[:, [8, values.shape[1]-1]]).T
        norm = float(np.linalg.norm(column))
        conditional_c_column = norm
        if norm > TOLERANCE*baseline_norm[8]:
            calibration = float(200_000 * (column @ response) / norm**2)
    return dict(status="diagnostic_only", latlon=geometry.p.scan.search_region.latlon(point), point_km=point,
                face=bool(np.max(np.abs(point)) >= half - 1e-9), nominal=shaped, profiled=profiled,
                nuisance_rank=rank, nuisance_columns=len(live), nonconstant_columns=int(live.sum()), qr_diagonal=diagonal,
                fitted_c_column_alive=bool(live[8]) if geometry.p.fitted_c else None,
                fitted_c_independent_norm=conditional_c_column, fitted_c_hz_per_ghz=calibration,
                trace=result, trust_cpu_ns=process_time_ns()-start)


def arm_fit(scan, node, keep, entries, means, model, arm):
    from leo.analysis.localization_v3.event_position import attach_event_predictive, make_event_problem
    from centre_oracle_step import exact_readout

    start = process_time_ns()
    powers = np.ones(len(node["seed"]["rows"]))
    reference = np.clip(means, -15., 15.)
    p = make_event_problem(scan, node, keep, arm, reference, powers, means, model, [])
    geometry = Geometry(p, entries)
    half = scan.search_region.half_width_km
    preparation = process_time_ns()-start
    start = process_time_ns()
    results = {name: estimate(geometry, half, track_means=with_means)
               for name, with_means in (("shape", False), ("shape_and_mean", True))}
    estimate_ns = process_time_ns()-start
    start = process_time_ns()
    attach_event_predictive(p, entries, powers)
    base = exact_readout(p.calculate(np.zeros(2)), keep)
    for result in results.values():
        if "point_km" in result:
            result["endpoint_rf_check"] = exact_readout(p.calculate(result["point_km"]), keep)
    return dict(results=results, centre_rf_check=base, observations=len(geometry.values), tracks=len(geometry.noise.total),
                arc_shape_dof=len(geometry.values)-len(geometry.noise.total), geometry_preparation_cpu_ns=preparation,
                estimate_cpu_ns=estimate_ns, full_objective_check_cpu_ns=process_time_ns()-start)
