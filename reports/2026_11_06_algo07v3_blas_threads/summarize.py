"""Bind the existing full profile and preserve the three completed BLAS trials."""

import hashlib
import json
import shutil
import statistics
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = Path(__file__).resolve().parent
    repo = out.parent.parent
    profile = out.parent / '2026_11_06_algo07v3_full_profile'
    bindings = json.loads((profile / 'profile/plan.json').read_bytes())['bindings']
    assert all(digest(Path(p)) == sha for p, sha in bindings.items())
    source = repo / 'tools/probe_algo07v3_blas_threads.py'
    shutil.copyfile(source, out / 'measured-split.py')
    summaries = []
    table = ['| Threaded library | Threads | Initial exact | Initial wall / CPU s | '
             'Recovery exact | Recovery wall / CPU s |',
             '| --- | ---: | --- | ---: | --- | ---: |']
    for backend, suffix in [('both', ''), ('numpy', '-numpy'), ('scipy', '-scipy')]:
        root = Path(f'/srv/bulk/leo-dev/algo07v3-blas-threads{suffix}-20261106')
        result = json.loads((root / 'result.json').read_bytes())
        for name, sha in result['bindings'].items():
            path = Path(name)
            if path == source:
                path = out / ('measured-uniform.py' if backend == 'both' else 'measured-split.py')
            assert digest(path) == sha, name
        dest = out / 'receipts' / backend
        dest.mkdir(parents=True, exist_ok=True)
        for name in ('result.json', 'plan.json'):
            shutil.copyfile(root / name, dest / name)
        reference = Path(result['rows'][0]['root'])
        for row in result['rows']:
            worker = Path(row['root'])
            copied = dest / worker.name
            copied.mkdir(exist_ok=True)
            for name in ('result.json', 'case-0.npz', 'case-1.npz', 'worker.log'):
                shutil.copyfile(worker / name, copied / name)
            for lib in row['libraries']:
                assert digest(Path(lib['path'])) == lib['sha256']
                expected = row['threads'] if backend in ('both', lib['owner']) else 1
                assert lib['threads'] == expected
            cases = []
            for case in row['cases']:
                index = case['index']
                with np.load(reference / f'case-{index}.npz') as a, np.load(
                    worker / f'case-{index}.npz'
                ) as b:
                    assert set(a.files) == set(b.files)
                    differences = {key: float(np.max(np.abs(a[key] - b[key]), initial=0))
                                   for key in a.files}
                cases.append(dict(
                    exact=case['exact'], differing_fields=case['differing_fields'],
                    samples=len(case['observations']), max_absolute_difference=differences,
                    wall_seconds=statistics.mean(v['seconds'] for v in case['observations']),
                    cpu_seconds=statistics.mean(v['cpu_seconds'] for v in case['observations'])))
            summaries.append(dict(backend=backend, sequence=row['sequence'],
                                  threads=row['threads'], cases=cases))
            a, b = cases
            label = backend + (' (end control)' if row['sequence'] else '')
            table.append(
                f"| {label} | {row['threads']} | {a['exact']} | "
                f"{a['wall_seconds']:.3f} / {a['cpu_seconds']:.3f} | {b['exact']} | "
                f"{b['wall_seconds']:.3f} / {b['cpu_seconds']:.3f} |")
    summary = dict(full_profile_bindings_verified=len(bindings), trials=summaries,
                   new_runtime_change=False, full_pipeline_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (out / 'timings.md').write_text('\n'.join(table) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
