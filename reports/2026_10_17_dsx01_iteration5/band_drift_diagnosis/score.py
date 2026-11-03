"""All-candidate training-mixture score for new RX high-band affine terms."""
import numpy as np

SCALES = np.array([100., 1., 100., 1.])  # Hz, Hz/s, Hz, Hz/s
NAMES = ['rx0_high_constant_hz', 'rx0_high_drift_hz_s',
    'rx1_high_constant_hz', 'rx1_high_drift_hz_s']


def design(times_s, receiver, channel):
    times = np.asarray(times_s, float)
    middle = .5*(times.min()+times.max())
    columns = []
    for rx in [0, 1]:
        high = ((np.asarray(receiver) == rx) & (np.asarray(channel) >= 5)).astype(float)
        columns.extend([high, high*(times-middle)])
    return np.column_stack(columns), float(middle)


def mixture_score(responsibility, residual_hz, sigma_hz, new_design):
    """Exact score and observed curvature at zero additive prediction shift.

    The positive complete-Gaussian information freezes responsibilities. It is
    distinct from observed mixture curvature, which can be indefinite.
    """
    p, residual = np.asarray(responsibility), np.asarray(residual_hz)
    sigma = np.broadcast_to(np.asarray(sigma_hz), (len(p),))
    basis = np.asarray(new_design)
    if p.shape != residual.shape or basis.shape[0] != len(p):
        raise ValueError('Aligned all-candidate rows and design required')
    mass = p.sum(axis=1)
    first = np.sum(p*residual, axis=1)/sigma**2
    row_gradient = -first
    info_weight = mass/sigma**2
    row_curvature = info_weight-np.sum(p*residual**2, axis=1)/sigma**4+first**2
    return dict(gradient=basis.T@row_gradient,
        observed_hessian=basis.T@(row_curvature[:, None]*basis),
        complete_gaussian_information=basis.T@(info_weight[:, None]*basis),
        row_gradient=row_gradient, row_curvature=row_curvature,
        signal_mass=mass, gaussian_information_weight=info_weight)


def masked_score(measured, prediction, visibility, sigma, q, score, times, receiver, channel, mask):
    """Exclude all held CFO before density evaluation or score calculation."""
    from leo.analysis.shared_scan_model import density
    mask = np.asarray(mask, bool)
    basis, midpoint = design(np.asarray(times)[mask], np.asarray(receiver)[mask], np.asarray(channel)[mask])
    sigma = np.broadcast_to(np.asarray(sigma), (len(mask),))[mask]
    terms, _ = density(np.asarray(measured)[mask], np.asarray(prediction)[mask],
        np.asarray(visibility)[mask], sigma, q, score)
    return terms, basis, midpoint, mixture_score(terms.responsibilities, terms.residual_hz, sigma, basis)


def profile_frequency_score(responsibilities, residual, sigma, new_design, old_jacobian):
    """Responsibility-weighted Gaussian tangent projection, no state fit.

    Uses ALL candidate columns, including competing/clutter-weighted candidates.
    Omits q/visibility derivatives and priors; not a full efficient-score test.
    """
    p = np.asarray(responsibilities)
    sigma = np.broadcast_to(np.asarray(sigma), (len(p),))
    weights = p/sigma[:, None]**2
    root = np.sqrt(weights.ravel())
    old = np.asarray(old_jacobian).reshape(len(root), -1)*root[:, None]
    new = np.repeat(np.asarray(new_design), p.shape[1], axis=0)*root[:, None]
    norm = np.linalg.norm(old, axis=0)
    active = norm > 1e-14
    old = old[:, active]/norm[active]
    coefficients, _, rank, singular = np.linalg.lstsq(old, new, rcond=1e-9)
    remaining = new-old@coefficients
    pair_gradient = (-p*np.asarray(residual)/sigma[:, None]**2).ravel()
    whitened_gradient = np.divide(pair_gradient, root, out=np.zeros_like(root), where=root > 0)
    return dict(gradient=remaining.T@whitened_gradient,
        complete_gaussian_information=remaining.T@remaining,
        old_frequency_rank=int(rank), old_frequency_columns=int(active.sum()),
        largest_singular=float(singular.max(initial=0)),
        smallest_retained_singular=float(singular[rank-1]) if rank else None,
        qualification='Local frequency tangent projection only; responsibility-frozen positive information, all candidates, no q/visibility/priors, no parameter refit or p-value.')
