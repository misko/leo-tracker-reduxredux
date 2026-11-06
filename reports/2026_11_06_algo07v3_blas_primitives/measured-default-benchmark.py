"""Fresh-process paired covariance-thread timings, without baseline spin carryover."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def worker(root, side, reference):
    import numpy as np
    from check_algo07v3_scan_likelihood import fingerprint
    from probe_algo07v3_blas_threads import library_info
    from probe_algo07v3_covariance_threads import candidate, configuration, hierarchical

    plan = json.loads((root.parent / 'plan.json').read_bytes())
    if sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        raise ValueError('Require CPU affinity 0,1,2')
    libraries = library_info()
    if any(row['threads'] != 1 for row in libraries):
        raise ValueError('Both libraries must start serial')
    capture = Path(plan['capture'])
    meta = json.loads((capture / 'hardest.json').read_bytes())
    with np.load(capture / 'hardest.npz', allow_pickle=False) as data:
        positional = [data[f'argument_{i}'] for i in range(4)]
        keywords = dict(meta['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): data[k] for k in data.files
                         if k.startswith('keyword_')})
    before = fingerprint((positional, keywords))
    function = hierarchical.hierarchical_bound
    if side == 'candidate':
        function, _ = candidate(configuration(libraries), plan['threads'])
    expected = json.loads(reference.read_bytes())['expected'] if reference else None
    warm = fingerprint(function(*positional, **keywords))
    if expected is None:
        assert side == 'baseline'
        expected = warm
    assert warm == expected
    began, used = time.perf_counter(), time.process_time()
    values = [function(*positional, **keywords) for _ in range(3)]
    elapsed, cpu = time.perf_counter() - began, time.process_time() - used
    exact = all(fingerprint(value) == expected for value in values)
    assert exact and fingerprint((positional, keywords)) == before
    assert library_info() == libraries
    result = dict(side=side, seconds=elapsed / 3, cpu_seconds=cpu / 3, calls=3,
                  exact=exact, expected=expected, libraries=libraries,
                  thread_count=len(list(Path('/proc/self/task').iterdir())),
                  thread_settings_returned_to_one=True)
    (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


def main():
    from probe_algo07v3_blas_threads import digest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--threads', type=int, choices=(2, 3))
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--side', choices=('baseline', 'candidate'))
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.side, args.reference)
        return
    if not args.output or not args.capture or not args.threads:
        parser.error('--output, --capture, --threads required')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths = [Path(__file__), Path('tools/probe_algo07v3_covariance_threads.py'),
             Path('tools/profile_algo07v3_blas_primitives.py'),
             Path('tools/probe_algo07v3_blas_threads.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('src/leo/analysis/localization_v3/hierarchical.py'),
             args.capture / 'hardest.json', args.capture / 'hardest.npz']
    bindings = {str(path.resolve()): digest(path) for path in paths}
    meta = json.loads((args.capture / 'hardest.json').read_bytes())
    assert digest(args.capture / 'hardest.npz') == meta['arrays_sha256']
    plan = dict(capture=str(args.capture.resolve()), threads=args.threads, bindings=bindings)
    (root / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    rows, reference = [], None
    for pair in range(6):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            target = root / f'{pair}-{side}'
            target.mkdir()
            command = ['taskset', '-c', '0,1,2', sys.executable, '-B',
                       str(Path(__file__).resolve()), '--worker', str(target), '--side', side]
            if reference:
                command += ['--reference', str(reference)]
            with (target / 'worker.log').open('xb') as stream:
                subprocess.run(command, check=True, timeout=60, stdout=stream,
                               stderr=subprocess.STDOUT, env=dict(
                                   os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
            if reference is None:
                reference = target / 'result.json'
            rows.append(dict(pair=pair, **json.loads((target / 'result.json').read_bytes())))
    assert all(digest(Path(p)) == sha for p, sha in bindings.items())
    result = dict(plan=plan, rows=rows, fresh_process_per_side=True,
                  captured_kernel_only=True, production_modified=False, full_pipeline_speedup=None)
    (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps([dict(pair=r['pair'], side=r['side'], seconds=r['seconds'],
                           cpu_seconds=r['cpu_seconds']) for r in rows]))


if __name__ == '__main__':
    main()
