"""Coordinate ranking uses only available scans and fixed acquisition scores."""
import numpy as np


def eligible_indices(candidates, target, target_only=False):
    available = set(target['scans'])
    return [i for i, c in enumerate(candidates)
            if c['block'] == target['block_id'] and set(c['scans']).issubset(available)
            and (not target_only or c['unit'] == target['unit_id'])]


def choose(scores, eligible, baseline, tolerance=1e-6):
    scores = np.asarray(scores, dtype=float)
    if not eligible or baseline not in eligible or not np.isfinite(scores[eligible]).all():
        raise ValueError('Missing baseline, empty pool or invalid scores')
    maximum = float(np.max(scores[eligible]))
    tied = [i for i in eligible if scores[i] >= maximum-tolerance]
    return baseline if baseline in tied else tied[0]


def rank_targets(candidates, scans, score_matrix, targets):
    matrix = np.asarray(score_matrix, dtype=float)
    if matrix.shape != (len(scans), len(candidates)):
        raise ValueError('Wrong score matrix binding')
    rows = []
    for target in targets:
        baseline_matches = [i for i, c in enumerate(candidates)
                            if c['unit'] == target['unit_id'] and c['policy'] == 'first']
        if len(baseline_matches) != 1:
            raise ValueError('Exactly one first-fit baseline is required')
        baseline = baseline_matches[0]
        values = matrix[[scans.index(s) for s in target['scans']]].sum(axis=0)
        same = eligible_indices(candidates, target, True)
        contained = eligible_indices(candidates, target)
        rows.append(dict(unit=target['unit_id'], size=target['size'], baseline=baseline,
            target_only=choose(values, same, baseline), contained=choose(values, contained, baseline),
            target_candidates=same, contained_candidates=contained, scores=values.tolist()))
    return rows
