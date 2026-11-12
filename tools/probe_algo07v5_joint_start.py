"""Capture an exact predictive recovery, then screen factorized-to-joint starts.

The warm screen runs only the two joint fits and their full original audits.
It is not a worker, numerical-recovery, GPS or population qualification.
"""

import argparse
import ast
import hashlib
import inspect
import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import differences, fingerprint
from evaluate_algo07 import source_binding
from probe_algo07v5_annotation_rounds import clone, cpu, load_context, request_inputs

from leo.analysis.localization_v3 import joint_recovery, recovery_controller
from leo.analysis.localization_v3.joint_fits import DeferredJointFits
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline
from leo.operations.localization_v3_parallel import (
    map_annotation_training,
    map_grid_batches,
    map_initial_arms,
    map_predictive_folds,
)

CHECKOUT = Path(__file__).resolve().parents[1]
ARMS = ('c0', 'fitted_c')


def initialized_fit(function):
    source = inspect.getsource(function)
    tree = ast.parse(source)
    definition, = tree.body
    candidates = [node for node in definition.body if isinstance(node, ast.Assign)
                  and ast.unparse(node) == 'x = np.zeros(2)']
    if len(candidates) != 1 or definition.args.kwonlyargs or definition.args.kwarg:
        raise ValueError('Exactly one original position initialization required')
    if sum(isinstance(n, ast.For) and ast.unparse(n.iter) == 'range(5)'
           for n in ast.walk(tree)) != 1:
        raise ValueError('All five original phase rounds required')
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == 'numerics.minimize']
    if len(calls) != 1:
        raise ValueError('Exactly one original position optimizer call required')
    options = next(k.value for k in calls[0].keywords if k.arg == 'options')
    values = {k.arg: ast.literal_eval(k.value) for k in options.keywords}
    cap = 'maxfun' if function.__name__ == '_fit_lbfgsb' else 'maxfev'
    if values.get('maxiter') != 48 or values.get(cap) != 240:
        raise ValueError('Original 48-iteration and 240-call ceilings required')
    definition.args.kwonlyargs.append(ast.arg(arg='start'))
    definition.args.kw_defaults.append(None)
    candidates[0].value = ast.parse('np.array(start, dtype=float, copy=True)', mode='eval').body
    ast.fix_missing_locations(tree)
    namespace = dict(function.__globals__)
    exec(compile(tree, '<explicit-joint-start>', 'exec'), namespace)
    return namespace[definition.name], source, ast.unparse(tree)


def elapsed(operation):
    began, used = time.perf_counter(), sum(cpu())
    value = operation()
    return value, dict(wall_seconds=time.perf_counter() - began,
                       cpu_seconds=sum(cpu()) - used)


def trial_summary(trial, audit):
    result = trial['result']
    history = result['history']
    if len(history) != 5:
        raise ValueError('A complete fit must retain all five phase rounds')
    return dict(protocol=trial['protocol'],
                endpoint_east_north_km=result['endpoint_east_north_km'],
                objective=result['negative_twice_elbo'],
                optimizer_nfev=sum(row['nfev'] for row in history),
                final_optimizer_success=history[-1]['success'],
                unsuccessful_rounds=sum(not row['success'] for row in history),
                history=history, RF_qualified_arm=audit['RF_qualified_arm'],
                audit_checks=audit['checks'],
                incumbent_owner_changes=audit['incumbent_owner_changes'],
                phase_check=audit['phase_check'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('capture', 'warm'), required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 301), default=300)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if (args.mode == 'warm') != (args.reference is not None):
        parser.error('Warm mode alone requires a complete capture reference')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    if request.get('backend_manifest') != manifest:
        raise ValueError('The saved request must bind the same native manifest')
    root = CHECKOUT / 'src'
    modules = source_binding(root)
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (args.request, args.native_manifest, Path(__file__),
                          CHECKOUT / 'tools/probe_algo07v5_annotation_rounds.py',
                          CHECKOUT / 'tools/census_algo07v5_initial_controls.py',
                          CHECKOUT / 'tools/evaluate_algo07.py')}
    transformed = {name: initialized_fit(getattr(joint_recovery, name))
                   for name in ('_fit_lbfgsb', '_fit_powell')}
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value) + '\n')

    plan = dict(status='plan', mode=args.mode, timeout_seconds=args.timeout,
                modules=modules, bindings=bindings, request_sha256=canonical_digest(request),
                manifest_sha256=canonical_digest(manifest), GPS_used=False,
                scope=('complete original predictive recovery capture' if args.mode == 'capture'
                       else 'joint fit/audit pair only; no worker or numerical replay claim'),
                initialization='same-arm factorized endpoint; original zero phase reference',
                unchanged_budgets=dict(phase_rounds=5, maxiter=48, maxfun_or_maxfev=240),
                whole_worker_speedup=None)
    save('plan.json', plan)
    save('transformation.json', {name: dict(original=source, changed=changed)
                                 for name, (_, source, changed) in transformed.items()})
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        raise ValueError('Exactly three CPUs and single-thread BLAS required')
    stages, captured, warm_trials, warm_audits = [], {}, {}, {}
    try:
        with stage_deadline(args.timeout):
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            save('scientific-binding.json', scientific)
            if args.mode == 'capture':
                from leo.analysis.localization_v5.annotation_fallback import fit
                from leo.operations.localization_v5_controls import ControlCacheFactory

                if fit.policy != request.get('annotation_training_policy'):
                    raise ValueError('Capture requires the current full fallback annotation policy')
                factory = ControlCacheFactory(backend, request['inclusion_control_policy'])

                def stage(name, operation):
                    value, timing = elapsed(operation)
                    stages.append(dict(name=name, **timing))
                    if name == 'joint-probe' or name.startswith(
                            ('control-', 'factorized-', 'joint-', 'retry-control-',
                             'retry-factorized-', 'retry-joint-')):
                        captured[name] = value
                        raw = pickle.dumps(captured, protocol=5)
                        (output / 'captured.pickle').write_bytes(raw)
                    save('stages.json', stages)
                    return True, value

                result, total = elapsed(lambda: recovery_controller.recover_tracks(
                    context, evidence, run_stage=stage, discovery_allowed=lambda: True,
                    map_annotation_folds=map_predictive_folds,
                    map_annotation_training=map_annotation_training,
                    map_inclusion_arms=map_initial_arms, map_joint_batches=map_grid_batches,
                    map_joint_arms=map_initial_arms, annotation_training_fit=fit,
                    inclusion_control_factory=factory))
                saved = store(job['output_root']).load(job['identity']['run_id'])
                issues = differences(saved['evidence']['audit']['predictive_recovery'], result)
                save('differences.json', issues)
                save('recovery.json', result)
                if issues or result.get('failure'):
                    raise ValueError('Capture must reproduce the complete original recovery audit')
                required = {'joint-probe'} | {m + '-' + a + suffix
                    for m in ('control', 'factorized', 'joint') for a in ARMS
                    for suffix in ('', '-audit')}
                if not required <= captured.keys():
                    raise ValueError('Complete original joint experiment required')
                raw = (output / 'captured.pickle').read_bytes()
                summary = dict(status='complete', complete_recovery_exact=True, **total,
                               captured_sha256=hashlib.sha256(raw).hexdigest(),
                               control_work=factory.provenance(),
                               baseline={a: trial_summary(captured['joint-' + a],
                                                         captured['joint-' + a + '-audit'])
                                         for a in ARMS})
            else:
                reference = args.reference.resolve()
                reference_plan = json.loads((reference / 'plan.json').read_bytes())
                reference_result = json.loads((reference / 'result.json').read_bytes())
                reference_scientific = json.loads(
                    (reference / 'scientific-binding.json').read_bytes())
                raw = (reference / 'captured.pickle').read_bytes()
                if (reference_result['status'] != 'complete'
                        or not reference_result['complete_recovery_exact']
                        or hashlib.sha256(raw).hexdigest() != reference_result['captured_sha256']
                        or any(reference_plan[k] != plan[k] for k in
                               ('modules', 'bindings', 'request_sha256', 'manifest_sha256'))
                        or fingerprint(reference_scientific) != fingerprint(scientific)):
                    raise ValueError('Complete, unchanged, scientifically matched capture required')
                captured = pickle.loads(raw)
                probe = captured['joint-probe']
                starts = {a: np.asarray(captured['factorized-' + a]['result']
                                        ['endpoint_east_north_km'], float) for a in ARMS}
                if any(x.shape != (2,) or not np.isfinite(x).all()
                       or np.max(abs(x)) > 12.5 for x in starts.values()):
                    raise ValueError('Finite in-bounds same-arm factorized endpoints required')

                def fit(context, probe, arm, method, *, optimizer):
                    if method != 'joint' or optimizer != 'lbfgsb':
                        raise ValueError('This screen covers the original first joint attempt only')
                    lb = transformed['_fit_lbfgsb'][0]

                    def initialized(d, targets, arm, method, step):
                        return lb(d, targets, arm, method, step, start=starts[arm])

                    operation = clone(joint_recovery.fit_joint, _fit_lbfgsb=initialized)
                    value = operation(context, probe, arm, method, optimizer=optimizer)
                    value['protocol']['start_east_north_km'] = starts[arm].tolist()
                    value['protocol']['initialization_policy'] = 'same-arm-factorized-endpoint'
                    return value

                fits = DeferredJointFits(context, probe, 'joint', 'lbfgsb', fit, map_initial_arms)
                for arm in ARMS:
                    warm_trials[arm], timing = elapsed(lambda arm=arm: fits.fit(arm))
                    stages.append(dict(name='joint-' + arm, **timing))
                    warm_audits[arm], timing = elapsed(lambda arm=arm: joint_recovery.audit_joint(
                        context, dict(evidence['inventory'],
                                      publication_support=evidence['publication_support']),
                        warm_trials[arm],
                        captured['control-' + arm + '-audit'], map_batches=map_grid_batches))
                    stages.append(dict(name='joint-' + arm + '-audit', **timing))
                    save('stages.json', stages)
                save('warm-trials.json', warm_trials)
                save('warm-audits.json', warm_audits)
                summary = dict(status='complete', reference=str(reference),
                               baseline=reference_result['baseline'],
                               candidate={a: trial_summary(warm_trials[a], warm_audits[a])
                                          for a in ARMS},
                               full_controller_selection_evaluated=False,
                               numerical_recovery_evaluated=False, GPS_used=False,
                               whole_worker_speedup=None)
        if source_binding(root) != modules or any(
                hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
                for path, digest in bindings.items()):
            raise ValueError('Bound source or inputs changed during the experiment')
        save('result.json', summary)
        print(json.dumps(dict(status='complete', output=str(output))), flush=True)
    except BaseException as error:
        save('stages.json', stages)
        save('warm-trials.json', warm_trials)
        save('warm-audits.json', warm_audits)
        save('result.json', dict(status='failed', error=type(error).__name__,
                                 message=str(error), whole_worker_speedup=None))
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
