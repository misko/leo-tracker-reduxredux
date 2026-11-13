"""Bounded inclusion and exact audit of a saved independent weak-track annotation.

Default invocation writes a provenance plan only. Execution never publishes a
position or changes the saved recording. Pickles are trusted local evidence.
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
from probe_algo07v5_annotation_rounds import load_context, request_inputs
from probe_initial_discovery_policies import bound_sources, native_counts, native_equivalence

from leo.analysis.localization_v3.recovery_acceptance import (
    numerical_only,
    shared_family_route,
    single_candidate,
)
from leo.analysis.localization_v3.recovery_inclusion import audit_inclusion, fit_new, fit_shared
from leo.analysis.localization_v3.recovery_partitions import require_distinct_annotation
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline
from leo.operations.localization_v5_controls import ControlCacheFactory

ARMS = ('c0', 'fitted_c')
POLICY = 'weak-track-validated-inclusion-audit-v1'


def read_validation(path):
    """Bind the previous raw validation, not a reconstructed or nominated identity."""
    root = path.resolve()
    receipt_path, raw_path = root / 'result.json', root / 'annotation.pickle'
    receipt_bytes, raw = receipt_path.read_bytes(), raw_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if (receipt.get('status') != 'complete'
            or receipt.get('policy') != 'weak-track-genuine-previous-independent-annotation-v1'
            or receipt.get('annotation_pickle_sha256') != hashlib.sha256(raw).hexdigest()
            or receipt.get('original_context_unchanged') is not True
            or receipt.get('position_inclusion_authorized') is not False
            or receipt.get('checkpoint_context_replay') != {'c0': 0., 'fitted_c': 0.}
            or receipt.get('actual_causal_bank_candidates') != 1420):
        raise ValueError('Complete bound independent validation required')
    annotation = pickle.loads(raw)
    if (fingerprint(annotation) != receipt['annotation_sha256']
            or annotation['result']['annotation'] != receipt['identity_consensus']):
        raise ValueError('Raw annotation differs from validated receipt')
    vote = identity_consensus(annotation['result']['folds'], score_name='conditional_target')
    require_distinct_annotation(annotation['result'], annotation['protocol'])
    if (vote != receipt['identity_consensus']
            or vote['status'] != 'conditionally_supported_identity'
            or vote['norad'] != 68106
            or annotation['protocol']['target_used_for_calibration']
            or annotation['protocol']['GPS_used']
            or annotation['protocol']['future_TLE']
            or annotation['protocol']['phase_rounds'] != 5
            or annotation['protocol']['position_steps'] != 48):
        raise ValueError('Original independent three-fold identity required')
    return receipt, annotation, dict(result_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
                                     annotation_pickle_sha256=hashlib.sha256(raw).hexdigest())


def match_checkpoint(context, evidence, scientific, receipt, annotation, request):
    """The validated physical target and genuine-previous incumbent must replay."""
    if (receipt['request_sha256'] != canonical_digest(request)
            or receipt['scientific'] != scientific
            or receipt['checkpoint_context_replay'] != context['replay']
            or receipt['causal_bank_sha256'] != fingerprint(context['scan'].sky)
            or receipt['actual_causal_bank_candidates'] != len(context['scan'].norads)
            or receipt['orbit_prior'] != 'genuine_previous'
            or receipt['original_training_policy'] != request['annotation_training_policy']
            or annotation['protocol'].get('training_optimizer_policy')
            != request['annotation_training_policy']):
        raise ValueError('Validated annotation belongs to another scientific checkpoint')
    target = annotation['protocol']['target']
    i = target['track_index']
    track = context['scan'].tracks[i]
    ids = set(track['observation_ids'])
    selected = receipt['selected_radio_target']
    if (target['track_id'] != receipt['checkpoint_record']['track_id']
            or target['component'] != selected['component']
            or i != selected['track_index']
            or len(ids) != len(track['observation_ids'])
            or ids != set(target['observation_ids'])
            or ids != set(receipt['checkpoint_record']['observation_ids'])
            or len(ids) != 33):
        raise ValueError('Validated whole physical weak target differs')
    records = {arm: [row for row in evidence['inventory']['tracks']
                     if row['arm'] == arm and row['track_id'] == target['track_id']]
               for arm in ARMS}
    if any(len(records[arm]) != 1 for arm in ARMS):
        raise ValueError('Matched target inventory absent')
    for arm in ARMS:
        row = records[arm][0]
        if (row['track_index'] != i or not row['current_large']
                or set(row['observation_ids']) != ids
                or set(row['all_track_observation_ids']) != ids
                or ids & set(evidence['publication_support'][arm]['owners'])):
            raise ValueError('Validated target is no longer whole and unowned')
    return dict(evidence['inventory'], publication_support=evidence['publication_support']), ids


def exact_qualified_target(candidate, inventory, target_ids, norad):
    """Check every published incumbent and exactly the independently scored target."""
    if candidate is None:
        return dict(qualified=False, reason='production_single_candidate_rejected')
    targets = candidate['targets']
    if (len(targets) != 1 or set(targets[0]['observation_ids']) != target_ids
            or targets[0]['norad'] != norad or candidate['kind'] not in
            ('shared_family', 'new_family')):
        raise ValueError('Selected target differs from independent annotation')
    per_arm = {}
    for arm in ARMS:
        old = inventory['publication_support'][arm]['owners']
        pair = candidate['arms'][arm]
        owners = pair['owners']
        expected = set(old) | target_ids
        if (set(owners) != expected or set(pair['associated_ids']) != expected
                or pair['added_points'] != len(target_ids)
                or any(owners.get(oid) != owner for oid, owner in old.items())
                or any(owners.get(oid) != norad for oid in target_ids)):
            raise ValueError('Qualified candidate changes incumbent or target ownership')
        per_arm[arm] = dict(endpoint_east_north_km=pair['endpoint_east_north_km'],
                            endpoint_latlon=pair['endpoint_latlon'],
                            negative_twice_elbo=pair['negative_twice_elbo'],
                            published_incumbent_points=len(old), added_points=len(target_ids),
                            owners_sha256=fingerprint(owners))
    if candidate['arms']['c0']['owners'] != candidate['arms']['fitted_c']['owners']:
        raise ValueError('Qualified c-arm ownership differs')
    return dict(qualified=True, kind=candidate['kind'], arms=per_arm)


def arm_metrics(trial, audit, shared):
    """Describe both candidate and control fits, even when scientific gates reject."""
    role = 'target_0' if shared else 'new_family'
    rows = {(r['role'], r['arm']): r for r in audit['rows']}
    return {name: dict(paired_valid=trial[name]['paired_valid'], arms={arm: dict(
        endpoint_east_north_km=trial[name]['arms'][arm]['endpoint_east_north_km'],
        endpoint_latlon=trial[name]['arms'][arm]['endpoint_latlon'],
        negative_twice_elbo=trial[name]['arms'][arm]['negative_twice_elbo'],
        incumbent_objective=trial[name]['arms'][arm].get('incumbent_objective'),
        target_negative_twice_log_density=(
            trial[name]['arms'][arm].get('family') or {}).get('negative_twice_log_density'),
        residual_rms_hz=trial[name]['arms'][arm]['RMS_hz'],
        added_points=trial[name]['arms'][arm]['added_points'],
        lost_points=trial[name]['arms'][arm]['lost_points'],
        final_phase_change_s=trial[name]['arms'][arm]['final_phase_change_s'],
        audit_verified=rows[(name, arm)]['verified'],
        audited_owners_sha256=fingerprint(rows[(name, arm)]['owners'])
        if 'owners' in rows[(name, arm)] else None)
        for arm in ARMS}) for name in ('control', role)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 111), default=110)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    request, job, store = request_inputs(args.request)
    if job.get('evaluation_reference') is not None:
        parser.error('Inference request must omit evaluation reference')
    manifest = validate_manifest(read_manifest(args.native_manifest))
    equivalence = native_equivalence(request['backend_manifest'], manifest)
    root = args.source_root.resolve()
    modules = bound_sources(root)
    validation = args.validation.resolve()
    paths = [Path(__file__), args.request, args.native_manifest,
             validation / 'result.json', validation / 'annotation.pickle',
             *(Path(__file__).with_name(name) for name in (
                 'probe_algo07v5_annotation_rounds.py',
                 'probe_initial_discovery_policies.py',
                 'census_algo07v5_initial_controls.py'))]
    bindings = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths}
    plan = dict(status='plan', policy=POLICY, request_path=str(args.request.resolve()),
                request_sha256=canonical_digest(request), identity=job['identity'],
                validation_path=str(validation), validation_result_sha256=bindings[str(
                    validation / 'result.json')], annotation_pickle_sha256=bindings[str(
                    validation / 'annotation.pickle')], source_root=str(root),
                modules=modules, bindings=bindings,
                manifest_sha256=canonical_digest(manifest), native_equivalence=equivalence,
                checkpoint='first saved genuine-previous recovery checkpoint',
                route='original shared_family_route from independent annotation priors',
                fit=('unchanged paired fit_new or fit_shared, original defaults '
                     'and request control cache'),
                audit=('unchanged audit_inclusion, single_candidate, exact published '
                       'owners and target'),
                conditional_retry='original numerical_only Powell retry, same deadline',
                prior='genuine_previous', focus_norad=68106, expected_points=33,
                no_annotation_rerun=True, GPS_used=False, published_result_changed=False,
                timeout_s=args.timeout, affinity=sorted(os.sched_getaffinity(0)),
                BLAS_threads=os.environ.get('OPENBLAS_NUM_THREADS'))
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value,
                                             allow_nan=False) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began = time.perf_counter()
    used = resource.getrusage(resource.RUSAGE_SELF)
    stages, backend = [], None

    def stage(name, operation):
        start, before = time.perf_counter(), resource.getrusage(resource.RUSAGE_SELF)
        status = 'failed'
        try:
            value = operation()
            (output / (name + '.pickle')).write_bytes(pickle.dumps(value, protocol=5))
            status = 'complete'
            return value
        finally:
            after = resource.getrusage(resource.RUSAGE_SELF)
            stages.append(dict(name=name, status=status,
                               seconds=time.perf_counter()-start,
                               cpu_seconds=(after.ru_utime + after.ru_stime
                                            - before.ru_utime - before.ru_stime)))
            save('stages.json', stages)

    try:
        if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin exactly one CPU and one BLAS thread')
        with stage_deadline(args.timeout):
            receipt, annotation, raw_binding = read_validation(validation)
            if (raw_binding['result_sha256'] != plan['validation_result_sha256']
                    or raw_binding['annotation_pickle_sha256'] != plan['annotation_pickle_sha256']):
                raise ValueError('Validation bytes changed after planning')
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            inventory, target_ids = match_checkpoint(
                context, evidence, scientific, receipt, annotation, request)
            prior_owners = {arm: dict(inventory['publication_support'][arm]['owners'])
                            for arm in ARMS}
            vote = identity_consensus(annotation['result']['folds'],
                                      score_name='conditional_target')
            shared = shared_family_route(annotation['result']['folds'], vote['norad'])
            controls = ControlCacheFactory(backend, request['inclusion_control_policy'])()
            operation = fit_shared if shared else fit_new
            trial = stage('primary-fit', lambda: operation(
                context, inventory, [annotation], control_cache=controls))
            audit = stage('primary-audit', lambda: audit_inclusion(
                context, inventory, [annotation], trial, shared=shared))
            selected = single_candidate(inventory, trial, audit, shared)
            primary = dict(metrics=arm_metrics(trial, audit, shared),
                           audit_all_verified=audit['all_verified'],
                           production_selected=selected is not None)
            retry = None
            if not shared and selected is None and numerical_only(
                    trial['control'], trial['new_family'], audit):
                retried = stage('retry-fit', lambda: fit_new(
                    context, inventory, [annotation], optimizer='powell',
                    control_cache=controls))
                replay = stage('retry-audit', lambda: audit_inclusion(
                    context, inventory, [annotation], retried, shared=False))
                selected = single_candidate(inventory, retried, replay, False)
                retry = dict(metrics=arm_metrics(retried, replay, False),
                             audit_all_verified=replay['all_verified'],
                             production_selected=selected is not None)
            qualified = exact_qualified_target(selected, inventory, target_ids, vote['norad'])
            final_modules = bound_sources(root)
            if (any(final_modules.get(name) != row for name, row in modules.items())
                    or any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
                           for path, digest in bindings.items())
                    or {arm: inventory['publication_support'][arm]['owners'] for arm in ARMS}
                    != prior_owners):
                raise ValueError('Frozen source, input or published owners changed')
            after = resource.getrusage(resource.RUSAGE_SELF)
            result = dict(plan, status='complete', validation=raw_binding,
                          scientific=scientific, checkpoint_replay=context['replay'],
                          annotation_consensus=vote, route='shared' if shared else 'new_family',
                          selected_target_id=annotation['result']['track_id'],
                          target_observation_ids_sha256=fingerprint(sorted(target_ids)),
                          published_incumbent_owners_sha256={
                              arm: fingerprint(prior_owners[arm]) for arm in ARMS},
                          baseline_arms={arm: dict(
                              endpoint_east_north_km=context['problems'][arm][1],
                              endpoint_latlon=context['scan'].search_region.latlon(
                                  context['problems'][arm][1])) for arm in ARMS},
                          primary=primary, retry=retry, qualification=qualified,
                          final_modules=final_modules, stages=stages,
                          native_counts=native_counts(backend),
                          elapsed_seconds=time.perf_counter()-began,
                          cpu_seconds=(after.ru_utime + after.ru_stime
                                       - used.ru_utime - used.ru_stime),
                          association_published=False, position_accuracy_measured=False)
            save('result.json', result)
    except BaseException as exc:
        counts = None
        if backend is not None:
            try:
                counts = native_counts(backend)
            except BaseException:
                counts = None
        save('failure.json', dict(status='failed', error_type=type(exc).__name__,
                                  error=str(exc), stages=stages, native_counts=counts,
                                  elapsed_seconds=time.perf_counter()-began))
        raise
    print(json.dumps(dict(status='complete', output=str(output),
                          qualified=qualified['qualified'],
                          association_published=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
