"""Geometry-dependent Gaussian copula with unchanged Student phase marginals.

R is the latent normal correlation, not the physical Student covariance. This
removes the global Gamma coupling of the elliptical-Student control. A runtime
implementation would need this nonlinear prior, not the old linear transform.
"""

import numpy as np
from scipy.special import ndtri, stdtr

from ds23_geometry_phase_covariance import (
    KINDS, RHOS, fit_controls, independent_cost, make_events,
    old_publication_total, quadratic_logdet,
)


def normal_scores(z, nu):
    z = np.asarray(z, float)
    if not np.isfinite(z).all():
        raise ValueError('finite standardized residuals required')
    if nu is None:
        return z.copy()
    if not np.isfinite(nu) or nu <= 2:
        raise ValueError('Student degrees of freedom must exceed two')
    # Evaluate the small tail directly; 1-cdf would lose precision for large z.
    tail = stdtr(nu, -abs(z)*np.sqrt(nu/(nu-2)))
    if np.any(tail <= 0):
        raise ValueError('Student tail probability underflow')
    score = ndtri(tail)
    return np.where(z < 0, score, -score)


def joint_cost(z, features, rho, nu):
    scores = normal_scores(z, nu)
    quadratic, logdet = quadratic_logdet(scores, features, rho)
    return float(independent_cost(z, nu)+quadratic-scores@scores+logdet)


def total(events, kind, rho, nu):
    return float(sum(joint_cost(e['z'], np.ones((len(e['z']), 1)) if kind == 'global'
                                else e[kind], rho, nu) for e in events))


def fit(events, nu, kinds=KINDS):
    count = sum(len(e['z']) for e in events)
    penalty = np.log(max(count, 1))+2*np.log(len(KINDS))
    choices = [dict(kind=kind, rho=rho, cost=total(events, kind, rho, nu))
               for kind in kinds for rho in RHOS]
    for c in choices:
        c['criterion'] = c['cost']+(penalty if c['rho'] else 0.)
    return dict(min(choices, key=lambda c: c['criterion']), choices=choices)


def evaluate(events, nu, selection, publication_rho, global_rho):
    count = sum(len(e['z']) for e in events)
    value = total(events, selection['kind'], selection['rho'], nu)
    controls = dict(independent=sum(independent_cost(e['z'], nu) for e in events),
                    old_publication=old_publication_total(events, publication_rho, nu),
                    global_copula=total(events, 'global', global_rho, nu))
    return dict(count=count, events=len(events), model_cost=value, control_costs=controls,
                gains={name: float(cost-value) for name, cost in controls.items()},
                penalty=float(np.log(max(count, 1))+2*np.log(len(KINDS))))


def qualify(rows, boundary, earlier, full_model, full_location):
    if 'prefix_model' not in earlier:
        return dict(qualified=False, reason=earlier['reason'], event_counts=earlier.get('event_counts'))
    model, location = earlier['prefix_model'], earlier['prefix_location']
    # These same prefix marginals were fitted without later events or NORAD%5=0.
    training = [r for r in rows if r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0]
    future = [r for r in rows if r['validation_time_ns'] > boundary]
    disjoint = [r for r in future if r['norad'] % 5 == 0]
    events, later, held = [make_events(part, model, location) for part in (training, future, disjoint)]
    fitted = fit(events, model['nu'])
    publication = fit_controls(events, model['nu'])['publication']
    global_model = fit(events, model['nu'], ('global',))
    checks = {name: evaluate(part, model['nu'], fitted, publication['rho'], global_model['rho'])
              for name, part in [('training', events), ('chronological', later), ('satellite_disjoint', held)]}
    qualified = bool(fitted['rho'] and all(v['count'] >= 30 and
                     min(v['gains'].values()) > v['penalty'] for v in checks.values()))
    complete = None
    if qualified:
        complete = fit(make_events(rows, full_model, full_location), full_model['nu'], (fitted['kind'],))
        qualified = bool(complete['rho'])
    return dict(qualified=qualified, prefix_selection=fitted, global_control=global_model,
                publication_control=publication, validation=checks, all_past=complete,
                selected_kind=complete['kind'] if qualified else None,
                selected_rho=complete['rho'] if qualified else 0.,
                prefix_marginals_bound_to_earlier_training_only_result=True,
                Student_marginals_exact_and_no_shared_Gamma=True,
                R_is_latent_normal_correlation_not_physical_Student_covariance=True,
                nonlinear_runtime_prior_required_if_qualified=True)
