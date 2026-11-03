"""Score geography only after candidate-set mode rankings have been sealed."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    scores_path = HERE/'checking-expansion-v1.json'
    assert digest(scores_path) == scores_path.with_suffix('.sha256').read_text().strip()
    scores = json.loads(scores_path.read_text())
    verify_sources(scores['sources'])
    audit_path = HERE/'split-expansion-fit-v1-audit.json'
    assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
    audit = json.loads(audit_path.read_text())
    assert audit['planned'] == 12
    rows = []
    for score in scores['rows']:
        unit = score['unit']
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        parent_seal = json.loads(parent_path.with_suffix('.seal.json').read_text())
        assert digest(parent_path) == parent_seal['prediction_sha256']
        parent = json.loads(parent_path.read_text())
        if not score['accepted']:
            rows.append(dict(unit=unit, accepted=False, failures=score['failures'],
                             all_data_baseline_point=parent['best']['mean'][:2]))
            continue
        path = HERE/'split-expansion-fit-v1'/(unit+'.json')
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
        source_path = HERE/'source-split-expansion-v1'/(unit+'.json')
        assert digest(source_path) == score['source_sha256']
        source = json.loads(source_path.read_text())
        rows.append(dict(unit=unit, accepted=True, training_seed=score['training_winner_seed'],
                         checking_seed=score['checking_winner_seed'], modes=modes,
                         all_data_baseline_point=parent['best']['mean'][:2],
                         scoring_seconds=score['scoring_seconds'],
                         preprocessing_seconds=source['seconds'],
                         training_fit_runtime_s=status['runtime_s']))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('checking_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        row['all_data_baseline_error_m'] = reference.distance_m(
            reference.latlon_from_enu(*row['all_data_baseline_point']), reference.REFERENCE)
        if not row['accepted']:
            row['training_error_m'] = row['checking_error_m'] = None
            continue
        for m in row['modes']:
            m['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*m['point']), reference.REFERENCE)
        row['training_error_m'] = next(m['error_m'] for m in row['modes']
                                       if m['seed'] == row['training_seed'])
        row['checking_error_m'] = next(m['error_m'] for m in row['modes']
                                       if m['seed'] == row['checking_seed'])
        row['saved_mode_oracle_error_m'] = min(m['error_m'] for m in row['modes'])
    valid = [r for r in rows if r['accepted']]
    summary = {}
    for name in ['training', 'checking']:
        values = [r[name+'_error_m'] for r in valid]
        summary[name+'_median_error_m'] = float(np.median(values)) if values else None
        summary[name+'_p90_error_m'] = float(np.percentile(values, 90)) if values else None
    summary['all_data_baseline_median_error_m'] = float(np.median(
        [r['all_data_baseline_error_m'] for r in rows]))
    summary['all_data_baseline_p90_error_m'] = float(np.percentile(
        [r['all_data_baseline_error_m'] for r in rows], 90))
    summary['checking_within_1000m_of_12'] = sum(r['checking_error_m'] <= 1000 for r in valid)
    summary['checking_within_3000m_of_12'] = sum(r['checking_error_m'] <= 3000 for r in valid)
    summary['saved_mode_oracle_median_error_m'] = float(np.median(
        [r['saved_mode_oracle_error_m'] for r in valid])) if valid else None
    summary['saved_mode_oracle_p90_error_m'] = float(np.percentile(
        [r['saved_mode_oracle_error_m'] for r in valid], 90)) if valid else None
    result = dict(planned=12, accepted=len(valid), rows=rows, **summary,
                  scoring_all_twelve_seconds=scores['seconds'],
                  source_scores_sha256=digest(scores_path), evaluator_sha256=digest(__file__),
                  qualification='Twelve exposed development recordings, checking split before '
                  'trajectory construction. Checking score rankings sealed before geographic '
                  'evaluation. No independent-recording validation, posterior calibration or '
                  'full64benchmark claim. Scoring is a separately timed diagnostic, not yet an '
                  'integrated cold90s pipeline. Reference remains operator-provided, unsurveyed. '
                  'Failures retained in denominators; split error quantiles conditional '
                  'on acceptance. Saved-mode oracle uses reference solely for diagnosis; '
                  'it is not deployable and does not bound unexplored location modes.')
    output = HERE/'checking-expansion-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
