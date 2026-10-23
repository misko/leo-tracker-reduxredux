"""Research adapter: retain weak calibration measurements as predictions.

Original curve slots, identities, aliases and orbital coordinates are kept.
Predictive noise uses the existing unseen-Gamma variance, divided by the
original curve power. No original measurement gets greater nominal precision.
"""

import copy
import numpy as np

from ds23_predictive_subsets import realize_predictive_subsets


def predictive_roles(data, inventory):
    scan = copy.copy(data['scan'])
    keep = np.asarray(data['keep'], bool).copy()
    entries = copy.deepcopy(data['entries'])
    old_meta = scan.fixed_window_noise
    use_native = old_meta['extra_parameter_BIC_gain'] > 0
    sigma = {o['observation_id']: float(old_meta['per_observation_noise_sigma_hz'][o['observation_id']]
             if use_native else scan.radio_sigma_hz) for o in data['observations']}
    receipts = []
    for row in inventory['rows']:
        if row['would_retain_calibration']:
            continue
        k = row['row']
        source = data['base'].rows[k]
        index = data['base'].members[k]
        sl = data['base'].slices[k]
        track = scan.tracks[index]
        ids = np.asarray(track['observation_ids'])[keep[sl]].tolist()
        if ids != row['observation_ids'] or source['component'] != row['component']:
            raise ValueError('RF inventory must match original active calibration rows')
        power = float(data['powers'][k])
        if not 0 < power <= 1:
            raise ValueError('original curve power must be in (0,1]')
        if any(set(ids) & set(e['observation_ids']) for e in entries):
            raise ValueError('a measurement cannot be both existing and demoted prediction')
        entries.append(dict(component=source['component'], track_index=index,
            candidate_index=source['candidate_index'], norad=source['candidate_norad'],
            alias=int(data['node']['aliases'][k]), observation_ids=ids, points=len(ids)))
        for observation_id in ids:
            sigma[observation_id] /= np.sqrt(power)
        keep[sl] = False
        receipts.append(dict(component=source['component'], points=len(ids),
            observation_ids=ids, original_power=power, predictive_variance_multiplier=2/power))
    if not keep.any():
        raise ValueError('at least one distributed curved calibration source required')
    if receipts:
        # This is an in-memory numerical adapter, not a new BIC estimate or
        # persisted noise contract. Every unchanged ID keeps its exact old SD.
        scan.fixed_window_noise = dict(old_meta, per_observation_noise_sigma_hz=sigma,
            extra_parameter_BIC_gain=1., research_explicit_noise_override=True,
            research_original_extra_parameter_BIC_gain=old_meta['extra_parameter_BIC_gain'])
    scan, entries, subsets = realize_predictive_subsets(scan, entries)
    result = dict(data, scan=scan, keep=keep, entries=entries)
    return result, dict(demoted=receipts, predictive_subsets=subsets,
        original_curve_slots_labels_aliases_priors_and_all_IDs_retained=True,
        no_fitted_noise_or_position_based_role_choice=True)
