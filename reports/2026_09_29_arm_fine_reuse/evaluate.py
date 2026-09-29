"""Paired saved-IQ experiment; require unchanged scientific candidate objects."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from itertools import zip_longest
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / '2026_09_29_arm_lag_discovery'
sys.path.insert(0, str(HERE.parent / '2026_09_28_arm_full_optimization'))
import arm_cohort as a


def science(row):
    return {k: v for k, v in row.items()
            if k not in ('timings_ms', 'fine_fft_cache_entries', 'fine_fft_cache_hits')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--reference', default='regional32-v1')
    parser.add_argument('--inputs', type=Path, default=a.INPUTS)
    parser.add_argument('--output', required=True)
    parser.add_argument('--arm', action='store_true')
    parser.add_argument('--features', type=Path, default=PRIOR/'ds7-704-v1/rows.jsonl')
    parser.add_argument('--allow-proposal-changes', action='store_true',
                        help='Record rather than reject changed outputs; requires a fresh standard-hit audit')
    args = parser.parse_args()
    binary = args.binary.resolve()
    receipt = binary.parent / 'fine-reuse-build.json'
    build = json.loads(receipt.read_text())
    assert a.sha(binary) == build['binaries'][binary.name]
    for name, digest in build['sources'].items():
        assert a.sha(binary.parent / name) == digest
    reference = PRIOR / args.reference
    manifest = json.loads((reference / 'manifest.json').read_text())
    assert manifest['complete']
    if args.arm:
        records = {}
        for row in map(json.loads, (reference / 'raw.jsonl').read_text().splitlines()):
            c = row['context']; key = (c['session_id'], c['visit_index'])
            records.setdefault(key, {'context': c, 'rows': []})['rows'].append(row['native'])
        expected = list(records.values())
    else:
        expected = list(map(json.loads, (reference / 'rows.jsonl').read_text().splitlines()))
    assert len(expected) == manifest['processed_dwells']
    features = {}
    for row in map(json.loads, args.features.read_text().splitlines()):
        c = row['context']
        features[(c['session_id'], c['visit_index'], row['window'], row['rx'])] = row
    oracle = json.loads((a.ORACLE / 'oracle.json').read_text())
    templates = {(c['context']['rate_hz'], c['context']['target']['edge']): c['templates']
                 for c in oracle['cases']}
    out = HERE / args.output
    out.mkdir(exist_ok=False)
    remote = '/mnt/glrtbench/fine-reuse-' + str(int(time.time()))
    if args.arm:
        a.remote('mkdir ' + shlex.quote(remote))
        a.upload(binary, remote + '/cohort')
        assert a.remote('sha256sum ' + remote + '/cohort').split()[0] == a.sha(binary)
    def worker(old):
        ctx = old['context']; source = args.inputs / ctx['file']
        assert a.sha(source) == ctx['sha256']
        template = templates[(ctx['rate_hz'], ctx['target']['edge'])]
        paths = [a.ORACLE / template[k]['file'] for k in ('exact', 'control')]
        for k, path in zip(('exact', 'control'), paths):
            assert a.sha(path) == template[k]['sha256']
        n = round(ctx['rate_hz'] / 750)
        regions = []
        for window in range(11):
            for rx in range(2):
                centers = features[(ctx['session_id'], ctx['visit_index'], window, rx)]['ranked_epochs']['combined'][:4]
                epochs = sorted({v for c in centers for v in range(max(0, c-4), min(n, c+5))})
                regions.append(str(len(epochs)) + ' ' + ' '.join(map(str, epochs)))
        with tempfile.TemporaryDirectory(prefix='fine-reuse-') as tmp:
            tmp = Path(tmp)
            raw = tmp / 'input.ci16'; np.load(source, allow_pickle=False).tofile(raw)
            region = tmp / 'regions.txt'; region.write_text('\n'.join(regions) + '\n')
            if args.arm:
                destinations = []
                for path in [*paths, raw, region]:
                    dest = remote + '/' + path.name
                    a.upload(path, dest)
                    assert a.remote('sha256sum ' + shlex.quote(dest)).split()[0] == a.sha(path)
                    destinations.append(dest)
                output = a.remote(shlex.join([remote+'/cohort', str(ctx['rate_hz']), *destinations]), timeout=60)
            else:
                run = subprocess.run([str(binary), str(ctx['rate_hz']), *map(str, paths), str(raw), str(region)],
                                     capture_output=True, text=True, timeout=120, check=True)
                assert not run.stderr
                output = run.stdout
        rows = [json.loads(line) for line in output.splitlines()]
        assert len(rows) == len(old['rows']) == 22
        equal = [science(r) for r in rows] == [science(r) for r in old['rows']]
        if not args.allow_proposal_changes:
            assert equal, ctx
        changed_candidates = sum(a != b for new, ref in zip(rows, old['rows'])
                                 for a, b in zip_longest(new['candidates'], ref['candidates']))
        changed_windows = sum(science(a) != science(b) for a, b in zip(rows, old['rows']))
        return {'context': ctx, 'returncode': 0, 'stderr': '', 'rows': rows,
                'changed_candidates': changed_candidates, 'changed_windows': changed_windows}
    result = []
    with ThreadPoolExecutor(max_workers=1 if args.arm else 4) as pool, (out/'rows.jsonl').open('x') as stream:
        for row in pool.map(worker, expected):
            stream.write(json.dumps(row, allow_nan=False)+'\n'); stream.flush()
            result.append(row)
            print('paired dwells', len(result), flush=True)
    rows = [r for item in result for r in item['rows']]
    summary = {'complete': True, 'reference': str(reference), 'binary_sha256': a.sha(binary),
        'build_sha256': a.sha(receipt), 'rows_sha256': a.sha(out/'rows.jsonl'),
        'reference_manifest_sha256': a.sha(reference/'manifest.json'), 'dwells': len(result),
        'windows': len(rows), 'candidate_entries': sum(r['candidate_count'] for r in rows),
        'changed_candidates': sum(r['changed_candidates'] for r in result),
        'changed_windows': sum(r['changed_windows'] for r in result),
        'scientific_outputs_identical': not any(r['changed_windows'] for r in result),
        'feature_rows_sha256': a.sha(args.features),
        'cache_entries': sum(r['fine_fft_cache_entries'] for r in rows),
        'cache_hits': sum(r['fine_fft_cache_hits'] for r in rows),
        'mean_timings_ms': {k: sum(r['timings_ms'][k] for r in rows)/len(result) for k in rows[0]['timings_ms']},
        'scope': 'search only, proposal/capture excluded; compare standard-hit audit for detection recovery',
        'hardware': 'PLUTO+ CPU0' if args.arm else 'host'}
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({
        'complete': True, 'selected': [r['context'] for r in result],
        'processed_dwells': len(result), 'processed_windows': len(rows),
        'binary_sha256': a.sha(binary), 'rows_sha256': a.sha(out/'rows.jsonl'),
        'method': 'regional proposals, exact lazy fine FFT reuse',
        'feature_rows_sha256': a.sha(args.features),
        'scope': summary['scope'], 'hardware': summary['hardware'],
    }, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
