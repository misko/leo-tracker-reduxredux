"""Plan or run one independently validated timing-gap recovery research trial.

direct-timing-gap-v1 omits the original parent annotation and rejected-fit
prerequisites. Branch identity and all paired physical gates remain mandatory.
No publication changes. Local pickle outputs are trusted research artifacts.
"""

import argparse
import hashlib
import json
import os
import pickle
import resource
import time
from pathlib import Path

from census_algo07v5_initial_controls import fingerprint
from initial_discovery_probe import load_saved
from probe_algo07v5_annotation_rounds import load_context, request_inputs

from leo.analysis.localization_v3.gap_fragments import prepare_gap
from leo.analysis.localization_v3.gap_recovery import annotate_gap, audit_gap, fit_gap
from leo.analysis.localization_v3.recovery_acceptance import shared_family_route
from leo.analysis.localization_v3.recovery_partitions import require_distinct_annotation
from leo.analysis.localization_v4.backend import ProcessBound, validate_manifest
from leo.application.localization_v3_engine import _json_value
from leo.contracts.fast_graph_position_v4 import qualify
from leo.operations.localization_v3_job import source_bindings, stage_deadline

POLICY = 'direct-timing-gap-v1'
ARMS = ('c0', 'fitted_c')


def timing_candidates(context, evidence, observations):
    inventory = evidence['inventory']
    grouped = {arm: {r['track_id']: r for r in inventory['tracks'] if r['arm'] == arm}
               for arm in ARMS}
    occupied = set().union(*(set(evidence['owners'][arm]) for arm in ARMS))
    result = []
    for tid, target in grouped['c0'].items():
        other = grouped['fitted_c'].get(tid)
        if other is None or not all(r['current_large'] for r in (target, other)):
            continue
        ids = set(target['observation_ids'])
        if (ids != set(other['observation_ids'])
                or ids != set(target['all_track_observation_ids']) or ids & occupied):
            continue
        source = prepare_gap(context, inventory, observations, tid)
        for branch in source['branches']:
            if len(branch['observation_ids']) == len(ids):
                continue
            result.append(dict(track_id=tid, component=target['component'],
                               branch_id=branch['branch_id'], points=len(branch['observation_ids']),
                               parent_points=len(ids), start_s=float(branch['times_s'][0]),
                               end_s=float(branch['times_s'][-1])))
    return sorted(result, key=lambda r: (-r['points'], r['track_id'], r['branch_id']))


def supported_shared_identity(annotation):
    result = annotation['result']
    require_distinct_annotation(result, annotation['protocol'])
    identity = result['annotation']
    return (identity['status'] == 'conditionally_supported_identity'
            and shared_family_route(result['folds'], identity['norad']))


def acceptance(trial, audit, evidence, observations, annotation):
    protocol = trial['protocol']
    required = dict(matched_c_arms=True, phase_rounds=5, steps=48,
                    target_calibrates_receiver=False,
                    target_updates_unobserved_satellite_parameters=False,
                    original_noise_weights_and_priors=True, conditional_satellite_refresh=True)
    if any(protocol.get(key) != value for key, value in required.items()):
        raise ValueError('Original paired conditional gap fitting protocol required')
    expected = set(annotation['protocol']['target']['observation_ids'])
    identity = annotation['result']['annotation']['norad']
    targets = protocol['targets']
    if (len(targets) != 1 or set(targets[0]['observation_ids']) != expected
            or targets[0]['norad'] != identity):
        raise ValueError('Trial must retain the independently annotated whole gap component')
    target = trial['target_0']
    result = qualify(target, audit, evidence['owners'],
                     {o['observation_id'] for o in observations})
    if result['qualified']:
        for arm in ARMS:
            proposed = target['arms'][arm]['proposed_owners']
            additions = set(proposed) - set(evidence['owners'][arm])
            if additions != expected or any(proposed.get(oid) != identity for oid in expected):
                raise ValueError('Qualified trial must add exactly the annotated native component')
    return result


def runtime_bindings(root):
    bindings = source_bindings()
    if any(not Path(v['path']).resolve().is_relative_to(root / 'src')
           for v in bindings.values()):
        raise ValueError('All loaded leo modules must come from the declared frozen runtime')
    return bindings


def matched_jobs(job, reference):
    keys = ('native_input', 'track_config', 'runtime', 'scan_identities',
            'search_center', 'screen_center', 'tle_root')
    if (job['identity']['input_sha256'] != reference['identity']['input_sha256']
            or any(job[key] != reference[key] for key in keys)):
        raise ValueError('Matched input, configuration, region and causal catalogue required')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--reference-request', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 121), default=110)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    request, job, store = request_inputs(args.request)
    reference_request, reference_job, reference_store = request_inputs(args.reference_request)
    matched_jobs(job, reference_job)
    modules = runtime_bindings(args.runtime_root.resolve())
    files = [Path(__file__), args.request, args.reference_request,
             Path(__file__).with_name('initial_discovery_probe.py'),
             Path(__file__).with_name('census_algo07v5_initial_controls.py'),
             Path(__file__).with_name('probe_algo07v5_annotation_rounds.py')]
    bindings = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in files}
    plan = dict(policy=POLICY, status='plan', maximum_components=1, timeout_s=args.timeout,
                request_path=str(args.request.resolve()),
                reference_request_path=str(args.reference_request.resolve()),
                modules=modules, bindings=bindings,
                selection='wholly unowned matched large tracks; proper time-gap components; '
                          'descending points then parent and branch IDs',
                gap_s=5, minimum_points=12, minimum_span_s=10,
                skipped_original_prerequisites=['parent independent identity',
                                                 'parent shared-family inclusion rejection'],
                independent_branch_identity_required=True, original_eligibility_equivalence=False,
                matched_c_arms=True, frozen_physical_fit_and_audit_budgets=True,
                prior='genuine_previous', GPS_used=False, published_result_changed=False)
    output.mkdir(parents=True)

    def save(name, value):
        (output / name).write_text(json.dumps(
            value, indent=2, default=_json_value, allow_nan=False) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began = time.perf_counter()
    cpu_began = resource.getrusage(resource.RUSAGE_SELF)
    stages, raw = [], {}

    def stage(name, operation):
        start, before = time.perf_counter(), resource.getrusage(resource.RUSAGE_SELF)
        status = 'failed'
        try:
            value = operation()
            status = 'complete'
        finally:
            after = resource.getrusage(resource.RUSAGE_SELF)
            stages.append(dict(name=name, status=status, seconds=time.perf_counter() - start,
                               cpu_seconds=(after.ru_utime + after.ru_stime
                                            - before.ru_utime - before.ru_stime)))
            save('stages.json', stages)
        if name != 'context':
            raw[name] = value
        return value

    try:
        if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin exactly one CPU and one BLAS thread')
        with stage_deadline(args.timeout):
            backend = ProcessBound(validate_manifest(request['backend_manifest']),
                                   output / 'native-receipts')
            context, evidence, scientific = stage(
                'context', lambda: load_context(request, job, store, backend))
            if not {'inventory', 'owners', 'publication_support'} <= set(evidence):
                raise ValueError('Complete saved recovery inventory wrapper required')
            runtime_bindings(args.runtime_root.resolve())
            saved = load_saved(request, job, store)
            observations = saved['evidence']['preparation']['tracks']['observations']
            reference = load_saved(reference_request, reference_job, reference_store)
            if (fingerprint(saved['evidence']['preparation'])
                    != fingerprint(reference['evidence']['preparation'])):
                raise ValueError('Matched saved scientific preparation required')
            inventory = evidence['inventory']
            before = fingerprint((context['scan'].tracks, inventory, observations))
            candidates = timing_candidates(context, evidence, observations)
            save('timing-candidates.json', candidates)
            result = dict(policy=POLICY, status='complete', scientific=scientific,
                          selected_component=candidates[0] if candidates else None,
                          independent_branch_identity_required=True, GPS_used=False,
                          published_result_changed=False, original_eligibility_equivalence=False)
            if candidates:
                selected = candidates[0]
                source = prepare_gap(context, inventory, observations, selected['track_id'])
                annotation, annotation_receipt = stage('annotation', lambda: annotate_gap(
                    context, inventory, source, selected['branch_id'], observations))
                result['identity'] = annotation['result']['annotation']
                if supported_shared_identity(annotation):
                    trial, fit_receipt = stage('inclusion', lambda: fit_gap(
                        context, inventory, annotation, observations))
                    audit, audit_receipt = stage('audit', lambda: audit_gap(
                        context, inventory, annotation, trial, observations))
                    result['qualification'] = acceptance(
                        trial, audit, evidence, observations, annotation)
                    result['numerical_receipts'] = dict(annotation=annotation_receipt,
                                                        inclusion=fit_receipt, audit=audit_receipt)
                    target = trial['target_0']
                    original = reference['evidence']['audit']['gap_recovery']
                    result['reference_comparison'] = dict(
                        receipt_sha256=reference['sha256'],
                        same_selected_branch=(original['selected'] is not None
                                              and original['selected']['branch_id']
                                              == selected['branch_id']),
                        same_identity=(original['selected'] is not None
                                       and original['selected']['identity']['norad']
                                       == result['identity']['norad']),
                        arms={arm: dict(
                            proposed_endpoint_latlon=target['arms'][arm]['endpoint_latlon'],
                            original_endpoint_latlon=original['candidate']['trial']['arms'][arm][
                                'endpoint_latlon'] if original['candidate'] else None,
                            added_points=target['arms'][arm]['added_points'],
                            frequency_score=target['arms'][arm]['negative_twice_elbo'],
                            owners_sha256=fingerprint(target['arms'][arm]['proposed_owners']))
                              for arm in ARMS})
                else:
                    result['qualification'] = dict(qualified=False,
                                                    reasons=['independent shared identity failed'])
            if before != fingerprint((context['scan'].tracks, inventory, observations)):
                raise ValueError('Trial mutated original graph, inventory or observations')
            final_modules = runtime_bindings(args.runtime_root.resolve())
            for entry in list(modules.values()) + list(final_modules.values()) + [
                    dict(path=p, sha256=d) for p, d in bindings.items()]:
                if hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() != entry['sha256']:
                    raise ValueError('Probe source or input changed')
            after = resource.getrusage(resource.RUSAGE_SELF)
            result.update(stages=stages, final_modules=final_modules,
                          elapsed_seconds=time.perf_counter() - began,
                          cpu_seconds=after.ru_utime + after.ru_stime
                          - cpu_began.ru_utime - cpu_began.ru_stime,
                          original_graph_inventory_observations_unchanged=True)
            (output / 'trial.pickle').write_bytes(pickle.dumps(raw, protocol=5))
            save('result.json', result)
    except BaseException as exc:
        (output / 'partial-trial.pickle').write_bytes(pickle.dumps(raw, protocol=5))
        save('failure.json', dict(status='failed', error_type=type(exc).__name__, error=str(exc),
                                  stages=stages, elapsed_seconds=time.perf_counter() - began))
        raise
    print(json.dumps(dict(status='complete', output=str(output),
                          qualified=result.get('qualification', {}).get('qualified', False),
                          published_result_changed=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
