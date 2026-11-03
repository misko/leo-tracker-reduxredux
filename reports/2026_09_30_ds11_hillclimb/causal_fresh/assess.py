"""Report every metadata-selected attempt and the unchanged-panel denominator."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ds11_harness', HERE.parent/'harness.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
INDICES = (10, 13, 16, 27, 31)


def metrics(values):
    return dict(count=len(values), median_m=statistics.median(values),
                mean_m=statistics.mean(values), p90_m=harness.percentile(values, .9),
                max_m=max(values), subkm=sum(x < 1000 for x in values)) if values else None


def main():
    bindings = {}

    def read(path):
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    old = {i: read(harness.BASE/'runs'/f'{i:02d}_iid.json')['selected'] for i in range(32)}
    original = {i: harness.distance(s['estimate_deg']) for i, s in old.items()}
    errors = {i: e for i, e in original.items() if i not in INDICES}
    rows = []
    for index in INDICES:
        path = HERE/'runs'/'causal'/f'fresh_{index:02d}.json'
        receipt = read(path.with_suffix('.receipt.json'))
        fit = read(path) if path.exists() else None
        selected = fit['selected'] if fit else None
        if fit:
            for start in fit['starts']:
                assert start['qualified'] == bool(start['success'] and not start['boundary']
                    and start['gradient'] <= .01 and start['audit'] <= .02)
            valid = [s for s in fit['starts'] if s['qualified']]
            assert bool(selected) == bool(valid)
            if selected:
                assert selected['score'] == max(s['score'] for s in valid)
            for artifact in fit['artifacts']:
                assert 'sha256:'+harness.digest(artifact['path']) == artifact['sha256']
            assert harness.digest(fit['metadata']['patch_path']) == fit['metadata']['patch_sha256']
            assert harness.digest(HERE/'PROTOCOL.md') == fit['metadata']['protocol_sha256']
            bindings[fit['metadata']['patch_path']] = fit['metadata']['patch_sha256']
        qualified = bool(selected and receipt['exit_code'] == 0)
        if qualified:
            assert fit['index'] == index and fit['variant'] == 'fresh'
            assert fit['session'] == json.loads((harness.BASE/'plan.json').read_text())['inputs'][index]['session_id']
            for source, expected in fit['sources'].items():
                assert hashlib.sha256(Path(source).read_bytes()).hexdigest() == expected
            errors[index] = harness.distance(selected['estimate_deg'])
        rows.append(dict(index=index, qualified=qualified, exit_code=receipt['exit_code'],
                         baseline_error_m=original[index], error_m=errors.get(index),
                         delta_m=errors[index]-original[index] if qualified else None,
                         wall_s=receipt['wall_s']))
    result = dict(schema='ds11-causal-fresh-assessment/v1', rows=rows,
                  changed_attempts=len(INDICES), changed_qualified=sum(r['qualified'] for r in rows),
                  changed_wins=sum(r['qualified'] and r['delta_m'] < 0 for r in rows),
                  unchanged_exact_outputs=27, output_coverage=len(errors), denominator=32,
                  baseline=metrics(list(original.values())),
                  qualified_outputs=metrics(list(errors.values())),
                  full_panel=metrics(list(errors.values())) if len(errors) == 32 else None,
                  limitation='Exploratory conditional-shortlist ablation; confirmation required. No fallback or failure exclusion in full_panel.',
                  source_sha256=bindings)
    result['source_sha256'][str(Path(__file__))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with (HERE/'assessment.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
