"""Score geography only after candidate-set mode rankings have been sealed."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    scores_path = HERE/'checking-candidates-v1.json'
    assert digest(scores_path) == scores_path.with_suffix('.sha256').read_text().strip()
    scores = json.loads(scores_path.read_text())
    verify_sources(scores['sources'])
    audit_path = HERE/'source-split-fit-v1-audit.json'
    assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
    audit = json.loads(audit_path.read_text())
    assert audit['accepted'] == audit['planned'] == 3
    rows = []
    for score in scores['rows']:
        unit = score['unit']
        path = HERE/'source-split-fit-v1'/(unit+'.json')
        assert digest(path) == score['fit_sha256']
        receipt = json.loads(path.read_text())
        verify_sources(receipt['source_sha256'])
        verify_sources(receipt['inputs'])
        status = next(r for r in audit['rows'] if r['unit'] == unit)
        assert status['accepted'] and status['receipt_sha256'] == digest(path)
        winner = max(score['modes'], key=lambda m: m['total_log_ratio'])
        assert winner['seed_index'] == score['checking_winner_seed']
        assert receipt['best']['seed_index'] == score['training_winner_seed']
        modes = []
        for m in score['modes']:
            fit = next(f for f in receipt['fits'] if f['seed_index'] == m['seed_index'])
            assert fit['converged'] and fit['objectives'][-1] == m['training_objective']
            assert abs(sum(m['per_group_log_ratios'])-m['total_log_ratio']) < 1e-8
            modes.append(dict(seed=m['seed_index'], point=fit['mean'][:2],
                              checking_log_ratio=m['total_log_ratio']))
        rows.append(dict(unit=unit, training_seed=score['training_winner_seed'],
                         checking_seed=score['checking_winner_seed'], modes=modes,
                         training_fit_runtime_s=status['runtime_s']))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('checking_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        for m in row['modes']:
            m['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*m['point']), reference.REFERENCE)
        row['training_error_m'] = next(m['error_m'] for m in row['modes']
                                       if m['seed'] == row['training_seed'])
        row['checking_error_m'] = next(m['error_m'] for m in row['modes']
                                       if m['seed'] == row['checking_seed'])
    result = dict(planned=3, accepted=3, rows=rows,
                  training_median_error_m=float(np.median([r['training_error_m'] for r in rows])),
                  checking_median_error_m=float(np.median([r['checking_error_m'] for r in rows])),
                  scoring_all_three_seconds=scores['seconds'],
                  source_scores_sha256=digest(scores_path), evaluator_sha256=digest(__file__),
                  qualification='Three exposed development recordings, checking split before '
                  'trajectory construction. Checking score rankings sealed before geographic '
                  'evaluation. No independent-recording validation, posterior calibration or '
                  'full64benchmark claim. Scoring is a separately timed diagnostic, not yet an '
                  'integrated cold90s pipeline. Reference remains operator-provided, unsurveyed.')
    output = HERE/'checking-candidates-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
