"""Only same-target fitted objectives are comparable."""
import numpy as np
from window_candidate_policy import choose


def select(candidates, objectives, target):
    eligible = [i for i, c in enumerate(candidates)
                if c['unit'] == target['unit_id'] and c['block'] == target['block_id']]
    if any(candidates[i]['scans'] != target['scans'] or candidates[i]['size'] != target['size'] for i in eligible):
        raise ValueError('Same target identifier with inconsistent scan binding')
    baselines = [i for i in eligible if candidates[i]['policy'] == 'first']
    if len(baselines) != 1:
        raise ValueError('Exactly one first-fit baseline required')
    values = np.asarray(objectives, dtype=float)
    if values.shape != (len(candidates),): raise ValueError('Wrong objective vector')
    return dict(baseline=baselines[0], eligible=eligible,
                selected=choose(-values, eligible, baselines[0]))
