"""External exact experiment: omit learned-prior updates when no prior groups exist."""

import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import algo07v3_prefixed_prior_oracle as hierarchical
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint


def candidate():
    original = inspect.getsource(hierarchical.hierarchical_bound)
    changed = original

    def replace(before, after):
        nonlocal changed
        if changed.count(before) != 1:
            raise ValueError('Review changed coefficient-prior boundary')
        changed = changed.replace(before, after)

    replace('    history = []\n',
            '    has_prior_groups = bool(len(dimensions))\n'
            '    precision = np.ones(width)\n'
            '    history = []\n')
    replace('''        precision = np.ones(width)
        precision[selected] = v[prior[selected]]''',
            '''        if has_prior_groups:
            precision = np.ones(width)
            precision[selected] = v[prior[selected]]''')
    before = '''        prior_energy = np.bincount(
            prior[selected],
            weights=(coefficient**2 + np.diag(covariance))[selected],
            minlength=len(dimensions),
        )
        next_prior_rate = pb0 + prior_energy / 2'''
    replace(before, '        if has_prior_groups:\n' +
            '\n'.join('    ' + line for line in before.splitlines()) +
            '\n        else:\n            next_prior_rate = prior_rate')
    replace('            float(np.max(abs(np.log(next_prior_rate / prior_rate)), initial=0)),',
            '            (float(np.max(abs(np.log(next_prior_rate / prior_rate)), initial=0))\n'
            '             if has_prior_groups else 0.0),')
    scope = dict(vars(hierarchical))
    exec(compile(changed, '<fixed-coefficient-priors>', 'exec'), scope)
    return scope['hierarchical_bound'], original, changed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        p.error('One CPU and one BLAS thread required')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    meta, arrays = args.capture/'hardest.json', args.capture/'hardest.npz'
    metadata = json.loads(meta.read_bytes())
    assert hashlib.sha256(arrays.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(arrays, allow_pickle=False) as data:
        positional = [data[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): data[k] for k in data.files
                         if k.startswith('keyword_')})
    operation, original, changed = candidate()
    paths = [Path(__file__), Path(hierarchical.__file__), meta, arrays,
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    (args.output/'original.py').write_text(original)
    (args.output/'candidate.py').write_text(changed)
    before = fingerprint((positional, keywords))
    expected = fingerprint(hierarchical.hierarchical_bound(*positional, **keywords))
    rows = []
    for pair in range(6):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            function = operation if side == 'candidate' else hierarchical.hierarchical_bound
            began, used = time.perf_counter(), time.process_time()
            values = [function(*positional, **keywords) for _ in range(3)]
            elapsed, cpu = time.perf_counter()-began, time.process_time()-used
            row = dict(pair=pair, side=side, seconds=elapsed/3, cpu_seconds=cpu/3,
                       calls=3, exact=all(fingerprint(v) == expected for v in values))
            rows.append(row)
            (args.output/'rows.json').write_text(json.dumps(rows, indent=2)+'\n')
            assert row['exact'], 'Candidate changed complete likelihood result'
    assert before == fingerprint((positional, keywords))
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == h for q, h in bindings.items())
    result = dict(exact=True, rows=rows, bindings=bindings, expected=expected,
                  captured_kernel_only=True, production_modified=False, full_pipeline_speedup=None)
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    means = {side:float(np.mean([r['seconds'] for r in rows if r['side']==side]))
             for side in ('baseline','candidate')}
    print(json.dumps(dict(means=means, exact=True)), flush=True)


if __name__ == '__main__':
    main()
