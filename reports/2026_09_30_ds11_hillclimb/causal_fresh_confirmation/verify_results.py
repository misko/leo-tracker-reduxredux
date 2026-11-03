"""Independent receipt, seed, qualification and frozen-source result audit."""
import json
import math
from pathlib import Path

from run import digest, INDICES

HERE = Path(__file__).resolve().parent


def main():
    paths = [Path(__file__), HERE/'assessment.json', HERE/'patch-audit.json']
    assessment = json.loads(paths[1].read_text())
    patch_audit = json.loads(paths[2].read_text())
    for source, expected in assessment['source_sha256'].items():
        assert digest(source) == expected
    for source, expected in patch_audit['source_sha256'].items():
        assert digest(source) == expected
    rows = []
    for index in INDICES:
        fits = {}
        for variant in ('original', 'fresh'):
            path = HERE/'runs'/f'{variant}_{index:02d}.json'
            receipt_path = path.with_suffix('.receipt.json')
            fit = json.loads(path.read_text())
            receipt = json.loads(receipt_path.read_text())
            assert receipt['variant'] == fit['variant'] == variant
            assert receipt['full_manifest_index'] == fit['full_manifest_index'] == index
            assert receipt['runner_sha256'] == digest(HERE/'run.py')
            assert receipt['exit_code'] == 0 and receipt['wall_s'] <= 95
            for source, expected in fit['sources'].items():
                assert digest(source) == expected
            assert [s['seed'] for s in fit['starts'][:3]] == [[-2., 0., 0.], [0., 0., 0.], [2., 0., 0.]]
            for start in fit['starts']:
                finite = all(math.isfinite(float(v)) for v in start['x']+[start['score'],start['gradient'],start['audit']])
                expected = start['success'] and finite and not start['boundary'] and start['gradient'] <= .01 and start['audit'] <= .02
                assert start['qualified'] == expected
            valid = [s for s in fit['starts'] if s['qualified']]
            assert bool(fit['selected']) == bool(valid)
            if valid:
                assert fit['selected']['score'] == max(s['score'] for s in valid)
            fits[variant] = fit
            paths.extend([path, receipt_path])
        assert fits['original']['session'] == fits['fresh']['session']
        assert fits['original']['fourth_seed'] == fits['fresh']['fourth_seed']
        assert len(fits['original']['starts']) == len(fits['fresh']['starts']) == 4
        assert fits['original']['starts'][3]['seed'] == fits['original']['fourth_seed']
        assert fits['fresh']['starts'][3]['seed'] == fits['original']['fourth_seed']
        patch = next(r for r in patch_audit['rows'] if r['index'] == index)
        assert fits['fresh']['metadata']['patch_sha256'] == patch['patch_sha256']
        assert fits['fresh']['metadata']['changed_slots'] == patch['changed_slots']
        assert fits['fresh']['reused_unchanged_output'] == (patch['changed_slots'] == 0)
        if patch['changed_slots'] == 0:
            assert fits['fresh']['selected'] == fits['original']['selected']
        rows.append(dict(index=index, status='passed', reused=patch['changed_slots'] == 0))
    output = dict(schema='ds11-causal-confirmation-result-verification/v1', status='passed', rows=rows,
                  source_sha256={str(p):digest(p) for p in paths})
    with (HERE/'verification.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
