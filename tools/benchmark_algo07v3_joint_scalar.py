"""Compare full versus scalar joint scores on original native grid captures."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from benchmark_algo07v3_direct_grids import load_capture
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_blas_threads import library_info
from probe_algo07v3_joint_scalar import candidate

from leo.analysis.localization_v3 import joint_density, numpy_factor


def measure(inputs, reference, scalar, mode, original_record, save):
    before, expected, rows = fingerprint(inputs), None, []
    for repeat in range(4):
        order = ('baseline', 'candidate') if repeat % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            fn = reference if side == 'baseline' else scalar
            began, used = time.perf_counter(), time.process_time()
            result = fn(*inputs, optimize_contractions=mode)
            seconds, used = time.perf_counter() - began, time.process_time() - used
            score = result['negative_twice_log_density'] if side == 'baseline' else result
            if not mode and side == 'baseline' and fingerprint(result) != original_record:
                raise ValueError('Full reference no longer matches original native capture')
            if expected is None:
                expected = fingerprint(score)
            row = dict(repeat=repeat, side=side, optimize_contractions=mode,
                       seconds=seconds, cpu_seconds=used,
                       exact_score=fingerprint(score) == expected)
            save(row)
            rows.append(row)
            if not row['exact_score'] or fingerprint(inputs) != before:
                raise ValueError('Scalar score or immutable native inputs changed')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, root = args.native.resolve(), args.output.resolve()
    if root.is_relative_to('/mnt/qnap01') or len(os.sched_getaffinity(0)) != 1:
        parser.error('Local output and exactly one CPU required for serial kernel comparison')
    comparison = json.loads((native / 'comparison.json').read_bytes())
    if not comparison['exact_owned_science_and_artifacts']:
        raise ValueError('Qualified native capture required')
    libraries = library_info()
    if any(row['threads'] != 1 for row in libraries):
        raise ValueError('One BLAS thread required')
    root.mkdir(exist_ok=False)
    capture_root = native / 'baseline'
    records = json.loads((capture_root / 'captures.json').read_bytes())
    scalar, source = candidate()
    paths = [Path(__file__), Path('tools/probe_algo07v3_joint_scalar.py'),
             Path('tools/benchmark_algo07v3_direct_grids.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_blas_threads.py'), Path(joint_density.__file__),
             Path(numpy_factor.__file__), *Path('src/leo/analysis').glob('_joint_lu*.so'),
             native / 'comparison.json', capture_root / 'captures.json',
             *(capture_root / 'captures' / f'{key}.npz' for key in records),
             *(Path(row['path']) for row in libraries)]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    plan = dict(bindings=bindings, libraries=libraries, cpus=sorted(os.sched_getaffinity(0)),
                scope='scalar joint score only; full diagnostic route unchanged',
                production_modified=False, full_pipeline_speedup=None)
    (root / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    (root / 'candidate.py').write_text(source + '\n')
    rows = []
    for key in sorted(records, key=int):
        inputs = load_capture(capture_root, key, records[key])
        for mode in (True, False):
            def save(row, phase_pairs=int(key)):
                row = dict(row, phase_pairs=phase_pairs)
                rows.append(row)
                (root / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
                print(json.dumps(row), flush=True)
            measure(inputs, joint_density.two_family_phase_evidence, scalar, mode,
                    records[key]['result'], save)
    if library_info() != libraries or any(
            hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound dependencies changed')
    (root / 'result.json').write_text(json.dumps(dict(plan=plan, rows=rows, exact=True), indent=2))


if __name__ == '__main__':
    main()
