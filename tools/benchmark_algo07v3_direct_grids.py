"""Benchmark direct chunks on hash-bound grids captured from a native scan."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_blas_threads import library_info
from probe_algo07v3_joint_chunks import candidate

from leo.analysis.localization_v3 import joint_density


def load_capture(root, key, record):
    path = root / 'captures' / f'{key}.npz'
    if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Native capture file changed')
    with np.load(path, allow_pickle=False) as data:
        inputs = [[data[f'{name}_{i}'] for i in range(2)]
                  for name in ('observed', 'means', 'modes', 'log_priors', 'visible')]
        inputs.insert(2, data['base_covariance'])
    if fingerprint(inputs) != record['input']:
        raise ValueError('Native input bytes changed during capture round trip')
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, native = args.output.resolve(), args.native.resolve()
    if root.is_relative_to('/mnt/qnap01') or sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Local output and exactly CPU slots 0,1,2 required')
    baseline = native / 'baseline'
    verification = json.loads((native / 'comparison.json').read_bytes())
    if not verification['exact_owned_science_and_artifacts']:
        raise ValueError('Complete native scientific comparison required first')
    records = json.loads((baseline / 'captures.json').read_bytes())
    libraries = library_info()
    if not records or any(row['threads'] != 1 for row in libraries):
        raise ValueError('Real captured grids and one-thread BLAS required')
    root.mkdir(exist_ok=False)
    fn, _ = candidate(workers=3)
    paths = [Path(__file__), Path('tools/probe_algo07v3_joint_chunks.py'),
             Path('tools/probe_algo07v3_blas_threads.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'), Path(joint_density.__file__),
             native / 'comparison.json', baseline / 'captures.json']
    paths += [baseline / 'captures' / f'{key}.npz' for key in records]
    pins = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (root / 'plan.json').write_text(json.dumps(dict(bindings=pins, libraries=libraries,
        workers=3, direct_only=True, native=str(native)), indent=2))
    rows = []
    for key in sorted(records, key=int):
        inputs = load_capture(baseline, key, records[key])
        before = fingerprint(inputs)
        for repeat in range(6):
            for side in (('baseline', 'candidate') if repeat % 2 == 0
                         else ('candidate', 'baseline')):
                function = joint_density.two_family_phase_evidence if side == 'baseline' else fn
                start, used = time.perf_counter(), time.process_time()
                result = function(*inputs, optimize_contractions=False)
                wall, used = time.perf_counter() - start, time.process_time() - used
                exact = fingerprint(result) == records[key]['result']
                rows.append(dict(phase_pairs=int(key), repeat=repeat, side=side, seconds=wall,
                                 cpu_seconds=used, exact_native_result=exact))
                (root / 'rows.json').write_text(json.dumps(rows, indent=2))
                print(json.dumps(rows[-1]), flush=True)
                if not exact or fingerprint(inputs) != before:
                    raise ValueError('Full native kernel result or input bytes changed')
    if library_info() != libraries or any(
            hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in pins.items()):
        raise ValueError('Bound dependencies changed')
    outcome = dict(rows=rows, exact_native_results=True,
                   native_pipeline_speedup=None, bindings=pins)
    (root / 'result.json').write_text(json.dumps(outcome, indent=2))


if __name__ == '__main__':
    main()
