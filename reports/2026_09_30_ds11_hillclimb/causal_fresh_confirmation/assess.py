"""Apply the frozen five-scan confirmation gate after endpoint selection."""
import hashlib
import json
from pathlib import Path
import statistics

from run import harness, INDICES

HERE = Path(__file__).resolve().parent


def metrics(values):
    return dict(median_m=statistics.median(values), mean_m=statistics.mean(values),
                p90_m=harness.percentile(values, .9), max_m=max(values),
                subkm=sum(v < 1000 for v in values))


def main():
    bindings = {}
    def read(path):
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())
    rows = []
    for index in INDICES:
        row = dict(full_manifest_index=index)
        for variant in ('original', 'fresh'):
            path = HERE/'runs'/f'{variant}_{index:02d}.json'
            receipt = read(path.with_suffix('.receipt.json'))
            fit = read(path) if path.exists() else None
            selected = fit['selected'] if fit else None
            if fit:
                assert fit['full_manifest_index'] == index and fit['variant'] == variant
                for source, expected in fit['sources'].items():
                    assert harness.digest(source) == expected
                for artifact in fit['artifacts']:
                    assert 'sha256:'+harness.digest(artifact['path']) == artifact['sha256']
                assert fit['metadata']['fit_protocol_sha256'] == harness.digest(HERE/'FIT_PROTOCOL.md')
                valid = [s for s in fit['starts'] if s['qualified']]
                assert bool(valid) == bool(selected)
                if selected:
                    assert selected['score'] == max(s['score'] for s in valid)
                if variant == 'fresh':
                    assert harness.digest(fit['metadata']['patch_path']) == fit['metadata']['patch_sha256']
                row[variant+'_reused'] = fit['reused_unchanged_output']
            qualified = bool(selected and receipt['exit_code'] == 0)
            row[variant+'_qualified'] = qualified
            row[variant+'_exit_code'] = receipt['exit_code']
            row[variant+'_error_m'] = harness.distance(selected['estimate_deg']) if qualified else None
            row[variant+'_wall_s'] = receipt['wall_s']
        row['matched'] = row['original_qualified'] and row['fresh_qualified']
        row['delta_m'] = row['fresh_error_m']-row['original_error_m'] if row['matched'] else None
        if row.get('fresh_reused') and row['matched']:
            assert row['delta_m'] == 0.
        rows.append(row)
    complete = all(r['matched'] for r in rows)
    original = metrics([r['original_error_m'] for r in rows]) if complete else None
    fresh = metrics([r['fresh_error_m'] for r in rows]) if complete else None
    checks = dict(all_five_matched=complete)
    if complete:
        case = next(r for r in rows if r['full_manifest_index'] == 75)
        threshold = max(100., .05*case['original_error_m'])
        checks.update(case75_required_improvement_m=threshold,
                      case75_improves_enough=-case['delta_m'] >= threshold,
                      median_nonworse=fresh['median_m'] <= original['median_m'],
                      mean_nonworse=fresh['mean_m'] <= original['mean_m'],
                      p90_nonworse=fresh['p90_m'] <= original['p90_m'],
                      no_regression_above_50m=max(r['delta_m'] for r in rows) <= 50.)
    gate = bool(complete and all(value for key, value in checks.items() if key != 'case75_required_improvement_m'))
    for path in (Path(__file__), HERE/'FIT_PROTOCOL.md', HERE/'eligibility.json'):
        bindings[str(path)] = harness.digest(path)
    output = dict(schema='ds11-causal-fresh-confirmation-assessment/v1', rows=rows,
                  denominator=5, matched=sum(r['matched'] for r in rows), original=original, fresh=fresh,
                  checks=checks, confirmation_gate=gate, source_sha256=bindings,
                  limitation='Metadata-selected same-site confirmation; unsurveyed reference; no general deployment accuracy claim.')
    with (HERE/'assessment.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in output.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
