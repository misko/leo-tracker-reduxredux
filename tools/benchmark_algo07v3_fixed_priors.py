"""Exact fixed-prior experiment on both full hard-fold calibration arms."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from benchmark_algo07v3_training_kernel import trial
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_fixed_priors import candidate, hierarchical
from probe_algo07v3_posterior_buffers import training_inputs

from leo.operations.localization_v3_job import runtime_versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-root', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/probe_algo07v3_fixed_priors.py'), Path(hierarchical.__file__),
             Path('tools/probe_algo07v3_posterior_buffers.py'),
             Path('tools/benchmark_algo07v3_training_kernel.py'),
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    expected_paths = {arm:args.expected_root/f'{arm}-0-candidate.json'
                      for arm in ('c0','fitted_c')}
    paths.extend(expected_paths.values())
    bindings = {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    operation, original, changed = candidate()
    (args.output/'original.py').write_text(original)
    (args.output/'candidate.py').write_text(changed)
    (args.output/'plan.json').write_text(json.dumps(dict(bindings=bindings,
        affinity=sorted(os.sched_getaffinity(0)), blas_threads=1, phase_rounds=5,
        optimizer_iterations=48, target_index=1, fold_index=1), indent=2)+'\n')
    rows = []
    for arm in ('c0','fitted_c'):
        expected = json.loads(expected_paths[arm].read_bytes())['signature']
        order = ('baseline','candidate') if arm=='c0' else ('candidate','baseline')
        for side in order:
            d, keep, receipt, seed, split = training_inputs(request)
            before = fingerprint((d['node'],keep))
            function = hierarchical.hierarchical_bound if side=='baseline' else operation
            result = trial(d,keep,arm,function)
            row = dict(arm=arm,side=side,**result,exact=result['signature']==expected,
                       scientific_receipt=receipt,seed=seed,split=split)
            rows.append(row)
            (args.output/f'{arm}-{side}.json').write_text(json.dumps(row,indent=2)+'\n')
            print(json.dumps({k:row[k] for k in ('arm','side','seconds','cpu_seconds','exact')}),
                  flush=True)
            assert row['exact'] and before==fingerprint((d['node'],keep))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in bindings.items())
    (args.output/'result.json').write_text(json.dumps(dict(rows=rows,exact=True,
        bindings=bindings,production_modified=False,full_pipeline_speedup=None),indent=2)+'\n')


if __name__=='__main__':
    main()
