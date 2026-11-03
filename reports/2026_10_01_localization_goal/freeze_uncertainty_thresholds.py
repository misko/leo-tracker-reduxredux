"""Freeze development-derived rank cutoffs before held-out geographic evaluation."""
import json
from math import ceil
from pathlib import Path

from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    evaluation = HERE/'deletion-spread-v1-evaluation.json'
    result = json.loads(evaluation.read_text())
    predictions = HERE/'deletion-spread-v1-predictions.json'
    assert digest(predictions) == result['prediction_sha256']
    assert digest(predictions) == predictions.with_suffix('.sha256').read_text().strip()
    assert digest(HERE/'evaluate_deletion_spread.py') == result['evaluator_sha256']
    thresholds = {}
    for arm in ['curvature', 'deletion', 'sum']:
        rows = result['rows'][arm]
        assert len(rows) == 64 and all(r['valid'] for r in rows)
        scores = sorted(r['mahalanobis_squared'] for r in rows)
        levels = {}
        for p in [.5, .9, .95]:
            rank = ceil((len(scores)+1)*p)
            assert 1 <= rank <= len(scores)
            levels[str(p)] = dict(one_based_rank=rank, squared_distance_cutoff=scores[rank-1])
        thresholds[arm] = levels
    sources = [HERE/'prepare_deletion_spread.py', HERE/'evaluate_deletion_spread.py',
               Path(__file__), HERE/'local_curvature.py', HERE/'diagnose_group_influence.py',
               HERE.parents[1]/'src/leo/analysis/localization_deletion_spread.py',
               HERE.parents[1]/'src/leo/analysis/localization_influence.py',
               HERE.parents[1]/'src/leo/analysis/localization_uncertainty.py']
    output = dict(
        schema='development-uncertainty-thresholds/v1',
        evaluation_sha256=digest(evaluation), predictions_sha256=digest(predictions),
        source_sha256={str(p.resolve()): digest(p) for p in sources},
        heldout_prediction_freeze_sha256=digest(HERE/'heldout-baseline-v1-freeze.json'),
        calibration_units=[r['unit'] for r in result['rows']['sum']],
        thresholds=thresholds,
        prediction_rule='For each unchanged shape S and position mu, include positions x with '
                        '(x-mu)^T inverse(S)(x-mu) <= frozen cutoff for that arm and level.',
        rank_rule='k=ceil((n+1)*p), kth smallest squared Mahalanobis score; no interpolation.',
        source_reference='https://arxiv.org/html/2107.07511v6',
        qualification='Conformal-style rank rule only. DS9/10/11 are exposed development scans, '
        'temporally dependent and from one reference site; scoring-rule development used this panel. '
        'Exchangeability and independent calibration assumptions are not established. No formal '
        'coverage guarantee, no retrospective calibration-success claim, no arm selected here. '
        'All three candidate threshold sets frozen before DS12 reference admission; no point changes.',
        pending='Construct the same shapes on sealed DS12 predictions, then evaluate coverage only '
                'after an independently qualified DS12 geographic reference is available.')
    path = HERE/'uncertainty-thresholds-v1-freeze.json'
    with path.open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')
    print(json.dumps(dict(freeze_sha256=digest(path), thresholds=thresholds), indent=2))


if __name__ == '__main__':
    main()
