"""Normalized conditional mark density for a supplied partition of observations.

Research component only: no track extraction, geometry, fitting, storage or
production likelihood imports. The group identity is shared; each point still
has a signal-versus-uniform alternative. All derivatives are of total NLL.
"""
from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp


ALIAS_HZ = 1. / 4.4e-6
ETA = .10
EPSILON = .12


@dataclass(frozen=True)
class CoherentTerms:
    nll: float
    group_nll: np.ndarray
    group_labels: tuple
    group_index: np.ndarray
    # Column 0 is the all-clutter component, columns 1..K catalogue identities.
    group_posterior: np.ndarray
    signal_responsibility: np.ndarray
    clutter_probability: np.ndarray
    residual_hz: np.ndarray
    prediction_gradient: np.ndarray
    visibility_gradient: np.ndarray
    q_gradient: np.ndarray

    @property
    def responsibilities(self):
        """Effective signal probability, not marginal group identity weight."""
        return self.signal_responsibility


def _partition(labels, count):
    labels = np.asarray(labels)
    if labels.ndim != 1 or len(labels) != count:
        raise ValueError('One group label is required for every observation')
    unique, lookup, index = [], {}, np.empty(count, dtype=np.intp)
    for row, value in enumerate(labels.tolist()):
        try:
            valid = value is not None and value == value
            if isinstance(value, (float, complex)):
                valid = valid and np.isfinite(value)
            if not valid:
                raise ValueError('Group labels must be finite nonmissing hashable scalars')
            if value not in lookup:
                lookup[value] = len(unique)
                unique.append(value)
            index[row] = lookup[value]
        except TypeError as exc:
            raise ValueError('Group labels must be hashable scalars') from exc
    return tuple(unique), index


def _sigma_array(sigma, shape):
    value = np.asarray(sigma, dtype=float)
    if value.ndim == 1:
        if value.shape != (shape[0],):
            raise ValueError('A sigma vector must have one value per observation')
        value = value[:, None]
    try:
        value = np.broadcast_to(value, shape)
    except ValueError as exc:
        raise ValueError('sigma_hz must be scalar, [N], or broadcastable to [N,K]') from exc
    if np.any(~np.isfinite(value)) or np.any(value <= 0):
        raise ValueError('sigma_hz must be finite and strictly positive')
    return value


def _wrapped_log_normal(residual, sigma, alias):
    """Image sum and exact derivative of that sum, with <1e-16 tail cutoff.

    The circular residual lies in [-alias/2,alias/2). Retaining images through
    the largest sigma's 8.6-sigma tail also handles widths comparable to alias.
    This is a normalized wrapped normal to floating-point tail precision, not
    a nearest-image Gaussian with a discontinuous derivative at the seam.
    """
    radius = max(1, int(np.ceil(.5 + np.max(sigma) / alias * np.sqrt(-2*np.log(1e-16)))))
    images = residual[..., None] + alias*np.arange(-radius, radius+1)
    scaled = images / sigma[..., None]
    logs = -.5*scaled**2 - np.log(sigma[..., None]) - .5*np.log(2*np.pi)
    log_phi = logsumexp(logs, axis=2)
    weights = np.exp(logs-log_phi[..., None])
    dlog_phi_dprediction = np.sum(weights*scaled, axis=2) / sigma
    return log_phi, dlog_phi_dprediction


def coherent_terms(measured_hz, prediction_hz, visibility, detection_q, group_labels,
                   *, sigma_hz=125., alias_hz=ALIAS_HZ, eta=ETA, epsilon=EPSILON):
    """Evaluate the normalized group model and exact first derivatives.

    Inputs y[N], prediction[N,K], visibility[N,K] in [0,1], positive q[K]
    and labels[N] describe one exhaustive disjoint row partition. Group order
    is first label occurrence. q need not sum to one; its scale is a gauge.

    U=1/alias, a=1-epsilon, h_ns=a*w_ns*phi_ns+(1-a*w_ns)*U,
    f_g=eta*U**n_g+(1-eta)*sum_s(q_s/sum(q))*prod_n_in_g(h_ns).

    Gradients are d(total NLL)/d(prediction Hz), d/d(visibility), and d/d(q)
    BEFORE q normalization. No priors are included. There is no per-row NLL:
    group_nll is the additive independent likelihood unit. Singleton groups
    give this model's own normalized point counterpart, not the deployed
    shared-scan density. eta and epsilon must be strictly between zero and one
    to preserve the all-clutter and per-point positive density floors.
    """
    measured = np.asarray(measured_hz, dtype=float)
    prediction = np.asarray(prediction_hz, dtype=float)
    visible = np.asarray(visibility, dtype=float)
    q = np.asarray(detection_q, dtype=float)
    if prediction.ndim != 2 or prediction.shape[0] == 0 or prediction.shape[1] == 0:
        raise ValueError('prediction_hz must be a nonempty [N,K] matrix')
    n, k = prediction.shape
    if measured.shape != (n,) or visible.shape != (n, k) or q.shape != (k,):
        raise ValueError('Expected measured[N], prediction/visibility[N,K] and q[K]')
    if any(np.any(~np.isfinite(x)) for x in (measured, prediction, visible, q)):
        raise ValueError('Observations, predictions, visibility and q must be finite')
    if np.any(visible < 0) or np.any(visible > 1):
        raise ValueError('visibility must lie in [0,1]')
    if np.any(q <= 0) or not np.isfinite(q.sum()):
        raise ValueError('detection_q must be strictly positive with finite sum')
    if not np.isfinite(alias_hz) or alias_hz <= 0:
        raise ValueError('alias_hz must be finite and positive')
    if not np.isfinite(eta) or not 0 < eta < 1 or not np.isfinite(epsilon) or not 0 < epsilon < 1:
        raise ValueError('eta and epsilon must be strictly between zero and one')
    sigma = _sigma_array(sigma_hz, (n, k))
    labels, index = _partition(group_labels, n)
    g = len(labels)
    residual = (measured[:, None]-prediction+alias_hz/2) % alias_hz-alias_hz/2
    log_phi, phi_gradient = _wrapped_log_normal(residual, sigma, alias_hz)
    a = 1-epsilon
    aw = a*visible
    log_signal = np.full((n, k), -np.inf)
    np.log(aw, out=log_signal, where=aw > 0)
    log_signal += log_phi
    log_uniform = -np.log(alias_hz)
    log_h = np.logaddexp(log_signal, np.log1p(-aw)+log_uniform)
    products = np.zeros((g, k))
    np.add.at(products, index, log_h)
    sizes = np.bincount(index, minlength=g)
    log_q_probability = np.log(q)-np.log(q.sum())
    log_components = np.column_stack((np.log(eta)+sizes*log_uniform,
        np.log1p(-eta)+log_q_probability+products))
    log_density = logsumexp(log_components, axis=1)
    posterior = np.exp(log_components-log_density[:, None])
    group_nll = -log_density
    gamma = posterior[index, 1:]
    within_signal = np.exp(log_signal-log_h)
    responsibilities = gamma*within_signal
    # Positive point clutter includes both the all-clutter group and candidate
    # branches choosing uniform for that point; it is not just gamma_g0.
    clutter = posterior[index, 0] + np.sum(gamma*(-np.expm1(log_signal-log_h)), axis=1)
    prediction_gradient = -responsibilities*phi_gradient
    visibility_gradient = -gamma*a*(np.exp(log_phi-log_h)-np.exp(log_uniform-log_h))
    # dNLL/dq_j = (sum_s gamma_gs)/Q - gamma_gj/q_j, summed over groups.
    # q is interior-positive by contract, so no 0/0 boundary approximation.
    q_gradient = np.sum(posterior[:, 1:].sum(axis=1)[:, None]/q.sum()-posterior[:, 1:]/q, axis=0)
    return CoherentTerms(float(group_nll.sum()), group_nll, labels, index, posterior,
        responsibilities, clutter, residual, prediction_gradient, visibility_gradient, q_gradient)
