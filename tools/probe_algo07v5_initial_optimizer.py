"""Plan a bounded complete initial-search optimizer comparison.

Run oracle GN, then qualify cloned GN against it, then compare L-BFGS-B.
Pickles are trusted local probe outputs. Endpoint shifts are not GPS errors.
"""

import argparse
import hashlib
import inspect
import json
import os
import pickle
import time
import types
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import differences, fingerprint
from evaluate_algo07 import source_binding
from probe_algo07v5_annotation_rounds import cpu, optimizer_policy, request_inputs

from leo.analysis.localization_v3 import initial_search as initial
from leo.analysis.localization_v3 import position
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.analysis.localization_v5.annotation_training import fit as annotation_fit
from leo.analysis.localization_v5.initial_control import initial_control
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline
from leo.operations.localization_v3_parallel import map_initial_branches

ARMS = ('c0', 'fitted_c')
SOURCE_HASHES = {
    'position.fit': '2dbc8e0042f1062d1c07b15f4d959c65b80fbdb4ebca311f077fb4df6b6948dd',
    'position.refreshed': 'd7ebcccbba363fd40ab03fb0c87d2316f8751f209a5ed5d017e4a86f7dac55da',
    'initial.fit_initial_arm': '2e3d36ddbd9c434bfcec39758c19f00ab2872be95a1a46a84ca844f94ba69272',
    'initial.initial_search': 'f547dd28e38f1cc06d55033d40abcd3599d203207a8644c5783392f48c89b10f',
    'initial_control': 'b6231ff97dac3f066bb8b7b25b7c9f3592b848cba167bc8ef4dc5b37bdb2125f',
    'annotation_fit': '428c0eeb0d2baea756fd70e326a6ab421343a0c94f8a26d6d6fa10e54b66d74b',
    'map_initial_branches': 'c25ed49d51712b3bbff25e65082459208e1d8974546896139bffba2a7798bd0d',
}


def guarded_sources():
    functions = dict(zip(SOURCE_HASHES, (
        position.fit, position.refreshed, initial.fit_initial_arm, initial.initial_search,
        initial_control, annotation_fit, map_initial_branches), strict=True))
    source_root = Path(__file__).resolve().parents[1] / 'src'
    if any(not Path(inspect.getsourcefile(function)).resolve().is_relative_to(source_root)
           for function in functions.values()):
        raise ValueError('Imported runtime differs from the bound source root')
    sources = {name: inspect.getsource(function) for name, function in functions.items()}
    if any(hashlib.sha256(source.encode()).hexdigest() != SOURCE_HASHES[name]
           for name, source in sources.items()):
        raise ValueError('Frozen initial-search source changed; review this probe')
    return sources


def private_clone(function, **overrides):
    if not overrides.keys() <= function.__globals__.keys():
        raise ValueError('Only existing global names may be replaced')
    namespace = dict(function.__globals__, **overrides)
    result = types.FunctionType(function.__code__, namespace, function.__name__,
                                function.__defaults__, function.__closure__)
    result.__kwdefaults__ = (None if function.__kwdefaults__ is None
                             else dict(function.__kwdefaults__))
    changed = {key for key in namespace if namespace[key] is not function.__globals__[key]}
    if not changed <= overrides.keys() or result.__code__ is not function.__code__:
        raise ValueError('Clone changed more than the declared global bindings')
    return result


def initial_operation(optimizer):
    fit = {'gn': position.fit, 'lbfgsb': annotation_fit}[optimizer]
    refreshed = private_clone(position.refreshed, fit=fit)
    arm = private_clone(initial.fit_initial_arm, refreshed=refreshed)
    return private_clone(initial.initial_search, fit_initial_arm=arm, fit=fit)


def load_scan(request, job, store, backend):
    saved = store(job['output_root']).load(job['identity']['run_id'])
    evidence, receipt = saved['evidence'], saved['receipt']
    if (evidence['provenance']['request_sha256'] != canonical_digest(request)
            or evidence['provenance']['configuration']['request'] != job
            or evidence['identity'] != job['identity']
            or any(receipt[k] != value for k, value in job['identity'].items())
            or saved['sha256'] != canonical_digest(receipt)):
        raise ValueError('Saved evidence/request/receipt binding mismatch')
    prepared = evidence['preparation']
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False) + '\n').encode()
    noise_sha256 = hashlib.sha256(noise).hexdigest()
    region = SearchRegion(tuple(job['search_center']))
    scan = _context(prepared, region, noise_sha256, genuine=True, bound=backend)
    scientific = dict(receipt_sha256=saved['sha256'], preparation_sha256=fingerprint(prepared),
                      noise_sha256=noise_sha256, search_center=job['search_center'],
                      context='original genuine initial scan; no recovery transformation')
    return scan, scientific


def metrics(result):
    branches = []
    for choice in result['choices']:
        arms = {}
        for arm in ARMS:
            value = choice['arms'][arm]
            accepted = [r for r in value['metrics']['tracks'] if r['compatible']]
            arms[arm] = dict(endpoint_east_north_km=value['fit']['parameters'],
                objective=value['fit']['score'], residual_rms_hz=value['fit']['residual_rms_hz'],
                nomination_and_acceptance=value['metrics'],
                all_graph_associations=value['all_graph_associations'],
                accepted_nominated_owners=sorted({r['candidate_index'] for r in accepted}),
                accepted_nominated_components=[r['component'] for r in accepted])
        branches.append(dict(hypothesis=choice['hypothesis'], center_score=choice['center_score'],
                             nominated_rows=choice['node']['seed']['rows'],
                             nominated_aliases=choice['node']['aliases'], arms=arms))
    return dict(selected_hypothesis=result['selected_hypothesis'], branches=branches,
                unique_RF_hypotheses=result['unique_RF_hypotheses'],
                fully_fitted_hypotheses=result['fully_fitted_hypotheses'],
                zero_phase_control={arm: dict(endpoint_east_north_km=value['parameters'],
                                             objective=value['score'])
                                    for arm, value in result['zero_phase_control'].items()})


def work_counts(result):
    fits = [dict(hypothesis=choice['hypothesis'], arm=arm, epoch=epoch['epoch'],
                 evaluations=epoch['fit']['evaluations'], stopped=epoch['fit']['stopped'],
                 budget_exhausted=epoch['fit'].get('budget_exhausted',
                     epoch['fit']['stopped'] == 'iteration_budget'),
                 converged=epoch['fit'].get('converged'),
                 stationarity=epoch['fit'].get('stationarity'),
                 scipy_result=epoch['fit'].get('scipy_result'))
            for choice in result['choices'] for arm in ARMS
            for epoch in choice['arms'][arm]['phase_rounds']]
    if any(len(choice['arms'][arm]['phase_rounds']) != 5
           for choice in result['choices'] for arm in ARMS):
        raise ValueError('Every complete initial arm must retain five rounds')
    return dict(branch_arm_fits=len(result['choices']) * 2, optimizer_calls=len(fits),
                residual_evaluations=sum(row['evaluations'] for row in fits),
                optimizer_final_metadata_calculations=len(fits),
                budget_exhaustions=sum(row['budget_exhausted'] for row in fits),
                reported_convergences=(sum(row['converged'] for row in fits)
                    if all(row['converged'] is not None for row in fits) else None),
                stationarity_satisfied=sum(row['stationarity'] is not None
                    and row['stationarity']['satisfied'] is True for row in fits),
                stationarity_available=sum(row['stationarity'] is not None for row in fits),
                reused_controls=2, additional_control_optimizer_calls=0,
                discovery_and_acceptance_evaluations='included in timing; not instrumented',
                per_fit=fits)


def read_reference(path):
    receipt = json.loads((path / 'result.json').read_bytes())
    raw = (path / 'initial.pickle').read_bytes()
    if (receipt['status'] != 'complete'
            or hashlib.sha256(raw).hexdigest() != receipt['pickle_sha256']):
        raise ValueError('Complete content-bound initial-search reference required')
    result = pickle.loads(raw)
    if fingerprint(result) != receipt['initial_sha256']:
        raise ValueError('Reference initial-search fingerprint differs')
    return receipt, result


def qualify_reference(receipt, plan):
    keys = ('request_sha256', 'manifest_sha256', 'modules', 'bindings', 'source_hashes')
    if (receipt['status'] != 'complete' or receipt['optimizer'] != 'gn'
            or receipt.get('optimizer_policy') != optimizer_policy('gn')
            or any(receipt[key] != plan[key] for key in keys)):
        raise ValueError('Complete GN reference with the same source and inputs required')
    if plan['optimizer'] == 'gn':
        qualified = receipt['mode'] == 'oracle'
    else:
        qualified = (receipt['mode'] == 'clone' and receipt.get('oracle_exact') is True
                     and bool(receipt.get('oracle_initial_sha256')))
    if not qualified:
        raise ValueError('Run cloned GN against untouched oracle before optimizer comparison')


def compare(reference, actual):
    def decisions(result):
        nominations, acceptance, owners = [], [], []
        for choice in result['choices']:
            branch = choice['hypothesis']
            nominations.append((branch, choice['node']['seed']['rows'], choice['node']['aliases']))
            for arm in ARMS:
                value = choice['arms'][arm]
                acceptance.append((branch, arm, [
                    {key: row.get(key) for key in (
                        'component', 'candidate_index', 'norad', 'compatible')}
                    for row in value['metrics']['tracks']]))
                owners.append((branch, arm, [
                    {key: row.get(key) for key in (
                        'component', 'candidate_index', 'norad', 'association_source')}
                    for row in value['all_graph_associations'].get('tracks', [])]))
        return nominations, acceptance, owners

    left, right = decisions(reference), decisions(actual)
    return dict(exact=fingerprint(reference) == fingerprint(actual),
                differences=differences(reference, actual),
                branch_winner_equal=(reference['selected_hypothesis']
                                     == actual['selected_hypothesis']),
                nomination_equal=fingerprint(left[0]) == fingerprint(right[0]),
                nominated_acceptance_equal=fingerprint(left[1]) == fingerprint(right[1]),
                graph_owners_equal=fingerprint(left[2]) == fingerprint(right[2]),
                reference=metrics(reference), actual=metrics(actual),
                GPS_used=False, position_accuracy_evaluated=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--mode', choices=('oracle', 'clone'), default='clone')
    parser.add_argument('--optimizer', choices=('gn', 'lbfgsb'), default='gn')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 121), default=120)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01') or output.exists():
        parser.error('Fresh local output required')
    if args.mode == 'oracle' and (args.optimizer != 'gn' or args.reference is not None):
        parser.error('Untouched oracle requires GN and no reference')
    if args.run and args.mode == 'clone' and args.reference is None:
        parser.error('Clone execution requires the qualified preceding reference')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    if 'backend_manifest' in request and request['backend_manifest'] != manifest:
        parser.error('Manifest differs from the saved request')
    sources = guarded_sources()
    operation = (initial.initial_search if args.mode == 'oracle'
                 else initial_operation(args.optimizer))
    paths = [args.request, args.native_manifest, Path(__file__),
             Path(__file__).with_name('probe_algo07v5_annotation_rounds.py'),
             Path(__file__).with_name('census_algo07v5_initial_controls.py'),
             Path(__file__).with_name('evaluate_algo07.py')]
    bindings = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths}
    source_root = Path(__file__).resolve().parents[1] / 'src'
    modules = source_binding(source_root)
    plan = dict(status='plan', mode=args.mode, optimizer=args.optimizer,
                optimizer_policy=optimizer_policy(args.optimizer), source_hashes=SOURCE_HASHES,
                request_sha256=canonical_digest(request),
                manifest_sha256=canonical_digest(manifest),
                modules=modules, bindings=bindings, timeout_s=args.timeout,
                seed_budget=4, branch_budget=3, phase_rounds=5, position_steps=48,
                candidates='all original discovery candidates', workers=3, BLAS_threads=1,
                calibration_policy=(
                    'matched c0/fitted_c observations, candidates, priors and budgets'),
                initial_control_policy='v5 selected first complete zero-start zero-reference fit',
                clone_policy=dict(mechanism='FunctionType; unchanged code/defaults/closure',
                    refreshed_globals=['fit'], arm_globals=['refreshed'],
                    initial_globals=['fit_initial_arm', 'fit']),
                candidate_fit_policy=annotation_fit.policy,
                GPS_used=False, accuracy_qualification=False, whole_worker_speedup=None,
                scope='complete initial search, including nomination and acceptance',
                omitted_work=['input preparation before saved request', 'all later worker stages'])
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value) + '\n')

    save('plan.json', plan)
    save('original-sources.json', sources)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began, began_cpu = time.perf_counter(), cpu()
    try:
        if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin exactly three CPUs and one BLAS thread')
        reference = reference_receipt = None
        with stage_deadline(args.timeout):
            if args.reference:
                reference_receipt, reference = read_reference(args.reference.resolve())
                qualify_reference(reference_receipt, plan)
            backend = ProcessBound(manifest, output / 'native-receipts')
            scan, scientific = load_scan(request, job, store, backend)
            if reference_receipt is not None and reference_receipt['scientific'] != scientific:
                raise ValueError('Reference reconstructed a different original initial context')
            prepared_seconds = time.perf_counter() - began
            prepared_cpu = np.subtract(cpu(), began_cpu).tolist()
            callbacks = []
            fit_began, fit_cpu = time.perf_counter(), cpu()
            result = operation(scan, scan.radio_sigma_hz,
                               map_branches=map_initial_branches, initial_control=initial_control,
                               on_branch=lambda choice: callbacks.append(choice['hypothesis']))
            seconds, used = time.perf_counter() - fit_began, np.subtract(cpu(), fit_cpu).tolist()
        raw = pickle.dumps(result, protocol=5)
        (output / 'initial.pickle').write_bytes(raw)
        row = dict(plan, status='complete', scientific=scientific,
                   preparation_seconds=prepared_seconds, preparation_cpu_seconds=prepared_cpu,
                   initial_seconds=seconds, initial_cpu_seconds=used,
                   cpu_order=['self', 'reaped_children'], callback_order=callbacks,
                   initial_sha256=fingerprint(result),
                   pickle_sha256=hashlib.sha256(raw).hexdigest(),
                   metrics=metrics(result), work_counts=work_counts(result),
                   native_activation=backend.provenance())
        if reference is not None:
            assessment = compare(reference, result)
            save('comparison.json', assessment)
            row.update(reference_initial_sha256=reference_receipt['initial_sha256'],
                       reference_result_sha256=hashlib.sha256(
                           (args.reference / 'result.json').read_bytes()).hexdigest(),
                       exact=assessment['exact'],
                       scientific_gate={key: assessment[key] for key in (
                           'branch_winner_equal', 'nomination_equal',
                           'nominated_acceptance_equal', 'graph_owners_equal')})
            if args.optimizer == 'gn':
                if not assessment['exact']:
                    raise ValueError('Cloned GN differs from the untouched initial-search oracle')
                row.update(oracle_exact=True,
                           oracle_initial_sha256=reference_receipt['initial_sha256'])
        if (source_binding(source_root) != modules or any(
                hashlib.sha256(Path(path).read_bytes()).hexdigest() != value
                for path, value in bindings.items())):
            raise ValueError('Bound source/input changed during experiment')
        save('result.json', row)
    except BaseException as exc:
        save('failure.json', dict(status='failed', error=type(exc).__name__, message=str(exc),
                                 seconds=time.perf_counter() - began,
                                 cpu_seconds=np.subtract(cpu(), began_cpu).tolist()))
        raise
    print(json.dumps(dict(status='complete', output=str(output), initial_seconds=seconds,
                          initial_cpu_seconds=sum(used), exact=row.get('exact'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
