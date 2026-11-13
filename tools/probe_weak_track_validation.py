"""Validate one radio-selected weak track at the saved first recovery checkpoint.

The default invocation writes only a bound plan. Execution uses the original
three independent predictive folds; it never adds an association or position
constraint. The optional focus NORAD filters the completed report only.
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
from census_algo07v5_initial_controls import fingerprint
from initial_discovery_probe import load_saved
from probe_algo07v5_annotation_rounds import load_context, request_inputs
from probe_initial_discovery_policies import bound_sources, native_counts, native_equivalence
from probe_initial_weak_track_nomination import select_targets

from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.analysis.localization_v3.recovery_partitions import (
    planned_split,
    require_distinct_annotation,
)
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline

ARMS = ('c0', 'fitted_c')
POLICY = 'weak-track-genuine-previous-independent-annotation-v1'


def selected_recovery_record(scan, initial, inventory):
    """Match the radio-only initial target to whole, unowned checkpoint support."""
    selected = select_targets(scan.tracks, scan.curved, initial, maximum=3)
    if not selected['targets']:
        raise ValueError('No radio-selected weak whole track')
    target = selected['targets'][0]
    i = target['track_index']
    track = scan.tracks[i]
    physical = set(track['observation_ids'])
    if len(physical) != len(track['observation_ids']):
        raise ValueError('Duplicate target physical support')
    records = {arm: [row for row in inventory['tracks']
                     if row['arm'] == arm and row['track_index'] == i]
               for arm in ARMS}
    if any(len(records[arm]) != 1 for arm in ARMS):
        raise ValueError('Exactly one matching checkpoint target per arm required')
    c0, fitted = (records[arm][0] for arm in ARMS)
    for row in (c0, fitted):
        if (row['component'] != target['component'] or not row['current_large']
                or set(row['observation_ids']) != physical
                or set(row['all_track_observation_ids']) != physical):
            raise ValueError('Selected weak track is not whole and unowned at checkpoint')
    if c0['track_id'] != fitted['track_id']:
        raise ValueError('Paired checkpoint target identity differs')
    return selected, c0


def request_training_fit(request):
    """Use the exact saved v5 training policy, including its fallback semantics."""
    from leo.analysis.localization_v5 import annotation_fallback, annotation_training

    policy = request.get('annotation_training_policy')
    fits = {fit.policy['id']: fit for fit in
            (annotation_training.fit, annotation_fallback.fit)}
    if not isinstance(policy, dict) or policy.get('id') not in fits:
        raise ValueError('Saved request-bound annotation training policy required')
    fit = fits[policy['id']]
    if fit.policy != policy or policy['phase_rounds'] != 5 or policy['position_steps'] != 48:
        raise ValueError('Annotation training implementation differs from saved request')
    return fit


def fold_receipts(context, record, annotation, *, focus_norad):
    """Verify independent training masks and expose all selected fold nominees."""
    protocol = annotation['protocol']
    result = annotation['result']
    require_distinct_annotation(result, protocol)
    p0, _ = context['problems']['c0']
    track = context['scan'].tracks[record['track_index']]
    n = len(p0.flat_times)
    full_times = np.r_[p0.flat_times, track['times']]
    if (protocol['seed_list'] != [f['seed'] for f in result['folds']]
            or len(result['folds']) != 3 or protocol['target_used_for_calibration']
            or protocol['GPS_used'] or protocol['future_TLE']
            or protocol['phase_rounds'] != 5 or protocol['position_steps'] != 48
            or protocol['block_s'] != 12 or protocol['guard_s'] != 2):
        raise ValueError('Original independent annotation protocol required')
    rows = []
    for fold in result['folds']:
        seed = fold['seed']
        train, held, split = planned_split(
            full_times, track['times'], seed, protocol['partition_plan'])
        nomination = annotation['nominations'][seed]
        indices = np.asarray(nomination['nomination']['training_indices'], int)
        if (split != fold['split'] or split != nomination['split']
                or len(indices) > 16 or len(set(indices.tolist())) != len(indices)
                or np.any(indices < 0) or np.any(indices >= len(track['times']))
                or not np.all(train[n:][indices])
                or np.any(held[n:][indices])
                or nomination['nomination']['nomination_uses_held_points']
                or len(nomination['selected']) > 12
                or len(fold['proposals']) != len(nomination['selected'])):
            raise ValueError('Fold nomination uses unexpected or held support')
        calibration_keep = context['keep'] & train[:n]
        if not calibration_keep.any() or train[n:].sum() < 8 or held[n:].sum() < 4:
            raise ValueError('Insufficient independent training or held support')
        proposals = []
        for offer, proposal in zip(nomination['selected'], fold['proposals'], strict=True):
            j = offer['candidate_index']
            if (proposal['candidate_index'] != j
                    or proposal['norad'] != int(context['scan'].norads[j])
                    or any(proposal['arms'][arm]['target_enters_calibration_equations']
                           for arm in ARMS)):
                raise ValueError('Fold proposal differs from full-bank nominee')
            proposals.append(dict(candidate_index=j, norad=proposal['norad'],
                alias=proposal['alias'], nomination_cost=offer['cost'],
                arms={arm: dict(
                    training_objective=proposal['arms'][arm]['training_objective'],
                    held_negative_twice_log_density=proposal['arms'][arm]['scores'][
                        'conditional_target']['negative_twice_log_density'],
                    held_rms_hz=proposal['arms'][arm]['scores'][
                        'conditional_target']['rms_hz'],
                    unobservable=proposal['arms'][arm]['scores'][
                        'conditional_target'].get('unobservable', False)) for arm in ARMS}))
        rows.append(dict(seed=seed, split=split,
                         calibration_keep_sha256=fingerprint(calibration_keep),
                         calibration_training_points=int(calibration_keep.sum()),
                         target_training_points=int(train[n:].sum()),
                         target_held_points=int(held[n:].sum()),
                         nomination_indices=indices.tolist(),
                         nomination_receipt_sha256=fingerprint(nomination),
                         proposals=proposals,
                         focus_proposals=[row for row in proposals
                                          if row['norad'] == focus_norad]))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--focus-norad', type=int, default=68106)
    parser.add_argument('--timeout', type=int, choices=range(1, 111), default=110)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    request, job, store = request_inputs(args.request)
    fit = request_training_fit(request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    equivalence = native_equivalence(request['backend_manifest'], manifest)
    root = args.source_root.resolve()
    modules = bound_sources(root)
    paths = [Path(__file__), args.request, args.native_manifest,
             *(Path(__file__).with_name(name) for name in (
                 'initial_discovery_probe.py', 'probe_algo07v5_annotation_rounds.py',
                 'probe_initial_discovery_policies.py',
                 'probe_initial_weak_track_nomination.py',
                 'census_algo07v5_initial_controls.py'))]
    bindings = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths}
    plan = dict(status='plan', policy=POLICY,
                request_path=str(args.request.resolve()), request_sha256=canonical_digest(request),
                identity=job['identity'], source_root=str(root), modules=modules,
                bindings=bindings, manifest_sha256=canonical_digest(manifest),
                native_equivalence=equivalence,
                checkpoint='first recovery inventory after saved cavity decision',
                orbit_prior='genuine_previous',
                selection='original radio-only weak whole-track duration prefix; first target',
                focus_norad=args.focus_norad, focus_used_only_after_fold_nomination=True,
                original_training_policy=fit.policy,
                fold_count=3, block_s=12, guard_s=2, timestamp_only_randomized=True,
                phase_rounds=5, position_steps=48, candidate_limit=12,
                causal_bank='full original checkpoint bank; count reported after context load',
                no_full_data_candidate_shortlist=True, no_full_data_calibration_reuse=True,
                GPS_used=False, position_inclusion_authorized=False,
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
    start = time.perf_counter()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    raw_annotation = None
    try:
        if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin exactly one CPU and one BLAS thread')
        with stage_deadline(args.timeout):
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            saved = load_saved(request, job, store)
            initial = saved['evidence']['audit']['initial']
            before = fingerprint((initial, evidence, context['scan'].tracks))
            selection, record = selected_recovery_record(
                context['scan'], initial, evidence['inventory'])
            inventory = dict(evidence['inventory'],
                             publication_support=evidence['publication_support'])
            started = time.perf_counter()
            annotation = annotate(context, inventory, record['track_id'],
                                  target_record=record, candidates=12, folds=3,
                                  phase_step=.1, shifted_origin=True, training_fit=fit)
            annotation_seconds = time.perf_counter() - started
            raw_annotation = pickle.dumps(annotation, protocol=5)
            (output / 'annotation.pickle').write_bytes(raw_annotation)
            if annotation['protocol'].get('training_optimizer_policy') != fit.policy:
                raise ValueError('Fold training policy differs from saved request')
            folds = fold_receipts(context, record, annotation,
                                  focus_norad=args.focus_norad)
            final_modules = bound_sources(root)
            if (fingerprint((initial, evidence, context['scan'].tracks)) != before
                    or any(final_modules.get(name) != row for name, row in modules.items())):
                raise ValueError('Saved context or bound runtime changed')
            if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
                   for path, digest in bindings.items()):
                raise ValueError('Bound probe or input changed')
            after = resource.getrusage(resource.RUSAGE_SELF)
            result = dict(plan, status='complete', scientific=scientific,
                          receipt_sha256=saved['sha256'],
                          initial_sha256=fingerprint(initial),
                          checkpoint_context_replay=context['replay'],
                          selected_radio_target=selection['targets'][0],
                          radio_selection=selection,
                          checkpoint_record=record,
                          actual_causal_bank_candidates=len(context['scan'].norads),
                          causal_bank_sha256=fingerprint(context['scan'].sky),
                          annotation_sha256=fingerprint(annotation),
                          annotation_pickle_sha256=hashlib.sha256(raw_annotation).hexdigest(),
                          identity_consensus=annotation['result']['annotation'],
                          folds=folds, partition_plan=annotation['protocol']['partition_plan'],
                          native_counts=native_counts(backend),
                          annotation_seconds=annotation_seconds,
                          elapsed_seconds=time.perf_counter()-start,
                          cpu_seconds=(after.ru_utime + after.ru_stime
                                       - usage.ru_utime - usage.ru_stime),
                          final_modules=final_modules, original_context_unchanged=True,
                          predictive_validation_performed=True,
                          published_result_changed=False)
            save('result.json', result)
    except BaseException as exc:
        save('failure.json', dict(status='failed', error_type=type(exc).__name__,
                                  error=str(exc), elapsed_seconds=time.perf_counter()-start,
                                  unvalidated_annotation_pickle_sha256=(
                                      hashlib.sha256(raw_annotation).hexdigest()
                                      if raw_annotation is not None else None)))
        raise
    print(json.dumps(dict(status='complete', output=str(output),
                          identity_status=result['identity_consensus']['status'],
                          position_inclusion_authorized=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
