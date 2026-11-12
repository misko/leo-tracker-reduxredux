"""Bounded complete-annotation experiment with explicit numerical approximations.

Default invocation only writes a plan. Pickles are trusted local probe outputs.
This experiment neither evaluates GPS nor establishes a whole-worker speedup.
"""

import argparse
import ast
import hashlib
import inspect
import json
import os
import pickle
import resource
import time
import types
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import differences, fingerprint
from scipy.optimize import least_squares, minimize

from leo.analysis.localization_v3 import prediction, predictive_annotation
from leo.analysis.localization_v3.recovery_inventory import recovery_context
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import runtime_versions, source_bindings, stage_deadline
from leo.operations.localization_v3_parallel import map_predictive_folds

ORIGINAL_SHA256 = 'bcf7da0df353d071f45ce64068e815707410c883489fba9d0c538e15fe1258d4'


def optimizer_policy(optimizer):
    shared = dict(objective='problem.residual(x) @ problem.residual(x)',
                  bounds='problem.lower/upper', start='clip(supplied start, lower, upper)',
                  original_gn_iterations=48, derivative_step_km=.001,
                  original_gn_worst_case_residual_calls=625,
                  final_metadata_calculate_calls=1,
                  evaluation_count='all physical residual calls including Jacobians')
    if optimizer == 'gn':
        return dict(shared, optimizer='gn', jacobian='clipped central residual differences',
                    max_damped_trials=9, initial_damping=.01,
                    minimum_damping=1e-7, damping_accept_divisor=3,
                    damping_reject_multiplier=5, normal_diagonal_floor=1e-6,
                    acceptance_improvement=1e-9, small_step_km=1e-4,
                    small_improvement=1e-5, history_kind='initial and accepted iterates')
    if optimizer == 'lbfgsb':
        return dict(shared, optimizer=optimizer, method='L-BFGS-B',
                    jacobian='SciPy forward objective differences, bound adjusted',
                    options=dict(maxiter=48, maxfun=625, eps=.001,
                                 ftol=2.220446049250313e-9, gtol=1e-5, maxls=20, maxcor=10),
                    residual_call_cap=625,
                    history_kind='all residual evaluations including Jacobians')
    if optimizer == 'trf':
        return dict(shared, optimizer=optimizer, method='trf',
                    jacobian='clipped central residual differences',
                    options=dict(max_nfev=625, ftol=1e-8, xtol=1e-8, gtol=1e-8,
                                 x_scale=1., loss='linear', f_scale=1., tr_solver='exact'),
                    residual_call_cap=625,
                    history_kind='all residual evaluations including Jacobians')
    raise ValueError('Declared gn, lbfgsb or trf optimizer required')


def alternative_fit(optimizer):
    policy = optimizer_policy(optimizer)
    if optimizer == 'gn':
        raise ValueError('Alternative optimizer required')

    def fit(problem, start=(0., 0.), iterations=48):
        if iterations != 48:
            raise ValueError('Original 48 position steps required')
        x, lo, hi = (np.asarray(v, float) for v in (start, problem.lower, problem.upper))
        if (x.shape != (2,) or lo.shape != x.shape or hi.shape != x.shape
                or not np.isfinite([x, lo, hi]).all() or np.any(lo >= hi)):
            raise ValueError('Finite two-dimensional start and ordered bounds required')
        x = np.clip(x, lo, hi)
        history = []

        class Budget(Exception):
            pass

        def residual(at):
            if len(history) >= policy['residual_call_cap']:
                raise Budget('physical residual call cap reached')
            value = np.asarray(problem.residual(at), float)
            score = float(value @ value)
            if not np.isfinite(score):
                raise ValueError('Finite residual objective required')
            history.append(dict(parameters=np.asarray(at).copy(), score=score))
            return value

        def objective(at):
            value = residual(at)
            return float(value @ value)

        def jacobian(at):
            columns = []
            for k in range(len(at)):
                a, b = at.copy(), at.copy()
                a[k], b[k] = max(lo[k], at[k] - .001), min(hi[k], at[k] + .001)
                columns.append((residual(b) - residual(a)) / (b[k] - a[k]))
            return np.array(columns).T

        try:
            if optimizer == 'lbfgsb':
                result = minimize(objective, x, method='L-BFGS-B',
                                  bounds=list(zip(lo, hi, strict=True)),
                                  options=policy['options'])
                score = float(result.fun)
            else:
                result = least_squares(residual, x, jac=jacobian, bounds=(lo, hi),
                                       method='trf', **policy['options'])
                score = float(result.fun @ result.fun)
            x = np.asarray(result.x).copy()
            stopped = f'scipy_status_{result.status}: {result.message}'
            scipy_result = dict(nfev=int(result.nfev), njev=int(result.njev),
                                nit=int(result.nit) if 'nit' in result else None,
                                success=bool(result.success), status=int(result.status),
                                message=str(result.message))
            solution_origin = 'scipy_result'
            budget_exhausted = bool((optimizer == 'lbfgsb' and (
                result.nit >= policy['options']['maxiter']
                or result.nfev >= policy['options']['maxfun']))
                or (optimizer == 'trf' and result.nfev >= policy['options']['max_nfev']))
        except Budget as exc:
            best = min(history, key=lambda row: row['score'])
            x, score = best['parameters'].copy(), best['score']
            stopped, scipy_result = str(exc), None
            solution_origin = 'lowest evaluated score after physical call cap'
            budget_exhausted = True
        calculated = problem.calculate(x)
        return dict(parameters=x, score=score, history=history, evaluations=len(history),
                    stopped=stopped, optimizer_policy=policy,
                    history_kind=policy['history_kind'], scipy_result=scipy_result,
                    budget_exhausted=budget_exhausted,
                    converged=bool(scipy_result and scipy_result['success']
                                   and not budget_exhausted),
                    solution_origin=solution_origin, final_metadata_calculate_calls=1,
                    residual_rms_hz=float(np.sqrt(np.mean(
                        calculated['conditional_residual_hz'][problem.keep] ** 2))),
                    active_points=int(problem.keep.sum()),
                    normalization_constant=calculated['normalization_constant'],
                    negative_twice_elbo=calculated['negative_twice_elbo'])
    return fit


def transform(rounds, source=None, scope=None, expected_sha256=ORIGINAL_SHA256):
    source = inspect.getsource(prediction.fit_training) if source is None else source
    if hashlib.sha256(source.encode()).hexdigest() != expected_sha256:
        raise ValueError('Original fit_training source changed; review the experiment')
    tree = ast.parse(source)
    outer = [n for n in tree.body[0].body if isinstance(n, ast.For)
             and ast.unparse(n.target) == '_epoch' and ast.unparse(n.iter) == 'range(5)']
    all_ranges = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and ast.unparse(n) == 'range(5)']
    if rounds not in (1, 2, 3, 5) or len(outer) != 1 or len(all_ranges) != 1:
        raise ValueError('Exactly one outer five-round phase loop is required')
    outer[0].iter.args[0] = ast.Constant(rounds)
    ast.fix_missing_locations(tree)
    namespace = dict(vars(prediction) if scope is None else scope)
    exec(compile(tree, '<annotation-phase-rounds>', 'exec'), namespace)
    return namespace[tree.body[0].name], source, ast.unparse(tree)


def clone(function, **globals_override):
    result = types.FunctionType(function.__code__, dict(function.__globals__, **globals_override),
                                function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def annotation_operation(rounds, receipts=None, optimizer='gn'):
    policy = optimizer_policy(optimizer)
    if optimizer != 'gn' and rounds != 5:
        raise ValueError('Alternative optimizers require all five phase rounds')
    training, original, changed = transform(rounds)
    fit = prediction.fit if optimizer == 'gn' else alternative_fit(optimizer)
    training.__globals__['fit'] = fit
    if receipts is not None:
        records, current = [], [None]
        def counted_fit(*args, **kwargs):
            if kwargs.get('iterations') != 48:
                raise ValueError('Original 48 position steps required')
            current[0]['optimizer_calls_started'] += 1
            result = fit(*args, **kwargs)
            current[0]['optimizers'].append(dict(evaluations=result['evaluations'],
                stopped=result['stopped'], final_metadata_calculate_calls=1,
                scipy_result=result.get('scipy_result'),
                budget_exhausted=(result['stopped'] == 'iteration_budget'
                                  if optimizer == 'gn' else result['budget_exhausted']),
                converged=result.get('converged'),
                solution_origin=result.get('solution_origin'), history_kind=policy['history_kind']))
            return result
        training.__globals__['fit'] = counted_fit
        def counted_training(d, node, keep, arm):
            row = dict(arm=arm, optimizer_policy=policy, phase_rounds=rounds,
                       approximation=rounds != 5 or optimizer != 'gn',
                       optimizer_calls_started=0, optimizers=[], completed=False)
            records.append(row)
            current[0] = row
            try:
                result = training(d, node, keep, arm)
                row.update(completed=True, completed_rounds=len(result[2]['history']))
                return result
            finally:
                (receipts / f'{os.getpid()}.json').write_text(json.dumps(records) + '\n')
        training_callable = counted_training
    else:
        training_callable = training
    fold = clone(predictive_annotation.annotate_fold, fit_training=training_callable)
    return clone(predictive_annotation.annotate, annotate_fold=fold), original, changed


def request_inputs(path):
    from leo.operations import localization_v3_job, localization_v4_job, localization_v5_job
    from leo.storage.localization_v3 import LocalizationV3Store
    from leo.storage.localization_v4 import LocalizationV4Store
    from leo.storage.localization_v5 import LocalizationV5Store

    request = json.loads(path.read_bytes())
    if not isinstance(request, dict) or not request:
        raise ValueError('A complete stored request is required')
    handlers = {'algo07v4-native-v1': (localization_v4_job, LocalizationV4Store),
                'algo07v5-native-v1': (localization_v5_job, LocalizationV5Store)}
    if 'job' in request:
        if request.get('algorithm') not in handlers:
            raise ValueError('Unsupported stored native request algorithm')
        validator, store = handlers[request['algorithm']]
        validator.validate_request(request)
        job = request['job']
    else:
        localization_v3_job.validate_request(request)
        job, store = request, LocalizationV3Store
    if job['runtime'] != runtime_versions():
        raise ValueError('Match the frozen numerical runtime')
    return request, job, store


def load_context(request, job, store, backend):
    saved = store(job['output_root']).load(job['identity']['run_id'])
    evidence, receipt = saved['evidence'], saved['receipt']
    if (evidence['provenance']['request_sha256'] != canonical_digest(request)
            or evidence['provenance']['configuration']['request'] != job
            or evidence['identity'] != job['identity']
            or any(receipt[k] != v for k, v in job['identity'].items())
            or saved['sha256'] != canonical_digest(receipt)):
        raise ValueError('Saved evidence/request/receipt binding mismatch')
    prepared = evidence['preparation']
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False) + '\n').encode()
    scan = _context(prepared, SearchRegion(tuple(job['search_center'])),
                    hashlib.sha256(noise).hexdigest(), genuine=True, bound=backend)
    context = recovery_context(scan, evidence['audit']['cavity_policy'])
    inventory = evidence['audit']['recovery_inventory']
    binding = dict(receipt_sha256=saved['sha256'],
                   context_sha256=fingerprint((prepared, evidence['audit']['cavity_policy'])),
                   replay_objective_deltas=context['replay'])
    return context, inventory, binding


def metrics(annotation):
    rows = []
    for fold in annotation['result']['folds']:
        for proposal in fold['proposals']:
            for arm in prediction.ARMS:
                value = proposal['arms'][arm]
                score = value['scores']['conditional_target']
                rows.append(dict(seed=fold['seed'], candidate_index=proposal['candidate_index'],
                    norad=proposal['norad'], alias=proposal['alias'], arm=arm,
                    training_objective=value['training_objective'],
                    negative_twice_log_density=score['negative_twice_log_density'],
                    rms_hz=score['rms_hz'], elevation_deg=value['minimum_target_elevation_deg'],
                    final_phase_change_s=value['final_phase_change_s'],
                    training_rounds=len(value['history']),
                    history_sha256=fingerprint(value['history'])))
    return dict(consensus=annotation['result']['annotation'], proposals=rows,
                nominees={str(k): [dict(candidate_index=o['candidate_index'], arm=o['arm'])
                                  for o in v['selected']]
                          for k, v in annotation['nominations'].items()})


def compare(reference, actual):
    return dict(exact=fingerprint(reference) == fingerprint(actual),
                differences=differences(reference, actual),
                reference=metrics(reference), actual=metrics(actual),
                inclusion_decisions_evaluated=False)


def cpu():
    return [resource.getrusage(w).ru_utime + resource.getrusage(w).ru_stime
            for w in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)]


def work_counts(output, mode):
    records = {p.stem: json.loads(p.read_bytes()) for p in
               sorted((output / 'training-receipts').glob('*.json'))}
    rows = [r for values in records.values() for r in values]
    convergences = [f['converged'] for r in rows for f in r['optimizers']]
    counts = dict(training_calls_started=len(rows),
                  training_calls_completed=sum(r['completed'] for r in rows),
                  completed_rounds=sum(r.get('completed_rounds', 0) for r in rows),
                  optimizer_calls_started=sum(r['optimizer_calls_started'] for r in rows),
                  optimizer_evaluations=sum(f['evaluations'] for r in rows
                                            for f in r['optimizers']),
                  optimizer_final_metadata_calculations=sum(
                      f['final_metadata_calculate_calls'] for r in rows for f in r['optimizers']),
                  optimizer_budget_exhaustions=sum(
                      f['budget_exhausted'] is True for r in rows for f in r['optimizers']),
                  optimizer_reported_convergences=(None if any(v is None for v in convergences)
                                                  else sum(convergences)))
    if mode == 'oracle':
        counts = dict.fromkeys(counts)
    return dict(counts, per_pid=records,
                unavailable_reason='untouched oracle is not instrumented'
                    if mode == 'oracle' else None)


def read_reference(path):
    receipt = json.loads((path / 'result.json').read_bytes())
    raw = (path / 'annotation.pickle').read_bytes()
    if (receipt['status'] != 'complete'
            or hashlib.sha256(raw).hexdigest() != receipt['pickle_sha256']):
        raise ValueError('Complete content-bound probe reference required')
    result = pickle.loads(raw)
    if fingerprint(result) != receipt['annotation_sha256']:
        raise ValueError('Reference annotation fingerprint differs')
    return receipt, result


def qualify_reference(receipt, plan):
    if (any(receipt[k] != plan[k] for k in
            ('request_sha256', 'target', 'manifest_sha256', 'modules', 'bindings'))
            or receipt.get('rounds') != 5 or receipt.get('optimizer') != 'gn'
            or receipt.get('optimizer_policy') != optimizer_policy('gn')):
        raise ValueError('Reference differs or lacks full5 oracle proof')
    if plan['optimizer'] == 'gn' and plan['rounds'] == 5:
        qualified = receipt['mode'] == 'oracle'
    else:
        qualified = receipt['mode'] == 'clone' and receipt.get('full5_oracle_exact')
    if not qualified:
        raise ValueError('Reference differs or lacks full5 oracle proof')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--target', type=int, required=True)
    parser.add_argument('--rounds', type=int, choices=(1, 2, 3, 5), required=True)
    parser.add_argument('--mode', choices=('oracle', 'clone'), default='clone')
    parser.add_argument('--optimizer', choices=('gn', 'lbfgsb', 'trf'), default='gn')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 121), default=120)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01') or output.exists() or args.target < 0:
        parser.error('Fresh local output and nonnegative target index required')
    if args.mode == 'oracle' and (args.rounds != 5 or args.reference is not None
                                  or args.optimizer != 'gn'):
        parser.error('Untouched oracle requires GN, five rounds and no reference')
    if args.optimizer != 'gn' and args.rounds != 5:
        parser.error('Alternative optimizers require all five phase rounds')
    if args.run and args.mode == 'clone' and args.reference is None:
        parser.error('Run GN clone5 against oracle, then alternatives against qualified GN clone5')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    if 'backend_manifest' in request and request['backend_manifest'] != manifest:
        parser.error('Explicit manifest differs from stored request')
    operation, original, changed = annotation_operation(args.rounds, optimizer=args.optimizer)
    paths = [args.request, args.native_manifest, Path(__file__),
             Path(__file__).with_name('census_algo07v5_initial_controls.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    modules = source_bindings()
    plan = dict(status='plan', mode=args.mode, optimizer=args.optimizer,
                optimizer_policy=optimizer_policy(args.optimizer),
                rounds=args.rounds, target=args.target,
                timeout_s=args.timeout, request_sha256=canonical_digest(request), bindings=bindings,
                modules=modules, manifest_sha256=canonical_digest(manifest),
                approximation=args.rounds != 5 or args.optimizer != 'gn',
                approximation_policy=dict(phase_round_cut=args.rounds != 5,
                                          optimizer_replacement=args.optimizer != 'gn'),
                work_budget_semantics=(
                    'GN uses 48 iterations with at most 625 residual calls in 2D; '
                    'alternatives use a hard 625 physical residual-call cap including Jacobians. '
                    'L-BFGS-B also has maxiter=48/maxfun=625; TRF max_nfev=625 excludes '
                    'Jacobian calls and is not a GN iteration budget. '
                    'Cap exhaustion is not convergence.'),
                calibration_policy=('same observations, candidates, priors, rounds '
                                    'and optimizer budgets for both arms'),
                position_steps=48, folds=3, candidates=12,
                phase_step_s=.1, map_training=None, GPS_used=False,
                scope='complete single-target annotation; original nomination and mixture',
                whole_worker_speedup=None, accuracy_qualification=False)
    output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value) + '\n')
    save('plan.json', plan)
    (output / 'original.txt').write_text(original)
    (output / 'candidate.txt').write_text(changed)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), inference_rerun=False)))
        return 0
    began, used = time.perf_counter(), cpu()
    try:
        if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin three CPUs and one BLAS thread')
        reference = reference_receipt = None
        if args.reference:
            reference_receipt, reference = read_reference(args.reference.resolve())
            qualify_reference(reference_receipt, plan)
        with stage_deadline(args.timeout):
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            if reference_receipt is not None and reference_receipt['scientific'] != scientific:
                raise ValueError('Reference reconstructed a different saved scientific context')
            target = evidence['selected_targets'][args.target]
            inventory = dict(evidence['inventory'],
                             publication_support=evidence['publication_support'])
            (output / 'training-receipts').mkdir()
            if args.mode == 'clone':
                operation, _, _ = annotation_operation(args.rounds, output / 'training-receipts',
                                                       optimizer=args.optimizer)
            prepared_seconds = time.perf_counter() - began
            fit_began, fit_cpu = time.perf_counter(), cpu()
            annotation = (predictive_annotation.annotate if args.mode == 'oracle' else operation)(
                context, inventory, target['track_id'],
                inactive_fragment=target['inactive_fragment'],
                candidates=12, folds=3, phase_step=.1, shifted_origin=True,
                map_folds=map_predictive_folds, map_training=None)
            annotation_seconds = time.perf_counter() - fit_began
            annotation_cpu = np.subtract(cpu(), fit_cpu).tolist()
            annotation['protocol']['phase_rounds'] = args.rounds
        provenance = backend.provenance()
        raw = pickle.dumps(annotation, protocol=5)
        (output / 'annotation.pickle').write_bytes(raw)
        assessment = compare(reference, annotation) if reference is not None else None
        if assessment is not None:
            save('comparison.json', assessment)
        final_modules = source_bindings()
        if (any(final_modules.get(k) != v for k, v in modules.items())
                or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha
                       for p, sha in bindings.items())):
            raise ValueError('Bound source/input changed during experiment')
        row = dict(plan, status='complete', scientific=scientific, target_record=target,
                   annotation_seconds=annotation_seconds, annotation_cpu_seconds=annotation_cpu,
                   preparation_seconds=prepared_seconds, total_seconds=time.perf_counter() - began,
                   total_cpu_seconds=np.subtract(cpu(), used).tolist(),
                   native_activation=provenance,
                   annotation_sha256=fingerprint(annotation),
                   pickle_sha256=hashlib.sha256(raw).hexdigest(), metrics=metrics(annotation),
                   work_counts=work_counts(output, args.mode),
                   reference=str(args.reference.resolve()) if args.reference else None,
                   full5_oracle_exact=bool(args.optimizer == 'gn' and args.rounds == 5
                                           and assessment and assessment['exact']),
                   exact=assessment['exact'] if assessment else None)
        if (args.optimizer == 'gn' and args.rounds == 5
                and assessment is not None and not assessment['exact']):
            raise ValueError('Entire clone5 annotation differs from untouched oracle')
        save('result.json', row)
    except BaseException as exc:
        save('failure.json', dict(status='failed', error=type(exc).__name__, message=str(exc),
                                 seconds=time.perf_counter() - began,
                                 cpu_seconds=np.subtract(cpu(), used).tolist()))
        raise
    print(json.dumps(dict(status='complete', output=str(output),
                          annotation_seconds=annotation_seconds, exact=row['exact'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
