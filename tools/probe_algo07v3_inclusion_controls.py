"""External census/prototype for exact repeated inclusion-control pairs.

No runtime edits. Capture both full calibration-arm results under a complete
normalized scientific-state key; never reuse target fits or stateful policy work.
"""

import argparse
import ast
import copy
import dataclasses
import hashlib
import inspect
import json
import os
import time
from pathlib import Path
from types import FunctionType

from probe_algo07v3_annotation_arms import load_context
from probe_algo07v3_native_recovery_queue import recovery_trial, signature

from leo.analysis.localization_v3 import recovery_controller, recovery_inclusion
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.operations.localization_v3_job import runtime_versions, validate_request
from leo.operations.localization_v3_parallel import _ordered
from leo.storage.localization_v3 import LocalizationV3Store


def normalized(value):
    if isinstance(value, (set, frozenset)):
        return {'set_values': sorted((normalized(x) for x in value), key=repr)}
    if dataclasses.is_dataclass(value):
        return {f.name: normalized(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    return value


def control_key(kind, d, inventory, count, option):
    if (d.get('numerical_policy') is not None or 'problem_factory' in d
            or type(d['scan']) is not ScanLikelihood or (kind == 'fit_shared' and option)):
        return None
    scan = dict(vars(d['scan']))
    if not 0 < count <= len(scan['tracks']):
        return None
    # These are exactly the three lists extended by inactive/gap views. Control
    # fitting uses original members/entries and truncates membership to count.
    for name in ('tracks', 'white', 'rx_basis'):
        scan[name] = scan[name][:count]
    if any(e['track_index'] >= count for e in d['entries']):
        return None
    state = dict(kind=kind, option=option, count=count, scan=scan,
                 context={k: d[k] for k in ('node', 'keep', 'powers', 'means', 'model', 'entries')},
                 policy=inventory['policy'])
    try:
        return signature(normalized(state))
    except TypeError:
        # Unknown mutable/callable state is not silently omitted from the key.
        return None


class ControlPairs:
    def __init__(self, reuse, key=control_key):
        self.reuse, self.key = reuse, key
        self.values, self.rows = {}, []

    def context(self, d, kind, option):
        return d

    def __call__(self, compute, control, kind, d, inventory, count, option):
        if not control:
            return compute()
        began = time.perf_counter()
        key = self.key(kind, d, inventory, count, option)
        key_seconds = time.perf_counter() - began
        duplicate = key is not None and key in self.values
        began = time.perf_counter()
        value = copy.deepcopy(self.values[key]) if self.reuse and duplicate else compute()
        seconds = time.perf_counter() - began
        actual = signature(value)
        if duplicate and actual != signature(self.values[key]):
            raise ValueError('Same control inputs produced different complete outputs')
        if key is not None and not duplicate:
            self.values[key] = copy.deepcopy(value)
        self.rows.append(dict(kind=kind, option=option, key=key, key_seconds=key_seconds,
                              duplicate=duplicate, reused=self.reuse and duplicate,
                              seconds=seconds, complete_output_signature=actual))
        return value

    pair = __call__


def transformed(kind, pairs):
    original = getattr(recovery_inclusion, kind)
    if 'control_cache' in inspect.signature(original).parameters:
        def wrapped(*args, control_cache=None, **kwargs):
            return original(*args, control_cache=pairs, **kwargs)
        return wrapped, inspect.getsource(original)
    tree = ast.parse(inspect.getsource(original))
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and len(n.targets) == 1 and ast.unparse(n.targets[0]) == 'pair']
    if len(matches) != 1:
        raise ValueError('Review changed inclusion pair implementation')
    item = matches[0]
    before = ast.dump(item.value)
    if not ast.unparse(item.value).startswith('dict(zip(ARMS, numerics.map_calibration_arms('):
        raise ValueError('Review changed inclusion execution port')
    role = 'name' if kind == 'fit_shared' else 'variant'
    option = 'conditional_satellite_refresh' if kind == 'fit_shared' else 'optimizer'
    item.value = ast.Call(func=ast.Name(id='_control_pair', ctx=ast.Load()),
                         args=[ast.Lambda(args=ast.arguments(posonlyargs=[], args=[],
                                   kwonlyargs=[], kw_defaults=[], defaults=[]), body=item.value),
                               ast.parse(f"{role} == 'control'", mode='eval').body,
                               ast.Constant(kind), *[ast.Name(id=v, ctx=ast.Load()) for v in
                                                    ('d', 'inventory', 'count', option)]],
                         keywords=[])
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(recovery_inclusion), _control_pair=pairs)
    exec(compile(tree, '<external-control-reuse>', 'exec'), scope)
    return scope[kind], before


def controller(pairs):
    base = recovery_controller.recover_tracks
    scope = dict(base.__globals__)
    for kind in ('fit_shared', 'fit_new'):
        scope[kind], _ = transformed(kind, pairs)
    result = FunctionType(base.__code__, scope, base.__name__, base.__defaults__, base.__closure__)
    result.__kwdefaults__ = base.__kwdefaults__
    return result


def trial(prepared, reuse):
    pairs = ControlPairs(reuse)
    row = recovery_trial(prepared, controller(pairs))
    row['controls'] = pairs.rows
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    request = validate_request(json.loads(args.request.read_bytes()))
    if request['runtime'] != runtime_versions():
        raise ValueError('Frozen runtime changed')
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin three CPUs and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__)]
    paths += [Path('tools') / name for name in ('probe_algo07v3_native_recovery_queue.py',
              'probe_algo07v3_annotation_arms.py', 'check_algo07v3_scan_likelihood.py',
              'profile_algo07v3_training_queue.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    context, evidence, receipt = load_context(request)
    prepared = dict(recovery_context=context, inventory=evidence)
    sequence = ['candidate', 'baseline'] if args.reverse else ['baseline', 'candidate']
    plan = dict(bindings=bindings, scientific_receipt=receipt, sequence=sequence,
                cpus=sorted(os.sched_getaffinity(0)), blas_threads=1,
                context_loading_outside_timer=True, runtime_modified=False,
                production_modified=False, full_pipeline_speedup=None)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    rows, expected = [], None
    for index, side in enumerate(sequence):
        row = _ordered(lambda _, side=side: trial(prepared, side == 'candidate'),
                       [0], workers=1)[0]
        actual = {k: row[k] for k in ('result_signature', 'selection_signature',
                                      'stage_signatures', 'input_signature')}
        if expected is None:
            expected = actual
        row.update(index=index, side=side, exact=actual == expected)
        rows.append(row)
        (args.output / f'{index}-{side}.json').write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('side', 'seconds', 'cpu_seconds', 'exact',
                                            'controls')}), flush=True)
        if not row['exact']:
            raise ValueError('Full recovery checkpoint changed')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    reference = signature(saved['evidence']['audit']['predictive_recovery'])
    if saved['sha256'] != receipt or any(r['result_signature'] != reference for r in rows):
        raise ValueError('Saved native recovery audit changed')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound input/source changed during comparison')
    (args.output / 'result.json').write_text(json.dumps(dict(plan=plan, rows=rows,
         exact=True, saved_native_audit_exact=True), indent=2) + '\n')


if __name__ == '__main__':
    main()
