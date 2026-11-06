"""Observe complete native recovery for repeated new-family/joint control cores."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from check_algo07v3_scan_likelihood import fingerprint

from leo.cli.algo07v3 import supervise, worker, write

CORE_FIELDS = (
    'endpoint_east_north_km', 'endpoint_latlon', 'state', 'phase_reference', 'gates',
    'linear_gates', 'negative_twice_elbo', 'curved_negative_twice_elbo', 'RMS_hz',
    'active_points', 'predictive_points', 'linear_calibration_max_difference',
    'events', 'event_amplitudes_hz', 'history',
)


def compare_cores(stages):
    controls, joint, pairs = [], [], []
    for name, record in stages.items():
        value = record['value']
        if isinstance(value, dict) and 'new_family' in value and 'control' in value:
            optimizer = value['protocol']['optimizer'].split()[0]
            if optimizer not in ('lbfgsb', 'powell'):
                raise ValueError('Unknown inclusion optimizer')
            controls.append((name, optimizer, value['control']['arms']))
        elif (isinstance(value, dict) and value.get('protocol', {}).get('method') == 'control'
              and 'result' in value):
            optimizer = value['protocol'].get('optimizer', 'lbfgsb').lower()
            joint.append((name, optimizer, value['protocol']['arm'], value['result'],
                          record['seconds']))
    for name, optimizer, arm, value, seconds in joint:
        for other_name, other_optimizer, arms in controls:
            if optimizer != other_optimizer:
                continue
            old = arms[arm]
            missing = sorted(set(CORE_FIELDS) - (value.keys() & old.keys()))
            if missing:
                raise ValueError('Control core fields missing: ' + ', '.join(missing))
            differences = [key for key in CORE_FIELDS
                           if fingerprint(old[key]) != fingerprint(value[key])]
            pairs.append(dict(joint_stage=name, inclusion_stage=other_name, arm=arm,
                              optimizer=optimizer, exact_core=not differences,
                              differing_fields=differences, joint_stage_seconds=seconds,
                              baseline_core=fingerprint({k: old[k] for k in CORE_FIELDS}),
                              joint_core=fingerprint({k: value[k] for k in CORE_FIELDS})))
    return dict(new_family_controls=len(controls), joint_controls=len(joint), pairs=pairs,
                sufficient_for_reuse=False, complete_fit_reused=False)


def observed_worker(root):
    from leo.application import localization_v3 as policy

    original = policy.recover_predictive_checkpoint

    def checkpoint(*args, **kwargs):
        result = original(*args, **kwargs)
        before = fingerprint(result['recovery'])
        census = compare_cores(result['completed_stages'])
        census['stage_names'] = list(result['completed_stages'])
        census['recovery_signature'] = before
        census['stateful_policy'] = args[0]['recovery_context'].get('numerical_policy') is not None
        assert before == fingerprint(result['recovery'])
        write(root / 'census.json', census)
        return result

    with patch.object(policy, 'recover_predictive_checkpoint', checkpoint):
        return worker(root / 'request.json', root / 'worker.json', False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        raise SystemExit(observed_worker(args.worker))
    if args.request is None or args.output is None:
        parser.error('--request and --output required')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    if sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Requires CPU affinity 0,1,2')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    request['output_root'] = str(root / 'publication')
    write(root / 'request.json', request)
    paths = [*Path('src').rglob('*.py'), Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'), args.request]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=bindings, profiled=True, production_modified=False,
                                  input_request=str(args.request.resolve()), timeout_seconds=1200))
    with (root / 'worker.log').open('xb') as log:
        process = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                             '--worker', str(root)], log=log, timeout=1200,
                            environment=dict(os.environ, OPENBLAS_NUM_THREADS='1',
                                             OMP_NUM_THREADS='1'))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(process=process, runtime_modified=False, full_pipeline_speedup=None)
    if process['returncode'] == 0:
        result['census'] = json.loads((root / 'census.json').read_bytes())
        result['worker'] = json.loads((root / 'worker.json').read_bytes())
    write(root / 'result.json', result)
    print(json.dumps(dict(process=process, census_available='census' in result)))
    raise SystemExit(process['returncode'])


if __name__ == '__main__':
    main()
