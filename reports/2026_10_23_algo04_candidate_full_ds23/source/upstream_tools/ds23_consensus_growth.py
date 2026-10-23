"""RF-only shared-phase selection for complete unused curved fragments."""

import numpy as np


def choose_consensus(phases, rows, prior_cost, minimum_owners=2):
    """Maximize complete-curve support, with one phase for the entire offer.

    Each row has a fixed observation set and vector of unchanged gate outcomes.
    Compare costs only after the selected complete-row set is fixed, never
    marginal likelihoods computed from different numbers of observations.
    """
    phases=np.asarray(phases,float);prior=np.asarray(prior_cost,float)
    if phases.ndim!=1 or not len(phases) or prior.shape!=phases.shape or not np.isfinite(phases).all():
        raise ValueError('finite phase grid and matching prior costs required')
    options=[]
    for k,phase in enumerate(phases):
        selected=[r for r in rows if bool(r['passing'][k])]
        owners={(r['receiver'],r['channel']) for r in selected}
        if len(owners)<minimum_owners:continue
        options.append(dict(phase_index=k,phase_s=float(phase),
            row_indices=tuple(sorted(r['row_index'] for r in selected)),
            added_points=sum(r['points'] for r in selected),owners=len(owners)))
    if not options:return None
    # Select the mask by count and stable row order. Costs have no role in
    # comparisons between different masks (even when point counts coincide).
    chosen=min(options,key=lambda o:(-o['added_points'],o['row_indices']))['row_indices']
    identical=[o for o in options if o['row_indices']==chosen]
    def score(option):
        k=option['phase_index']
        return float(prior[k]+sum(r['power']*r['cost'][k] for r in rows if r['row_index'] in chosen))
    result=min(identical,key=lambda o:(score(o),abs(o['phase_s']),o['phase_s']))
    k=result['phase_index']
    return dict(result,proposal_score=score(result),
        aliases={r['row_index']:int(r['aliases'][k]) for r in rows if r['row_index'] in chosen},
        component_names=[r['component'] for r in rows if r['row_index'] in chosen])


def eligible_curve(track, active, occupied):
    """No original point is stolen and no partial accepted track is expanded."""
    times=np.asarray(track['times'])
    return bool(not np.asarray(active,bool).any() and len(times)>=12 and np.ptp(times)>=10 and
                not occupied.intersection(track['observation_ids']))
