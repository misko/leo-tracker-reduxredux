"""External paired-training experiment on one complete predictive annotation fold.

The original fold body changes only the training dictionary construction. Child
fits return compact final-problem recipes, never live closures. Reconstruction
must reproduce every final calculation/state byte before satellite nomination.
This tool does not change runtime code or claim full-pipeline qualification.
"""

import argparse
import ast
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_discovery_schedule import cpu_seconds, host_resources

from leo.analysis.localization_v3 import prediction, predictive_annotation
from leo.analysis.localization_v3.event_position import cached, make_event_problem
from leo.analysis.localization_v3.recovery_fragments import inactive_fragment_context
from leo.analysis.localization_v3.recovery_inventory import recovery_context
from leo.analysis.localization_v3.recovery_partitions import partition_schedule
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_initial_arms
from leo.storage.localization_v3 import LocalizationV3Store


def trained_record(d, node, keep, arm):
    began = time.perf_counter()
    p, x, meta = prediction.fit_training(d, node, keep, arm)
    return dict(reference=p.reference.copy(), x=x.copy(), meta=meta,
                final=fingerprint((p.calculate(x), p.state(x))),
                seconds=time.perf_counter() - began)


def restore_record(d, node, keep, arm, record):
    means, _ = prediction.prior_means(d, node)
    p = make_event_problem(
        d['scan'], node, keep, arm, record['reference'].copy(), np.ones(len(d['powers'])),
        means, d['model'], [], base_problem_factory=prediction.training_factory(d))
    cached(p)
    x = record['x'].copy()
    if fingerprint((p.calculate(x), p.state(x))) != record['final']:
        raise ValueError('Reconstructed training likelihood differs')
    return p, x, record['meta']


def training_pair(d, node, keep, mapper=map_initial_arms):
    if d.get('numerical_policy') is not None:
        raise ValueError('Mutable numerical-policy replay is outside this experiment')
    records = mapper(lambda arm: trained_record(d, node, keep, arm), prediction.ARMS)
    records = list(records)
    d['_probe_arm_seconds'] = {a: r['seconds']
                               for a, r in zip(prediction.ARMS, records, strict=True)}
    return {arm: restore_record(d, node, keep, arm, record)
            for arm, record in zip(prediction.ARMS, records, strict=True)}


def transform(pair=training_pair):
    source = inspect.getsource(predictive_annotation.annotate_fold)
    tree = ast.parse(source)
    matches = [n for n in tree.body[0].body if isinstance(n, ast.Assign)
               and ast.unparse(n.targets[0]) == 'base']
    if len(matches) != 1 or ast.unparse(matches[0].value) != (
            "{a: fit_training(d, d['node'], keep, a) for a in ARMS}"):
        raise ValueError('Original fold training changed; review extraction')
    matches[0].value = ast.parse("_training_pair(d, d['node'], keep)", mode='eval').body
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(predictive_annotation), _training_pair=pair)
    exec(compile(tree, '<paired-annotation-training>', 'exec'), scope)
    return scope['annotate_fold'], source, ast.unparse(tree)


def load_context(request):
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    prepared = evidence['preparation']
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False) + '\n').encode()
    scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                    hashlib.sha256(noise).hexdigest(), genuine=True)
    d = recovery_context(scan, evidence['audit']['cavity_policy'])
    inv = evidence['audit']['recovery_inventory']
    return d, inv, saved['sha256']


def fold_inputs(d, evidence, index, fold):
    target = evidence['selected_targets'][index]
    inventory = dict(evidence['inventory'], publication_support=evidence['publication_support'])
    p0 = d['problems']['c0'][0]
    if target['inactive_fragment']:
        d, target = inactive_fragment_context(d, inventory, target['track_id'])
    i = target['track_index']
    times = d['scan'].tracks[i]['times']
    full = np.r_[p0.flat_times, times]
    seeds, plan = partition_schedule(full, times)
    return (d, i, full, len(p0.flat_times), seeds[fold], plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=int, default=1)
    parser.add_argument('--fold', type=int, choices=range(3), default=1)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request,
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_discovery_schedule.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    if request['runtime'] != runtime_versions():
        raise ValueError('Match the frozen numerical runtime')
    candidate, original, changed = transform()
    (args.output / 'original.txt').write_text(original)
    (args.output / 'candidate.txt').write_text(changed)
    rows, expected = [], None
    host = host_resources()
    for pair in range(args.repeats):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            d, inv, receipt = load_context(request)
            inputs = fold_inputs(d, inv, args.target, args.fold)
            operation = predictive_annotation.annotate_fold if side == 'baseline' else candidate
            before = cpu_seconds()
            began = time.perf_counter()
            result = operation(*inputs, candidates=12, phase_step=.1, shifted_origin=True)
            elapsed = time.perf_counter() - began
            cpu = np.subtract(cpu_seconds(), before).tolist()
            signature = fingerprint(result)
            if expected is None:
                expected = signature
            exact = signature == expected
            row = dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=cpu, exact=exact,
                       scientific_receipt=receipt, seed=inputs[4], fingerprint=signature,
                       arm_seconds=inputs[0].get('_probe_arm_seconds'))
            rows.append(row)
            (args.output / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps({k: v for k, v in row.items() if k != 'fingerprint'}), flush=True)
            if not exact:
                raise ValueError('Complete predictive fold changed')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound sources changed during benchmark')
    result = dict(rows=rows, bindings=bindings, target=args.target, fold=args.fold,
                  exact=True, resources_start=host, resources_end=host_resources(),
                  affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                  scope='One prepared predictive fold; full five-round training, both arms',
                  full_pipeline_benchmark=False, production_modified=False)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
