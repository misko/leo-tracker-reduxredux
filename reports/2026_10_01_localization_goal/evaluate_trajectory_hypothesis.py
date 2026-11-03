"""Geographic and common checking-score comparison after sealed cold-fit audits."""
import importlib.util
import json
from pathlib import Path

from regression_batch import digest

HERE = Path(__file__).resolve().parent


def sealed(name):
    path = HERE/name
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    return json.loads(path.read_text())


def main():
    audit = sealed('trajectory-hypothesis-v1-audit.json')
    scores = {r['unit']: r for r in sealed('trajectory-hypothesis-checking-v1.json')['rows']}
    old_scores = {r['unit']: r for r in sealed('checking-expansion-v1.json')['rows']}
    baseline = {r['unit']: r for r in sealed('candidate-joint-expansion-v1-evaluation.json')[
        'rows'] if r['arm'] == 'candidate'}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('trajectory_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    rows = []
    for row in audit['rows']:
        unit = row['unit']
        out = dict(**row, error_m=None, checking_log_ratio_gain=None)
        if row['accepted']:
            path = HERE/'trajectory-hypothesis-v1'/(unit+'.json')
            assert digest(path) == row['receipt_sha256']
            receipt = json.loads(path.read_text())
            out['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*receipt['best']['mean'][:2]), reference.REFERENCE)
            out['original_all_data_error_m'] = baseline[unit]['all_data_baseline_error_m']
            out['chronological_split_error_m'] = baseline[unit]['baseline_error_m']
            new, old = scores[unit], old_scores[unit]
            assert new['source_group_order'] == old['source_group_order']
            new_mode = next(m for m in new['modes']
                            if m['seed_index'] == new['training_winner_seed'])
            old_mode = next(m for m in old['modes']
                            if m['seed_index'] == old['training_winner_seed'])
            out['checking_log_ratio_gain'] = new_mode['total_log_ratio']-old_mode['total_log_ratio']
            out['checking_groups'] = new['groups']
            out['new_groups_with_prediction'] = new_mode['groups_with_prediction']
            out['old_groups_with_prediction'] = old_mode['groups_with_prediction']
        rows.append(out)
    result = dict(rows=rows, planned=3, accepted=audit['accepted'],
        evaluator_sha256=digest(__file__),
        qualification='First-ranked training trajectory hypothesis, first scan per dataset. '
        'Cold acquisition and fitting; preprocessing separate. Geography scored only after '
        'audit. Compare checking composite scores on identical raw candidate groups without '
        'reranking location seeds. This is exposed development data, not held-out validation. '
        'Different training track sets have incomparable raw training objectives.')
    path = HERE/'trajectory-hypothesis-v1-evaluation.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
