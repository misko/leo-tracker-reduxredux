"""Pure membership, segmentation and satellite-screen helpers for DBG01."""

import numpy as np
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def ownership(rows):
    """Compatible rows own only their explicit physical measurement IDs."""
    ids = set()
    for row in rows:
        if not row['compatible']:
            continue
        new = set(row['observation_ids'])
        if len(new) != len(row['observation_ids']) or ids & new:
            raise ValueError('duplicate physical association ownership')
        ids.update(new)
    return ids


def remaining_indices(track, accepted):
    return np.array([i for i, oid in enumerate(track['observation_ids']) if oid not in accepted], int)


def orphan_blocks(observations, graph_ids, accepted, width_s=20):
    """Partition all outside-graph evidence; these blocks are NOT found tracks."""
    groups = {}
    for o in observations:
        oid = o['observation_id']
        if oid in graph_ids or oid in accepted:
            continue
        key = (o['receiver'], o['channel'], o['actual_rf_hz'], int(o['time_s'] // width_s))
        groups.setdefault(key, []).append(o)
    return [dict(key=key, observations=sorted(values, key=lambda o: (o['time_s'], o['observation_id'])))
            for key, values in sorted(groups.items())]


def candidate_gates(terms, elevation, times):
    noise = batch_noise_screen(terms['innovations'], times)
    passed = (terms['rms'] <= 450) & (abs(terms['bias']) <= 3000)
    passed &= (np.min(elevation, axis=1) >= 0) & noise['noise_screen_pass']
    return passed, noise


def validate_post_version(row, end_ns, hours=48):
    """Never hide a missing following element behind a causal fallback label."""
    high = end_ns + int(hours * 3600e9)
    return (end_ns < row['element_epoch_utc_ns'] <= high and
            end_ns < row['collected_utc_ns'] <= high)
