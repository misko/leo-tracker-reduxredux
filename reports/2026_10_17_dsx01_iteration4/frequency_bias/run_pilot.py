"""Matched fixed-bank original-classifier bias pilots; no target-aware inputs."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
import common
from model import ConstantBiasObjective
from profiles import fit

_contexts = {}


def execute(task):
    source_id, arm, method, maximum, seconds = task
    name = f'{source_id}-{arm}-{method}'
    path = HERE/'results'/(name+'.json')
    if path.exists():
        return dict(task=name, state='existing')
    try:
        if source_id not in _contexts:
            _contexts[source_id] = common.load_context(source_id)
        original = _contexts[source_id]
        seed_path = REPORTS/'2026_10_16_dsx01_iteration2/results'/f'{source_id}-fitted-c-profile.json'
        seed = json.loads(seed_path.read_text())
        v, n = np.array(seed['vector']), np.array(seed['nuisance'])
        if arm == 'zero-c':
            v[6] = 0.
        bias = method != 'b0'
        sigma = float(method.split('-')[0][1:]) if bias else None
        if bias:
            model = ConstantBiasObjective(original.model, sigma)
            full = ConstantBiasObjective(original.full_model, sigma)
            n = np.r_[n, np.zeros(model.bias_count)]
            reference = (original.vector, np.r_[original.nuisance, np.zeros(model.bias_count)])
        else:
            model, full = original.model, original.full_model
            reference = (original.vector, original.nuisance)
        context = replace(original, model=model, full_model=full, vector=v, nuisance=n,
            fixed_c=arm == 'zero-c', deadline=time.monotonic()+seconds)
        if not bias or method.endswith('continuation'):
            solved = common.refit(context, v, n, max_evaluations=maximum,
                max_seconds=seconds, fixed_c=context.fixed_c)
        else:
            solved = fit(context, max_evaluations=maximum, max_seconds=seconds)
        vv, nn = solved['vector'], solved['nuisance']
        mask = common.challenge_mask(context)
        record = dict(task=name, source_id=source_id, arm=arm, method=method,
            seed_policy='same immutable fitted-c profile endpoint; only c is zeroed for zero-c; biases initialize zero',
            seed_path=str(seed_path), seed_sha256='sha256:'+hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            bias_sigma_hz=sigma, bias_bound_hz=4000. if bias else 0.,
            budget=dict(max_evaluations=maximum, max_seconds=seconds),
            diagnostics=solved['diagnostics'], endpoint_audit=common.endpoint_status(context, vv, nn),
            full_scan=common.measure(context, vv, nn, original=reference),
            challenge=common.measure(context, vv, nn, original=reference, mask=mask),
            outside=common.measure(context, vv, nn, original=reference, mask=~mask),
            vector=vv, nuisance=nn, source=original.source,
            biases_hz={str(int(number)):float(value) for number, value in
                zip(context.bank.numbers, nn[model.bias_start:] if bias else np.zeros(len(context.bank.numbers)))},
            cost_qualification='Independent replay/endpoint audit/metrics outside inference budget; never used to choose parameters',
            qualification='Full-recording development pilot; empirical constant-Hz nuisance, no demonstrated cause or predictive validity; fixed candidate bank and original winner/classifier denominators.')
        record['code_sha256'] = {name:'sha256:'+hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in ['model.py', 'profiles.py', 'run_pilot.py']}
        _, _, best, assigned, residual = common.point_state(full, vv, nn)
        np.savez_compressed(path.with_suffix('.npz'), associated=assigned,
            residual_hz=residual, satellite_number=context.bank.numbers[best],
            challenge_mask=mask, observation_id=np.asarray(context.observations.window_ids),
            times_s=context.observations.times_s, receiver=context.observations.receiver,
            channel=context.observations.channel)
        common.save_json(path, record)
        return dict(task=name, state='complete', full=record['full_scan']['associated'],
            challenge=record['challenge']['associated'], accepted=record['endpoint_audit']['accepted'],
            kkt=record['endpoint_audit'].get('stationarity'),
            objective=record['full_scan']['objective'], evaluations=solved['diagnostics'].get('evaluations'))
    except Exception as error:
        failure = dict(task=name, state='failed', error_type=type(error).__name__,
            error=str(error), traceback=traceback.format_exc())
        common.save_json(path, failure)
        return failure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', nargs='+', default=['S01', 'S04'])
    parser.add_argument('--arms', nargs='+', default=['fitted-c', 'zero-c'])
    parser.add_argument('--methods', nargs='+', default=['b0', 'b300-profile', 'b1000-profile'])
    parser.add_argument('--max-evaluations', type=int, default=1000)
    parser.add_argument('--seconds', type=float, default=120.)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    (HERE/'results').mkdir(exist_ok=True)
    tasks = [(source, arm, method, args.max_evaluations, args.seconds)
        for source in args.sources for arm in args.arms for method in args.methods]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, task) for task in tasks]
        for future in as_completed(futures):
            print(json.dumps(future.result()), flush=True)


if __name__ == '__main__':
    main()
