"""Serial two-shard parity/cost preflight; no optimization or reference ports."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def verify(plan, policy):
    if plan['policy'] != policy:
        raise ValueError('policy mismatch')
    if str(Path(sys.executable).absolute()) != plan['runtime']['interpreter']:
        raise ValueError('immutable interpreter path required')
    if any(os.environ.get(name) != '1' for name in
           ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('single-thread environment required')
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError('bound artifact changed: ' + name)
    for name, expected in plan['runtime']['sha256'].items():
        if sha(name) != expected:
            raise ValueError('runtime changed: ' + name)
    labels = [member['label'] for member in plan['members']]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError('exact twelve members required')


def fingerprint(model):
    """Hash explicit inference state, excluding private evaluation caches."""
    import dataclasses
    import numpy as np
    def value(item):
        if isinstance(item, np.ndarray):
            if item.dtype.hasobject:
                raise ValueError('object array cannot supply deterministic identity')
            return dict(shape=list(item.shape), dtype=item.dtype.str,
                        sha256=hashlib.sha256(np.ascontiguousarray(item).tobytes()).hexdigest())
        if isinstance(item, np.generic):
            return item.item()
        if dataclasses.is_dataclass(item):
            return {f.name: value(getattr(item, f.name)) for f in dataclasses.fields(item)}
        if isinstance(item, (tuple, list)):
            return [value(x) for x in item]
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        raise TypeError('unsupported inference identity: ' + type(item).__name__)
    def record(obj):
        if dataclasses.is_dataclass(obj):
            return value(obj)
        return {k: value(v) for k, v in vars(obj).items()
                if not k.startswith('_') and (isinstance(v, np.ndarray)
                   or v is None or isinstance(v, (str, int, float, bool, tuple, list)))}
    names = ('baseline', 'design', 'basis', 'clock_design', 'precision', 'nodes', 'null',
             'rf_time_design', 'satellite_basis', 'centers_s', 'delta_time')
    payload = dict(model={name: value(getattr(model, name)) for name in names},
                   observations=record(model.observations), bank=record(model.bank),
                   prior=value(model.prior), score=value(model.score))
    return dict(sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                fields=payload)


def dependencies(member):
    # This function is called only after full closure/runtime verification.
    folder = ROOT / 'reports/2026_10_09_position_error_iter116'
    sys.path.insert(0, str(folder))
    entry = module('entry116_for155', folder / 'entrypoint.py')
    environment = entry.make_loader(ROOT, member['binding'])
    clean = module('clean131_for155', ROOT / 'reports/2026_10_09_position_error_iter131/inference_loader.py')
    loader = clean.InferenceLoader(ROOT, environment.load_case)
    components = module('components132_for155', ROOT / 'reports/2026_10_10_position_error_iter132/audit.py').numerical_components()
    construct = module('construct137_for155', ROOT / 'reports/2026_10_10_position_error_iter137/parity.py').construct
    math_path = ROOT / 'reports/2026_10_10_position_error_iter152/math_core.py'
    if 'math_core' in sys.modules and Path(sys.modules['math_core'].__file__).resolve() != math_path:
        raise ValueError('ambient math_core collision')
    sys.modules['math_core'] = module('math_core', math_path)
    conditional = module('conditional152_for155', math_path.with_name('conditional.py')).ConditionalModes
    from leo.analysis.hard60_bounded_fit import _Problem
    from reconstruction import reconstruct
    from preflight import check, evidence
    return dict(loader=loader, construct=construct, components=components,
                conditional=conditional, problem=_Problem, reconstruct=reconstruct,
                check=check, evidence=evidence)


def evaluate_member(member, *, dependency_factory=dependencies, clock=time.monotonic):
    begun = clock()
    result = dict(label=member['label'], status='failed', arms={}, matched_model=None)
    try:
        path = ROOT / member['selected_path']
        if sha(path) != member['selected_sha256']:
            raise ValueError('original selected receipt changed')
        receipt = json.loads(path.read_text())
        if (receipt.get('label') != member['label'] or receipt.get('branch') != 'native'
                or receipt.get('protocol_sha256') != member['selected_protocol_digest']):
            raise ValueError('foreign original control/native receipt')
        ports = dependency_factory(member)
        case = ports['loader'](member['binding'])
        result['input_reconstruction_elapsed_s'] = clock() - begun
        identities = {}
        for arm in ('fitted-c', 'zero-c'):
            start = clock()
            try:
                endpoint = ports['reconstruct'](case, receipt, arm, construct=ports['construct'],
                    components=ports['components'], problem_type=ports['problem'])
                model = endpoint['model']
                model_identity = fingerprint(model)
                identity = dict(model=model_identity, local_center=endpoint['local_center'].tolist(),
                                input_binding=member['binding']['expected_input_binding'])
                identities[arm] = identity
                reconstruct_elapsed = clock() - start
                diagnostic = ports['check'](model, endpoint['vector'], endpoint['clock'], arm=arm,
                    stored_objective=endpoint['saved_objective'],
                    stored_joint_objective=endpoint['saved_joint_objective'],
                    conditional_factory=ports['conditional'], feasible=endpoint['feasible'],
                    anchor_audit=endpoint['anchor_audit'], fingerprint=lambda: fingerprint(model))
                result['arms'][arm] = dict(status=diagnostic['status'], diagnostic=diagnostic,
                    reconstruction_elapsed_s=reconstruct_elapsed, model_identity=identity,
                    seed_stage=endpoint['seed_stage'], helper_projection_delta=ports['evidence'](endpoint['helper_projection_delta']))
            except Exception as error:
                result['arms'][arm] = dict(status='failed', error=repr(error), reconstruction_elapsed_s=clock()-start)
        result['matched_model'] = len(identities) == 2 and identities['fitted-c'] == identities['zero-c']
        result['status'] = 'complete' if all(r['status'] == 'passed' for r in result['arms'].values()) else 'failed'
    except Exception as error:
        result['error'] = repr(error)
        result['input_reconstruction_elapsed_s'] = clock() - begun
        for arm in ('fitted-c', 'zero-c'):
            result['arms'].setdefault(arm, dict(status='failed', error='input-reconstruction-failed'))
    result['elapsed_s'] = clock() - begun
    return result


def run_member(member, directory, digest, *, evaluate=evaluate_member):
    folder = Path(directory); folder.mkdir(parents=True, exist_ok=True)
    result_path, claim_path = folder / (member['label']+'.json'), folder / (member['label']+'.claim.json')
    if result_path.exists():
        row = json.loads(result_path.read_text())
        if row.get('protocol_sha256') != digest or row.get('label') != member['label'] or row.get('status') not in ('complete','failed'):
            raise ValueError('foreign or nonterminal result')
        return row
    with claim_path.open('x') as stream:
        json.dump(dict(label=member['label'], protocol_sha256=digest), stream)
    row = dict(evaluate(member), protocol_sha256=digest)
    with result_path.open('x') as stream:
        json.dump(row, stream, indent=2, allow_nan=False)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('shard', type=int, choices=(0,1))
    parser.add_argument('--protocol', type=Path, default=HERE/'protocol.json')
    parser.add_argument('--output', type=Path, default=HERE/'results')
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    from freeze import POLICY
    verify(plan, POLICY)
    from leo.contracts.digests import canonical_digest
    digest = canonical_digest(plan)
    for member in plan['members'][args.shard::2]:
        row = run_member(member, args.output, digest)
        print(member['label'], row['status'], flush=True)


if __name__ == '__main__':
    main()
