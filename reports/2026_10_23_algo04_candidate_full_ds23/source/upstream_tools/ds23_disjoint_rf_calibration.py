"""Remove all graph evidence from probes reused for independent RF calibration."""

import numpy as np


def exclude_probes(scan, base, keep, entries, probes):
    mask = np.asarray(keep, bool).copy()
    probe_ids = set()
    for track in scan.tracks:
        times = np.asarray(track['times'])
        selected = np.zeros(len(times), bool)
        for probe in probes:
            if track['channel'] == probe['channel'] and abs(track['rf_hz']-probe['rf_hz']) < 1.:
                selected |= abs(times-probe['time_s']) <= 1e-6
        probe_ids.update(np.asarray(track['observation_ids'])[selected].tolist())
    removed_curved = []
    for index, sl in zip(base.members, base.slices, strict=True):
        ids = scan.tracks[index]['observation_ids']
        selected = np.array([oid in probe_ids for oid in ids])
        removed_curved.extend(np.asarray(ids)[mask[sl] & selected].tolist())
        mask[sl] &= ~selected
    retained_entries = []
    removed_predictive = []
    for entry in entries:
        remaining = [oid for oid in entry['observation_ids'] if oid not in probe_ids]
        removed_predictive.extend(oid for oid in entry['observation_ids'] if oid in probe_ids)
        if len(remaining) >= 4:
            retained_entries.append(dict(entry, observation_ids=remaining, points=len(remaining)))
        else:
            removed_predictive.extend(remaining)
    retained = set()
    for index, sl in zip(base.members, base.slices, strict=True):
        retained.update(np.asarray(scan.tracks[index]['observation_ids'])[mask[sl]].tolist())
    retained.update(oid for entry in retained_entries for oid in entry['observation_ids'])
    if retained.intersection(probe_ids):
        raise ValueError('RF calibration shares IQ with retained GLRT evidence')
    return mask, retained_entries, dict(excluded_probe_graph_ids=sorted(probe_ids),
        removed_curved_ids=removed_curved, removed_predictive_ids=sorted(set(removed_predictive)),
        calibration_probe_ids_disjoint_from_all_retained_GLRT=True)
