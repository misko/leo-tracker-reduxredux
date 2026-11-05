"""Normal-prior likelihood used by the original fresh-discovery policy."""
import numpy as np

from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.position import NormalPosition


class DiscoveryPosition(NormalPosition):
    def __init__(self, scan, seed, fitted_c, *, variant='normal', sigma=150., aliases=None,
                 reference=None):
        if variant != 'normal':
            raise ValueError('Production discovery uses the normal prior')
        super().__init__(scan, dict(seed=seed, aliases=aliases), sigma, fitted_c,
                         reference=reference)

    def calculate(self, x):
        # The hierarchical result replaces every Gaussian posterior field.
        result = JointMarginal.calculate(self, x, geometry_only=True)
        features = result['features']
        stop = features.shape[1] - len(self.members)
        features = np.column_stack((features[:, :stop], np.empty((len(self.flat_times), 0)),
                                    features[:, stop:]))
        bound = hierarchical_bound(self.values - self.q * result['intercept'], features,
            self.point_noise, self.noise_groups, prior_groups=None, powers=self.power, prior_nu=4)
        bound['residual'] = np.r_[bound['residual'], np.sqrt(self.diagonal_logvolume)]
        bound['full_objective_offset'] = bound['normalization_constant'] - self.diagonal_logvolume
        result.update(bound, features=features)
        return result
