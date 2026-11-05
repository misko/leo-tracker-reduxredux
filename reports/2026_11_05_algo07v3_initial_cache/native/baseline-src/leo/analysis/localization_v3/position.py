"""Production normal-prior position likelihood and phase-refreshed descent.

All scan, orbit, noise and search-region evidence is supplied explicitly. This
fits a supplied hypothesis; fresh hypothesis discovery and later recovery are
separate policies, still under construction.
"""
import numpy as np

from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton


class NormalPosition(JointMarginal):
    """Exact normal-prior path, without unrelated experimental model controls."""

    def __init__(self, scan, node, sigma, fitted_c, *, reference=None, keep=None,
                 point_noise=None):
        super().__init__(scan, node['seed'], fitted_c, variant='radio_noise', sigma=sigma,
                         reference=reference, aliases=node['aliases'])
        self.noise_groups = np.concatenate(
            [np.full(sl.stop - sl.start, k, dtype=int) for k, sl in enumerate(self.slices)])
        self.noise_metadata = scan.fixed_window_noise
        self.noise_sha256 = scan.fixed_window_noise_sha256
        if point_noise is None:
            by_oid = self.noise_metadata['per_observation_noise_sigma_hz']
            selected = self.noise_metadata['extra_parameter_BIC_gain'] > 0
            point_noise = [by_oid[oid] if selected else self.sigma
                           for i in self.members for oid in scan.tracks[i]['observation_ids']]
        self.point_noise = np.asarray(point_noise, float)
        if (self.point_noise.shape != self.flat_times.shape
                or not np.isfinite(self.point_noise).all() or np.any(self.point_noise < 40)):
            raise ValueError('one fixed finite radio noise scale >=40 Hz per observation required')
        self.power = np.ones(len(self.slices))
        self.point_power = self.power[self.noise_groups]
        self.diagonal_logvolume = float(
            2 * np.sum(self.point_power * np.log(self.point_noise / 40)))
        self.keep = (np.ones(len(self.values), dtype=bool) if keep is None
                     else np.asarray(keep, bool))
        if self.keep.shape != self.values.shape or not self.keep.any():
            raise ValueError('nonempty observation mask matching full design required')
        self.noise_volume = float(2 * np.log(self.point_noise[self.keep] / 40).sum())

    def calculate(self, x):
        # The hierarchical result replaces every Gaussian posterior field.
        result = JointMarginal.calculate(self, x, geometry_only=True)
        features = result['features']
        scales = np.ones(features.shape[1])
        raw = self.values - self.q * result['intercept']
        design, response, noise = features * scales, raw, self.point_noise
        bound = hierarchical_bound(response[self.keep], design[self.keep], noise[self.keep],
                                   self.noise_groups[self.keep])
        bound['coefficient'] *= scales
        bound['coefficient_prior_precision'] /= scales**2
        present = np.unique(self.noise_groups[self.keep])
        weights = np.zeros(len(self.members))
        weights[present] = bound['noise_precision']
        bound['noise_precision'] = weights
        bound['conditional_residual_hz'] = raw - features @ bound['coefficient']
        bound['residual'] = np.r_[bound['residual'], np.sqrt(self.noise_volume)]
        result.update(bound, features=features)
        return result

    def residual(self, x):
        result = self.calculate(x)
        return np.r_[result['residual'], np.maximum(0, -result['elevation'][self.keep]) / 2]

def fit(problem, start=(0.0, 0.0), iterations=48):
    result = bounded_gauss_newton(problem.residual, start, problem.lower, problem.upper,
                                 iterations=iterations)
    calculated = problem.calculate(result['parameters'])
    return dict(result, residual_rms_hz=float(np.sqrt(np.mean(
        calculated['conditional_residual_hz'][problem.keep] ** 2))),
        active_points=int(problem.keep.sum()),
        normalization_constant=calculated['normalization_constant'],
        negative_twice_elbo=calculated['negative_twice_elbo'])


def refreshed(scan, sigma, node, arm, *, rounds=5, iterations=48):
    if arm not in ('c0', 'fitted_c') or rounds < 1 or iterations < 1:
        raise ValueError('Declared calibration arm and positive iteration budgets required')
    labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
    reference, anchor, history = np.zeros(len(labels)), np.zeros(2), []
    for epoch in range(rounds):
        problem = NormalPosition(scan, node, sigma, arm == 'fitted_c', reference=reference)
        result = fit(problem, anchor, iterations=iterations)
        anchor = np.array(result['parameters'])
        phase = problem.state(anchor)['phases'][problem.labels]
        history.append(dict(epoch=epoch, fit=result, phase_reference=reference.copy(),
                            posterior_phase_s=phase,
                            max_reference_change_s=float(np.max(abs(phase - reference)))))
        reference = np.clip(phase, -15, 15)
    return problem, result, history
