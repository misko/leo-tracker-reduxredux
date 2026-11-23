"""One bounded location step with frozen physical nuisance columns."""

from time import process_time_ns
from unittest.mock import patch

import numpy as np
from scipy.linalg import cho_factor, cho_solve


ARMS = ("c0", "fitted_c")
CENTRE = np.zeros(2)


def frequency_jacobian(position, velocity, observer, observer_jacobian):
    range_vector = position - observer
    distance = np.linalg.norm(range_vector, axis=1)
    radial = np.sum(range_vector * velocity, axis=1) / distance
    rate_gradient = (range_vector * (radial / distance)[:, None] - velocity) / distance[:, None]
    return -(11.5e9 / 299792.458) * (rate_gradient @ observer_jacobian)


def observer_geometry(region):
    from leo.sky.frames import geodetic_to_ecef_km

    def observer(point):
        return geodetic_to_ecef_km(*region.latlon(point), 0.)

    axes = np.eye(2) * .010
    jacobian = np.column_stack([(observer(dx) - observer(-dx)) / .020 for dx in axes])
    return observer(CENTRE), jacobian


def site_gradient(view, observer, jacobian):
    from leo.analysis.research.continuous_curve_fit import paired_phase_states

    position, velocity = paired_phase_states(view.sky, view.flat_times, view.flat_labels,
                                             view.reference)
    return view.q[:, None] * frequency_jacobian(position, velocity, observer, jacobian)


def train_test(groups):
    held = np.zeros(len(groups), dtype=bool)
    for group in np.unique(groups):
        rows = np.flatnonzero(groups == group)
        if len(rows) > 1:
            held[rows[-min((len(rows) + 4) // 5, len(rows) - 1):]] = True
    return held


def fit_once(response, basis, gradient, half_width):
    """Least-squares profile with unit-normal nuisances and a flat site prior."""
    from tools.pipeline_eval.variants.compact_cavity_optimizer import _box_step

    gram = np.eye(basis.shape[1]) + basis.T @ basis
    signals = np.column_stack((gradient, response))
    projected_coef = cho_solve(cho_factor(gram), basis.T @ signals)
    projected_data = signals - basis @ projected_coef
    normal = projected_data.T @ projected_data + projected_coef.T @ projected_coef
    information = normal[:2, :2]
    eigenvalues = np.linalg.eigvalsh(information)
    if eigenvalues[0] <= 1e-12 * max(1., eigenvalues[-1]):
        raise np.linalg.LinAlgError("The nuisance-profiled 2D position is singular")
    # _box_step minimizes its quadratic with gradient equal to minus the RHS.
    point = _box_step(information, -normal[:2, 2], np.full(2, -half_width),
                      np.full(2, half_width))
    nuisance0 = projected_coef[:, 2]
    nuisance = nuisance0 - projected_coef[:, :2] @ point
    return point, nuisance0, nuisance, eigenvalues


def exact_readout(result, curved_mask):
    curved = result["conditional_residual_hz"][curved_mask]
    predictive = result["linear_raw_prediction_residual_hz"]
    elevation = np.minimum(0., result["elevation"][curved_mask]) / 2
    rms = lambda a: float(np.sqrt(np.mean(a**2)))
    return dict(
        robust_loss=float(result["residual"] @ result["residual"] + elevation @ elevation),
        curved_rms_hz=rms(curved), predictive_rms_hz=rms(predictive),
        all_rms_hz=rms(np.r_[curved, predictive]),
    )


def centre_rows(p, entries, powers, means):
    from leo.analysis.localization_v3 import event_position

    linear, linear_values, linear_noise, groups, _ = event_position.linear_geometry(p, entries)
    event_position.attach_event_predictive(p, entries, powers)
    original = event_position.geometry_features
    predictive = {}

    def observe(*args):
        predictive.update(original(*args))
        return predictive

    with patch.object(event_position, "geometry_features", observe):
        centre = p.calculate(CENTRE)
    if not predictive:
        raise ValueError("The frozen oracle requires the original predictive rows")
    width = centre["features"].shape[1]
    phase_slot = p.hardware.shape[1] + p.smooth.shape[1]
    prior_mean = np.zeros(width)
    prior_mean[phase_slot:phase_slot + len(means)] = means / p.phase_sigma
    masks = p.keep
    c_response = p.values - p.q * centre["intercept"] - centre["features"] @ prior_mean
    p_response = (linear_values - linear.q * predictive["intercept"]
                  - predictive["features"] @ prior_mean)
    noise = np.r_[p.point_noise[masks], np.sqrt(2.) * linear_noise]
    response = np.r_[c_response[masks], p_response] / noise
    bases = np.vstack((centre["features"][masks], predictive["features"]))
    bases[:, -len(p.members):] *= .3
    linear_bias = np.eye(len(entries))[groups] * 300.
    bases = np.column_stack((bases, np.vstack((np.zeros((masks.sum(), len(entries))),
                                               linear_bias))))
    observer, jacobian = observer_geometry(p.scan.search_region)
    gradient = np.vstack((site_gradient(p, observer, jacobian)[masks],
                          site_gradient(linear, observer, jacobian))) / noise[:, None]
    groups = np.r_[p.noise_groups[masks], len(p.members) + groups]
    return centre, response, bases / noise[:, None], gradient, groups


def arm_step(scan, node, keep, entries, means, model, arm):
    from leo.analysis.localization_v3.event_position import make_event_problem

    start = process_time_ns()
    powers = np.ones(len(node["seed"]["rows"]))
    reference = np.clip(means, -15., 15.)
    if not np.array_equal(reference, means):
        raise ValueError("Expected causal prior means within the original phase domain")
    p = make_event_problem(scan, node, keep, arm, reference, powers, means, model, [])
    centre, response, basis, gradient, groups = centre_rows(p, entries, powers, means)
    prepared_ns = process_time_ns() - start
    start = process_time_ns()
    half = scan.search_region.half_width_km
    point, _, _, eigenvalues = fit_once(response, basis, gradient, half)
    solve_ns = process_time_ns() - start
    start = process_time_ns()
    endpoint = p.calculate(point)
    exact_ns = process_time_ns() - start
    start = process_time_ns()
    held = train_test(groups)
    if not held.any():
        raise ValueError("No chronological held rows")
    move, centre_coef, moved_coef, _ = fit_once(response[~held], basis[~held], gradient[~held], half)
    centre_error = response[held] - basis[held] @ centre_coef
    moved_error = response[held] - basis[held] @ moved_coef - gradient[held] @ move
    holdout_ns = process_time_ns() - start
    return dict(
        point_km=point, latlon=scan.search_region.latlon(point),
        information_eigenvalues=eigenvalues,
        at_face=bool(np.max(np.abs(point)) >= half - 1e-9),
        centre=exact_readout(centre, keep), endpoint=exact_readout(endpoint, keep),
        held=dict(rows=int(held.sum()), training_rows=int((~held).sum()), point_km=move,
                  centre_mse=float(np.mean(centre_error**2)), moved_mse=float(np.mean(moved_error**2))),
        clocks_ns=dict(prepare_and_centre=prepared_ns, step=solve_ns, exact_endpoint=exact_ns,
                       holdout=holdout_ns),
    )
