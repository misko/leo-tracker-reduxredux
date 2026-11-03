"""Audit the fixed eight-scan data-budget screen; never claim held prediction."""
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import harness


def main():
    rows = []
    hashes = {str(p): harness.digest(p) for p in
              (Path(__file__), HERE/'PROTOCOL.md', HERE/'model.py', HERE/'test_model.py')}
    for index in harness.SCREEN:
        base = HERE/'runs/wave1'/f'all_{index:02d}'
        receipt = json.loads(base.with_suffix('.receipt.json').read_text())
        result_path = base.with_suffix('.json')
        result = json.loads(result_path.read_text()) if result_path.exists() else None
        selected = result['selected'] if result else None
        if result:
            for path, sha in result['sources'].items():
                assert harness.digest(path) == sha, path
            for artifact in result['artifacts']:
                assert 'sha256:'+harness.digest(artifact['path']) == artifact['sha256']
            valid = [s for s in result['starts'] if s['qualified']]
            assert (selected is not None) == bool(valid)
            if selected:
                assert selected['score'] == max(s['score'] for s in valid)
                assert not result['metadata']['held_diagnostic_independent']
            hashes[str(result_path)] = harness.digest(result_path)
        hashes[str(base.with_suffix('.receipt.json'))] = harness.digest(base.with_suffix('.receipt.json'))
        old_path = harness.BASE/'runs'/f'{index:02d}_iid.json'
        hashes[str(old_path)] = harness.digest(old_path)
        old = json.loads(old_path.read_text())['selected']
        qualified = bool(selected and receipt['exit_code'] == 0)
        rows.append(dict(index=index, qualified=qualified, exit_code=receipt['exit_code'],
                         error_m=harness.distance(selected['estimate_deg']) if qualified else None,
                         baseline_error_m=harness.distance(old['estimate_deg']),
                         runtime_s=receipt['wall_s'], metadata=result['metadata'] if result else None))
    good = [r for r in rows if r['qualified']]
    summary = dict(attempts=len(rows), qualified=len(good),
                   wins=sum(r['error_m'] < r['baseline_error_m'] for r in good),
                   held_prediction_claim=False, screen_gate=False)
    if len(good) == len(harness.SCREEN):
        for prefix, key in [('', 'error_m'), ('baseline_', 'baseline_error_m')]:
            values = [r[key] for r in rows]
            summary.update({prefix+'median_m': statistics.median(values),
                            prefix+'mean_m': statistics.mean(values),
                            prefix+'p90_m': harness.percentile(values, .9),
                            prefix+'subkm': sum(v < 1000 for v in values)})
        summary['screen_gate'] = (summary['wins'] >= 5 and
            summary['median_m'] <= .9*summary['baseline_median_m'] and
            summary['p90_m'] <= summary['baseline_p90_m'])
    output = dict(schema='ds11-all-observations-screen/v1', summary=summary, rows=rows,
                  source_sha256=hashes)
    with (HERE/'assessment.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
