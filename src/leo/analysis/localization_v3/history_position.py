"""Family-weighted phase-history likelihood, preserving original nuisance arithmetic."""

import numpy as np

from leo.analysis.localization_v3.conservative_recovery import retained_metrics
from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.orbit_modes import build_modes
from leo.analysis.localization_v3.position import NormalPosition, fit
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.analysis.research.orbital_support import (
    include_active_orbital_uncertainty,
    include_predictive_orbital_uncertainty,
    restrict_to_active_orbital_support,
)


def problem(scan, node, arm, keep, reference=None):
    p = NormalPosition(
        scan, node, scan.radio_sigma_hz, arm == "fitted_c", keep=keep, reference=reference
    )
    cache = getattr(scan, "diagnostic_phase_width_cache", {})
    key = tuple(p.labels)
    if key not in cache:
        cache[key] = phase_widths(scan, p.labels)[0]
    scan.diagnostic_phase_width_cache = cache
    p.phase_sigma = cache[key].copy()
    return p


def scale_posterior(bound, scales):
    """Return means/precisions in the original design coordinates, including zero modes."""
    s = np.asarray(scales)
    bound["coefficient"] *= s
    nonzero = s != 0
    bound["coefficient_prior_precision"][nonzero] /= s[nonzero] ** 2
    return bound


def forecast_phase_mean(receipts, shrinkage):
    if not 0 <= shrinkage <= 1:
        raise ValueError("fixed shrinkage must lie in [0,1]")
    means = []
    for r in receipts:
        delta, gap = r["old_new_alignment_s"], r["previous_epoch_gap_s"]
        value = (
            0.0
            if delta is None or gap is None or gap < 1
            else -shrinkage * np.clip((r["age_s"] + 150) / gap, 0, 2) * delta
        )
        means.append(float(np.clip(value, -min(15, 3 * r["sigma_s"]), min(15, 3 * r["sigma_s"]))))
    return np.asarray(means)


def make_problem(scan, node, keep, arm, reference, weights, means, multiplier, nu, *,
                 support_policy='nominal', extra_orbital_families=(),
                 predictive_orbital_families=()):
    if support_policy not in ('nominal', 'active', 'active_uncertainty'):
        raise ValueError('unknown physical orbital support policy')
    p = problem(scan, node, arm, keep, reference)
    if support_policy == 'active':
        restrict_to_active_orbital_support(p)
    elif support_policy == 'active_uncertainty':
        include_active_orbital_uncertainty(p,
            lambda supported: build_modes(scan, p.labels, supported, 'physical'))
    if extra_orbital_families:
        include_active_orbital_uncertainty(p,
            lambda supported: build_modes(scan, p.labels, supported, 'physical'),
            families=extra_orbital_families)
    if predictive_orbital_families:
        include_predictive_orbital_uncertainty(p,
            lambda supported: build_modes(scan, p.labels, supported, 'physical'),
            predictive_orbital_families)
    p.phase_sigma *= multiplier
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    width = begin + len(p.labels) + 3 * len(p.supported) + len(p.members)
    mean = np.zeros(width)
    mean[begin : begin + len(p.labels)] = means / p.phase_sigma
    groups = np.full(width, -1, int)
    if nu is not None:
        groups[begin : begin + len(p.labels)] = np.arange(len(p.labels))

    def calculate(x):
        result = JointMarginal.calculate(p, x, geometry_only=True)
        features = result["features"]
        scale = np.ones(width)
        scale[-len(p.members) :] = 0.3
        raw = p.values - p.q * result["intercept"] - features @ mean
        present = np.unique(p.noise_groups[keep])
        bound = hierarchical_bound(
            raw[keep],
            (features * scale)[keep],
            p.point_noise[keep],
            p.noise_groups[keep],
            powers=weights[present],
            prior_groups=None if nu is None else groups,
            prior_nu=4 if nu is None else nu,
        )
        bound = scale_posterior(bound, scale)
        latent = bound["coefficient"].copy()
        bound["coefficient"] = latent + mean
        bound["latent_coefficient"] = latent
        precision = np.zeros(len(p.members))
        precision[present] = bound["noise_precision"]
        bound["noise_precision"] = precision
        bound["conditional_residual_hz"] = (
            p.values - p.q * result["intercept"] - features @ bound["coefficient"]
        )
        volume = float(2 * np.sum(weights[p.noise_groups[keep]] * np.log(p.point_noise[keep] / 40)))
        bound["residual"] = np.r_[bound["residual"], np.sqrt(volume)]
        result.update(bound)
        return result

    p.calculate = calculate
    return p


def refit(scan, node, keep, arm, weights, means, multiplier, nu, *, rounds=5, iterations=48):
    reference = np.zeros(len(means))
    anchor = np.zeros(2)
    history = []
    for epoch in range(rounds):
        p = make_problem(scan, node, keep, arm, reference, weights, means, multiplier, nu)
        result = fit(p, anchor, iterations=iterations)
        anchor = np.array(result["parameters"])
        phase = p.state(anchor)["phases"][p.labels]
        history.append(
            dict(epoch=epoch, fit=result, phase_change_s=float(max(abs(phase - reference))))
        )
        reference = np.clip(phase, -15, 15)
    c = p.calculate(anchor)
    residual = p.residual(anchor)
    return dict(
        endpoint_east_north_km=anchor,
        endpoint_latlon=scan.search_region.latlon(anchor),
        score=float(residual @ residual),
        negative_twice_elbo=c["negative_twice_elbo"],
        normalization_constant=c["normalization_constant"],
        RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][keep] ** 2))),
        active_points=int(keep.sum()),
        gates=retained_metrics(p, anchor),
        history=history,
        state=p.state(anchor),
        phase_reference=reference,
        phase_prior_mean_s=means,
        phase_prior_sigma_s=p.phase_sigma,
        phase_posterior_s=p.state(anchor)["phases"][p.labels],
        prior_penalty=float(
            np.sum(c["latent_coefficient"] ** 2 * c["coefficient_prior_precision"])
        ),
        prior_precision=c["coefficient_prior_precision"],
        noise_precision=c["noise_precision"],
        precision_iterations=c["precision_iterations"],
        final_precision_change=c["final_log_precision_change"],
    )
