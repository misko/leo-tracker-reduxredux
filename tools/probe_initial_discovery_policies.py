"""Screen complete initial discovery policies on content-bound saved inputs.

Invoke in a fresh process with PYTHONPATH pointing at --source-root and tools.
This measures initial search only; endpoints are not GPS errors or worker speed.
"""

import argparse
import hashlib
import json
import os
import pickle
import resource
import time
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import differences, fingerprint
from initial_discovery_probe import load_saved, replay_initial, request_inputs, selected_branch

from leo.analysis.localization_v3.discovery import signature
from leo.analysis.localization_v3.initial_search import initial_search
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.analysis.localization_v5.initial_control import initial_control
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import source_bindings, stage_deadline

ARMS = ('c0', 'fitted_c')
POLICIES = {
    'legacy': {},
    'seed': dict(seed_policy='anchor-round-robin-v1', ranking_policy='legacy'),
    'ranking': dict(seed_policy='legacy', ranking_policy='warm-center-v1'),
    'combined': dict(seed_policy='anchor-round-robin-v1', ranking_policy='warm-center-v1'),
}
BUDGETS = dict(seed_budget=4, branch_budget=3, rounds=5, iterations=48)


def cpu():
    return [r.ru_utime + r.ru_stime for r in (
        resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN))]


def bound_sources(root):
    """Bind loaded runtime modules and require all to come from the requested freeze."""
    sources = source_bindings()
    if not sources or any(not Path(v['path']).resolve().is_relative_to(root)
                          for v in sources.values()):
        raise ValueError('Imported runtime differs from the bound source root')
    return sources


def native_equivalence(saved, actual):
    # Paths change in a freeze; all executable content and numerical options must match.
    keys = ('source_sha256', 'wrapper_sha256', 'binary_sha256', 'provider', 'flags',
            'original_sha256', 'ABI', 'sanitized')
    if any(saved[key] != actual[key] for key in keys):
        raise ValueError('Frozen native provider differs from the saved numerical provider')
    return dict(equal=True, compared_keys=list(keys), saved_manifest_sha256=canonical_digest(saved))


def owners(value):
    return [{key: row.get(key) for key in (
        'component', 'candidate_index', 'norad', 'compatible', 'association_source')}
        for row in value['all_graph_associations'].get('tracks', [])]


def metrics(result):
    branches = []
    for choice in result['choices']:
        branches.append(dict(hypothesis=choice['hypothesis'], signature=signature(choice['node']),
            center_score=choice['center_score'], arms={arm: dict(
                endpoint_east_north_km=value['fit']['parameters'], objective=value['fit']['score'],
                residual_rms_hz=value['fit']['residual_rms_hz'], graph_owners=owners(value),
                nominated_acceptance=value['metrics']) for arm, value in choice['arms'].items()}))
    return dict(selected_hypothesis=result['selected_hypothesis'], branches=branches,
                unique_RF_hypotheses=result['unique_RF_hypotheses'],
                fully_fitted_hypotheses=result['fully_fitted_hypotheses'])


def work_counts(result):
    fits = [dict(hypothesis=choice['hypothesis'], arm=arm, epoch=epoch['epoch'],
                 evaluations=epoch['fit']['evaluations'], stopped=epoch['fit']['stopped'])
            for choice in result['choices'] for arm in ARMS
            for epoch in choice['arms'][arm]['phase_rounds']]
    branches = min(result['unique_RF_hypotheses'], BUDGETS['branch_budget'])
    if len(result['choices']) != branches or len(fits) != branches * 2 * 5 or any(
            [e['epoch'] for e in choice['arms'][arm]['phase_rounds']] != list(range(5))
            for choice in result['choices'] for arm in ARMS):
        raise ValueError('Full branch-budget paired five-round initial search required')
    if any(fingerprint(result['zero_phase_control'][arm]) != fingerprint(
            selected_branch(result)['arms'][arm]['phase_rounds'][0]['fit']) for arm in ARMS):
        raise ValueError('Original v5 initial control reuse required')
    return dict(branch_arm_fits=branches * 2, optimizer_calls=len(fits),
                residual_evaluations=sum(r['evaluations'] for r in fits),
                additional_control_optimizer_calls=0, per_fit=fits)


def compare(reference, actual):
    before, after = selected_branch(reference), selected_branch(actual)
    same_signature = signature(before['node']) == signature(after['node'])
    arms = {}
    for arm in ARMS:
        old, new = before['arms'][arm], after['arms'][arm]
        arms[arm] = dict(
            endpoint_shift_km=float(np.linalg.norm(np.asarray(new['fit']['parameters'])
                                                   - old['fit']['parameters'])),
            objective_delta=new['fit']['score'] - old['fit']['score'],
            graph_owners_equal=fingerprint(owners(old)) == fingerprint(owners(new)),
            matched_nominated_rows_and_aliases=same_signature)
    # Policy audit fields describe the experiment and must not hide scientific equality.
    def strip(value):
        return {k: v for k, v in value.items()
                if k not in ('initial_discovery_policy', 'initial_discovery_ranking')}

    return dict(full_exact=fingerprint(reference) == fingerprint(actual),
                scientific_exact=fingerprint(strip(reference)) == fingerprint(strip(actual)),
                selected_signature_equal=same_signature, arms=arms,
                GPS_used=False, position_accuracy_evaluated=False, whole_worker_speedup=None)


def read_reference(path, plan):
    receipt = json.loads((path / 'result.json').read_bytes())
    raw = (path / 'initial.pickle').read_bytes()
    if (receipt['status'] != 'complete' or receipt['policy'] != 'legacy'
            or receipt.get('saved_initial_exact') is not True
            or hashlib.sha256(raw).hexdigest() != receipt['pickle_sha256']
            or any(receipt[key] != plan[key] for key in (
                'request_sha256', 'manifest_sha256', 'sources', 'tool_bindings', 'budgets'))):
        raise ValueError('Exact saved-initial legacy reference with matched bindings required')
    result = pickle.loads(raw)  # Trusted, hash-bound, locally produced probe output only.
    if fingerprint(result) != receipt['initial_sha256']:
        raise ValueError('Legacy reference content differs')
    return result


def native_counts(backend):
    receipts = backend.provenance()['receipts']
    return {key: sum(r['counts'][key] for r in receipts)
            for key in receipts[0]['counts']} if receipts else {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policy', choices=tuple(POLICIES), required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--timeout', type=int, choices=range(1, 601), default=600)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    if (args.policy == 'legacy') != (args.reference is None):
        parser.error('Candidates require a legacy reference; legacy has no reference')
    request, job, store = request_inputs(args.request)
    if (request.get('initial_control_policy') != 'winner-arm-phase0-fit-v1'
            or request.get('initial_discovery_policy') is not None):
        parser.error('Original v5 initial-control saved request without discovery policy required')
    manifest = validate_manifest(read_manifest(args.native_manifest))
    equivalence = native_equivalence(request['backend_manifest'], manifest)
    sources = bound_sources(args.source_root.resolve())
    tool_paths = (Path(__file__), Path(__file__).with_name('initial_discovery_probe.py'),
                  Path(__file__).with_name('census_algo07v5_initial_controls.py'),
                  args.request, args.native_manifest)
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in tool_paths}
    plan = dict(status='plan', policy=args.policy, policy_options=POLICIES[args.policy],
                source_root=str(args.source_root.resolve()),
                request_path=str(args.request.resolve()), request_sha256=canonical_digest(request),
                manifest_sha256=canonical_digest(manifest), native_equivalence=equivalence,
                identity=job['identity'], sources=sources, tool_bindings=bindings,
                budgets=BUDGETS, initial_control_policy=request['initial_control_policy'],
                timeout_s=args.timeout, affinity=sorted(os.sched_getaffinity(0)),
                BLAS_threads=os.environ.get('OPENBLAS_NUM_THREADS'),
                prior='previous', genuine_previous=False, GPS_used=False,
                scope='complete initial discovery only; original public saved preparation',
                position_accuracy_evaluated=False, whole_worker_speedup=None)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value,
                                             allow_nan=False) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began, began_cpu = time.perf_counter(), cpu()
    try:
        if sorted(os.sched_getaffinity(0)) != [20] or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin CPU20 and one BLAS thread for the bounded component screen')
        with stage_deadline(args.timeout):
            saved = load_saved(request, job, store)
            sources = bound_sources(args.source_root.resolve())
            # Loading public stores imports their contract modules. Bind those too.
            plan['sources'] = sources
            save('plan.json', plan)
            reference = read_reference(args.reference.resolve(), plan) if args.reference else None
            prepared = saved['evidence']['preparation']
            noise = (json.dumps(prepared['noise'], default=_json_value,
                                sort_keys=True, allow_nan=False) + '\n').encode()
            backend = ProcessBound(manifest, output / 'native-receipts')
            scan = _context(prepared, SearchRegion(tuple(job['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False, bound=backend)
            initial = saved['evidence']['audit']['initial']
            replay = replay_initial(scan, initial)
            before_counts = native_counts(backend)
            preparation_seconds = time.perf_counter() - began
            start, start_cpu = time.perf_counter(), cpu()
            result = initial_search(scan, scan.radio_sigma_hz, initial_control=initial_control,
                                    **BUDGETS, **POLICIES[args.policy])
            seconds, used = time.perf_counter() - start, np.subtract(cpu(), start_cpu).tolist()
            after_counts = native_counts(backend)
            work = work_counts(result)
            if (bound_sources(args.source_root.resolve()) != sources
                    or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest
                           for p, digest in bindings.items())):
                raise ValueError('Bound source or input changed during the screen')
        raw = pickle.dumps(result, protocol=5)
        (output / 'initial.pickle').write_bytes(raw)
        exact = fingerprint(initial) == fingerprint(result)
        row = dict(plan, status='complete',
                   saved_initial_exact=exact if args.policy == 'legacy' else None,
                   receipt_sha256=saved['sha256'], preparation_sha256=fingerprint(prepared),
                   saved_initial_sha256=fingerprint(initial), initial_sha256=fingerprint(result),
                   pickle_sha256=hashlib.sha256(raw).hexdigest(), context_replay=replay,
                   preparation_seconds=preparation_seconds, initial_seconds=seconds,
                   initial_cpu_seconds=used, cpu_order=['self', 'reaped_children'],
                   elapsed_seconds=time.perf_counter() - began,
                   elapsed_cpu_seconds=np.subtract(cpu(), began_cpu).tolist(),
                   work_counts=work, metrics=metrics(result), native_counts_total=after_counts,
                   native_counts_initial={k: value - before_counts.get(k, 0)
                                          for k, value in after_counts.items()},
                   comparison=compare(initial if reference is None else reference, result))
        save('result.json', row)
        if args.policy == 'legacy' and not exact:
            save('saved-initial-differences.json', differences(initial, result))
            raise ValueError('Legacy full initial search did not exactly reproduce saved initial')
    except BaseException as exc:
        save('failure.json', dict(status='failed', error_type=type(exc).__name__, error=str(exc),
                                  elapsed_seconds=time.perf_counter() - began))
        raise
    print(json.dumps(dict(status='complete', output=str(output), policy=args.policy,
                          saved_initial_exact=row['saved_initial_exact'], initial_seconds=seconds,
                          selected_signature_equal=row['comparison']['selected_signature_equal'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
