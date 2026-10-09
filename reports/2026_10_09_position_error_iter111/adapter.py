"""Complete-data conditional frequency information at an ordinary B7 endpoint.

This freezes responsibilities, visibility and the wrapped-frequency branch.
It is not observed mixture curvature, full posterior information or covariance.
The complete-data proxy omits the mixture score-covariance subtraction and
nonlinear residual second derivatives; it can overstate observed information.
Responsibilities are arm-specific at matched observations/bank, not argmax labels.
No reference position enters the adapter. Dense storage is O(N*K*P), never
O((N*K)**2); callers must budget memory before constructing a cohort diagnostic.
"""

import numpy as np


def frequency_design(model, vector, clock, *, predictor=None):
    """Exact local frequency Jacobian in the model's parameter coordinates."""
    if predictor is None:
        from leo.analysis.hard60_score import predict_orbits

        predictor = predict_orbits
    vector, clock = np.asarray(vector, float), np.asarray(clock, float)
    if vector.shape != (model.size,) or clock.shape != model.initial_clock.shape:
        raise ValueError("endpoint vector/clock shapes do not match model")
    if not np.isfinite(vector).all() or not np.isfinite(clock).all():
        raise ValueError("endpoint must be finite")
    prediction, _, spatial, timing = predictor(
        model.bank,
        model.observations,
        model.prior,
        vector[:2],
        vector[7] + model.basis @ vector[8:],
    )
    prediction = prediction.copy()
    prediction += (model.design @ vector[2:7] + model.baseline + model.clock_design @ clock)[
        :, None
    ]
    n, k = prediction.shape
    jacobian = np.zeros((n, k, model.size + len(clock)))
    jacobian[:, :, :2] = spatial
    jacobian[:, :, 2:7] = model.design[:, None, :]
    jacobian[:, :, 7] = timing
    jacobian[:, :, 8 : model.size] = timing[:, :, None] * model.basis[None, :, :]
    jacobian[:, :, model.size :] = model.clock_design[:, None, :]
    if hasattr(model, "satellite_basis"):
        for selection, factor in (
            (model.offset_slice, np.ones((n, k))),
            (model.slope_slice, model.delta_time),
        ):
            if selection.stop > selection.start:
                correction = factor[:, :, None] * model.satellite_basis[None, :, :]
                jacobian[:, :, model.size + selection.start : model.size + selection.stop] += (
                    correction
                )
                prediction += np.einsum("nkp,p->nk", correction, clock[selection])
    return prediction, jacobian


def construct(model, endpoint, arm, *, predictor=None):
    """Bind a qualified endpoint, retain every observation/satellite soft row."""
    if arm not in ("fitted-c", "zero-c") or not endpoint.get("converged"):
        raise ValueError("qualified matched arm endpoint required")
    vector, clock = (
        np.asarray(endpoint["vector"], float),
        np.asarray(endpoint["clock_coefficients"], float),
    )
    if arm == "zero-c" and (vector[6] != 0 or np.any(clock[-2:] != 0)):
        raise ValueError("zero-c endpoint must lock static c and both RF-time terms")
    if getattr(model, "fixed_rf_drift", False) and np.any(clock[-2:] != 0):
        raise ValueError("fixed RF drift endpoint must lock both RF-time terms")
    prediction, jacobian = frequency_design(model, vector, clock, predictor=predictor)
    value, _, _, terms = model.evaluate_joint(vector, clock)
    if not np.isclose(value, endpoint["objective"], atol=1e-6, rtol=0):
        raise ValueError("ordinary endpoint objective mismatch")
    responsibilities = np.asarray(terms.responsibilities, float)
    if (
        responsibilities.shape != prediction.shape
        or not np.isfinite(responsibilities).all()
        or np.any(responsibilities < 0)
        or np.any(responsibilities > 1)
        or np.any(responsibilities.sum(axis=1) > 1 + 1e-12)
    ):
        raise ValueError("invalid complete-data responsibilities")
    sigma = model.score.sigma_hz
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("positive finite Gaussian sigma required")
    locked = (
        {6, model.size + len(clock) - 2, model.size + len(clock) - 1} if arm == "zero-c" else set()
    )
    if getattr(model, "fixed_rf_drift", False):
        locked.update((model.size + len(clock) - 2, model.size + len(clock) - 1))
    nuisance = [i for i in range(2, jacobian.shape[2]) if i not in locked]
    prior = np.zeros((jacobian.shape[2],) * 2)
    prior[7, 7] = 1 / model.score.common_sigma_s**2
    prior[8 : model.size, 8 : model.size] = (
        model.basis.T @ model.basis / model.score.relative_sigma_s**2
    )
    prior[model.size :, model.size :] = model.precision
    parameter_scales = np.ones(jacobian.shape[2])
    if hasattr(model, "slope_slice"):
        parameter_scales[
            model.size + model.slope_slice.start : model.size + model.slope_slice.stop
        ] = 100
    # The model stores satellite slopes in Hz per100s; use physical Hz/s here.
    jacobian *= parameter_scales[None, None, :]
    prior *= parameter_scales[:, None] * parameter_scales[None, :]
    return dict(
        spatial=jacobian[:, :, :2].reshape(-1, 2),
        nuisance=jacobian[:, :, nuisance].reshape(-1, len(nuisance)),
        weights=(responsibilities / sigma**2).ravel(),
        full_jacobian=jacobian,
        prediction=prediction,
        nuisance_parameter_indices=nuisance,
        locked_parameter_indices=sorted(locked),
        prior_information_separate=prior,
        model_parameter_scales=parameter_scales,
        objective_delta=float(value - endpoint["objective"]),
        observations=prediction.shape[0],
        satellites=prediction.shape[1],
        scope="Complete-data conditional Gaussian frequency information; soft rows retained; "
        "data-only projection treats nuisance as free and omits actual bounds/prior restoration",
        units="Spatial Hz/km; receiver/satellite slopes Hz/s; timing seconds; "
        "smooth-clock and RF-time coordinates retain original model units",
    )
