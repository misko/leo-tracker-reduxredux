"""Report-only affine-slope priors, in physical Hz/s and NLL units."""
import numpy as np


def penalty(slopes, spec):
    b = np.asarray(slopes, dtype=float)
    if spec['kind'] == 'none':
        return 0., np.zeros_like(b)
    scale = float(spec['scale'])
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('positive finite slope-prior scale required')
    if spec['kind'] == 'gaussian':
        return float(.5 * np.sum((b / scale) ** 2)), b / scale ** 2
    if spec['kind'] == 'smooth':
        onset = float(spec['onset'])
        if not np.isfinite(onset) or onset < 0:
            raise ValueError('nonnegative finite onset required')
        excess = np.maximum(np.abs(b) - onset, 0.)
        return float(.5 * np.sum((excess / scale) ** 2)), np.sign(b) * excess / scale ** 2
    raise ValueError('unknown slope prior')


class PenalizedObjective:
    """Preserve the likelihood terms; add the slope prior to value and gradient."""
    def __init__(self, base, spec):
        self.base, self.spec = base, dict(spec)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def evaluate(self, vector):
        value, gradient, terms = self.base.evaluate(vector)
        cost, derivative = penalty(np.asarray(vector)[[3, 5]], self.spec)
        if self.spec['kind'] == 'none':
            return value, gradient, terms
        gradient = gradient.copy()
        gradient[[3, 5]] += derivative
        return value + cost, gradient, terms


def annotate_region(region, spec):
    """Charge the retained calibration prior once; separate timing from slope cost.

The original engine's within-region continuation ordering is unaffected by this
constant. Region ranking includes the postfit prior because its affine terms
are retained in the frozen baseline. The preliminary prefit is not retained.
"""
    if region.get('slope_prior_annotation') is not None:
        assert region['slope_prior_annotation'] == spec
        return region
    frozen = 0.
    if 'calibration' in region:
        frozen, _ = penalty(np.asarray(region['calibration']['postfit']['vector'])[[3, 5]], spec)
    def annotate(row):
        cost, _ = penalty(np.asarray(row['vector'])[[3, 5]], spec)
        return dict(row, slope_penalty=cost, frozen_slope_penalty=frozen,
                    unpenalized_objective=row['objective'] - cost,
                    timing_penalty=row['timing_penalty'] - cost,
                    selection_score=row['selection_score'] + frozen)
    return dict(region, candidates=[annotate(r) for r in region['candidates']],
                runs=[annotate(r) for r in region['runs']], frozen_slope_penalty=frozen,
                slope_prior_annotation=dict(spec))
