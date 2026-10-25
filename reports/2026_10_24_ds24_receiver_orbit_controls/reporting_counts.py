"""Read position-likelihood counts across existing research-result schemas.

Counts exclude post-fit-only associations. For auditable coverage, independently
verify the unique curved/predictive native-ID union as count_audit.py does.
"""

def likelihood_point_count(fit, *, legacy_predictive_points=0):
    active = fit['active_points']
    values = [fit[k] for k in ('predictive_points', 'additional_predictive_points')
              if k in fit and fit[k] is not None]
    if values and any(x != values[0] for x in values):
        raise ValueError('conflicting predictive count fields')
    predictive = values[0] if values else legacy_predictive_points
    for value in (active, predictive):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('nonnegative integer likelihood counts required')
    return active + predictive
