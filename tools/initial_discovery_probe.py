"""Probe one post-initial radio re-nomination without fitting or accepting it.

Default invocation writes a plan without loading a scientific archive. Execution
replays the stored initial likelihood using its original previous-orbit prior.
The focus NORAD is a report filter and never enters proposal generation.
"""

import argparse
import hashlib
import json
import os
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import fingerprint

from leo.analysis.localization_v3.discovery import explore, reference_state, signature
from leo.analysis.localization_v3.families import AnchoredFamilies
from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4.backend import ProcessBound, validate_manifest
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import runtime_versions, source_bindings, stage_deadline


def selected_branch(initial):
    choices = [c for c in initial['choices']
               if c['hypothesis'] == initial['selected_hypothesis']]
    if initial['status'] != 'complete' or len(choices) != 1:
        raise ValueError('One completed selected initial branch required')
    return choices[0]


def miss_census(evidence):
    audit = evidence['audit']
    winner = selected_branch(audit['initial'])
    labels = {r['candidate_norad'] for r in winner['node']['seed']['rows']}
    targets = {t['track_id']: t for t in audit['recovery_inventory']['selected_targets']}
    rows = []
    for attempt in audit['predictive_recovery']['attempts']:
        target = targets[attempt['track_id']]
        norad = attempt['annotation']['norad']
        component = target['component']
        owners = {arm: next((r['norad'] for r in data['all_graph_associations']['tracks']
                            if r['component'] == component and r['compatible']), None)
                  for arm, data in winner['arms'].items()}
        rows.append(dict(track_id=attempt['track_id'], component=component,
                         recovery_status=attempt['status'], proposed_norad=norad,
                         present_in_initial_labels=norad in labels,
                         initial_accepted_owners=owners))
    return rows


def replay_initial(scan, initial):
    winner = selected_branch(initial)
    saved = winner['arms']['c0']
    point = np.asarray(saved['fit']['parameters'])
    problem = NormalPosition(scan, winner['node'], scan.radio_sigma_hz, False,
                             reference=np.asarray(saved['reference']))
    residual = problem.residual(point)
    score = float(residual @ residual)
    difference = score - saved['fit']['score']
    if not np.isfinite(difference) or abs(difference) > 1e-5:
        raise ValueError(f'Original initial-context score replay mismatch {difference}')
    state = problem.state(point)
    for key in ('beta', 'phases', 'smooth'):
        if not np.allclose(state[key], saved['state'][key], rtol=1e-9, atol=1e-7):
            raise ValueError(f'Original initial-context state replay mismatch {key}')
    return dict(prior='previous', genuine_previous=False, score=score,
                saved_score=saved['fit']['score'], score_difference=difference,
                saved_state_sha256=fingerprint(saved['state']), state_matches=True)


def propose(scan, initial):
    before = fingerprint(initial)
    winner = selected_branch(initial)
    original = winner['node']
    incumbent = winner['arms']['c0']
    point = np.asarray(incumbent['fit']['parameters'])
    state = reference_state(incumbent['state'])
    seed, detail = explore(scan, state, point, 'receiver_smooth', compact_update=False)
    anchor = AnchoredFamilies(scan, seed, 'receiver_smooth', False, point)
    node = dict(seed=seed, aliases=anchor.alias)
    old = {r['component']: (r, a)
           for r, a in zip(original['seed']['rows'], original['aliases'], strict=True)}
    changes, rows = [], []
    for row, alias in zip(seed['rows'], node['aliases'], strict=True):
        previous, old_alias = old[row['component']]
        summary = {key: row[key] for key in (
            'component', 'candidate_norad', 'candidate_index', 'points', 'rms_hz',
            'bias_hz', 'compatible')}
        summary['alias'] = int(alias)
        rows.append(summary)
        if (row['candidate_norad'], alias) != (previous['candidate_norad'], old_alias):
            changes.append(dict(component=row['component'],
                                previous_norad=previous['candidate_norad'],
                                proposed_norad=row['candidate_norad'],
                                previous_alias=int(old_alias), proposed_alias=int(alias)))
    old_labels = {r['candidate_norad'] for r in original['seed']['rows']}
    new_labels = {r['candidate_norad'] for r in seed['rows']}
    if before != fingerprint(initial):
        raise ValueError('Proposal mutated stored initial evidence')
    return dict(original_signature=signature(original), proposed_signature=signature(node),
                identical_hypothesis=signature(original) == signature(node),
                point_east_north_km=point, original_norads=sorted(old_labels),
                proposed_norads=sorted(new_labels), added_norads=sorted(new_labels - old_labels),
                removed_norads=sorted(old_labels - new_labels), changes=changes,
                proposed_rows=rows, proposal_detail=detail, initial_evidence_unchanged=True,
                position_fit_performed=False, position_inclusion_authorized=False,
                predictive_qualification_performed=False)


def request_inputs(path):
    from leo.operations import localization_v3_job, localization_v4_job, localization_v5_job
    from leo.storage.localization_v3 import LocalizationV3Store
    from leo.storage.localization_v4 import LocalizationV4Store
    from leo.storage.localization_v5 import LocalizationV5Store

    request = json.loads(path.read_bytes())
    handlers = {'algo07v4-native-v1': (localization_v4_job, LocalizationV4Store),
                'algo07v5-native-v1': (localization_v5_job, LocalizationV5Store)}
    if 'job' in request:
        if request.get('algorithm') not in handlers:
            raise ValueError('Supported saved native request required')
        validator, store = handlers[request['algorithm']]
        validator.validate_request(request)
        job = request['job']
    else:
        localization_v3_job.validate_request(request)
        job, store = request, LocalizationV3Store
    if job['runtime'] != runtime_versions():
        raise ValueError('Match the saved numerical runtime')
    return request, job, store


def load_saved(request, job, store):
    if not Path(job['output_root']).is_dir():
        raise FileNotFoundError(job['output_root'])
    saved = store(job['output_root']).load(job['identity']['run_id'])
    evidence, receipt = saved['evidence'], saved['receipt']
    if (evidence['provenance']['request_sha256'] != canonical_digest(request)
            or evidence['provenance']['configuration']['request'] != job
            or evidence['identity'] != job['identity']
            or any(receipt[key] != value for key, value in job['identity'].items())
            or saved['sha256'] != canonical_digest(receipt)):
        raise ValueError('Saved request, evidence and receipt binding mismatch')
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--focus-norad', type=int, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 121), default=110)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output directory required')
    request, job, store = request_inputs(args.request)
    sources = {value['path']: value['sha256'] for value in source_bindings().values()}
    sources[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    sources[str(args.request.resolve())] = hashlib.sha256(args.request.read_bytes()).hexdigest()
    plan = dict(status='plan', request_path=str(args.request.resolve()),
                request_sha256=canonical_digest(request), identity=job['identity'],
                sources=sources, timeout_s=args.timeout, affinity=sorted(os.sched_getaffinity(0)),
                BLAS_threads=os.environ.get('OPENBLAS_NUM_THREADS'),
                scope='one c0-incumbent all-catalogue re-nomination; no position fits',
                prior='previous', genuine_previous=False, focus_norad=args.focus_norad,
                focus_used_only_after_proposal=True, GPS_used=False,
                future_TLE_used=False, position_inclusion_authorized=False)
    output.mkdir(parents=True)

    def save(name, value):
        (output / name).write_text(json.dumps(
            value, indent=2, default=_json_value, allow_nan=False) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began = time.perf_counter()
    try:
        if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin exactly one CPU and one BLAS thread')
        with stage_deadline(args.timeout):
            saved = load_saved(request, job, store)
            evidence = saved['evidence']
            prepared = evidence['preparation']
            noise = (json.dumps(prepared['noise'], default=_json_value,
                                sort_keys=True, allow_nan=False) + '\n').encode()
            backend = (ProcessBound(validate_manifest(request['backend_manifest']),
                                    output / 'native-receipts')
                       if 'backend_manifest' in request else None)
            scan = _context(prepared, SearchRegion(tuple(job['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False, bound=backend)
            initial = deepcopy(evidence['audit']['initial'])
            replay = replay_initial(scan, initial)
            start = time.perf_counter()
            proposal = propose(scan, initial)
            proposal_seconds = time.perf_counter() - start
            focus = [r for r in proposal['proposed_rows']
                     if r['candidate_norad'] == args.focus_norad]
            if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
                   for path, digest in sources.items()):
                raise ValueError('Probe source or input changed during execution')
            result = dict(status='complete', receipt_sha256=saved['sha256'],
                          preparation_sha256=fingerprint(prepared),
                          initial_sha256=fingerprint(initial), context_replay=replay,
                          proposal=proposal, focus_norad=args.focus_norad, focus_rows=focus,
                          known_recovery_misses=miss_census(evidence),
                          proposal_seconds=proposal_seconds,
                          elapsed_seconds=time.perf_counter() - began,
                          GPS_used=False, future_TLE_used=False,
                          position_inclusion_authorized=False)
            save('result.json', result)
    except Exception as exc:
        save('failure.json', dict(status='failed', error_type=type(exc).__name__, error=str(exc),
                                  elapsed_seconds=time.perf_counter() - began))
        raise
    print(json.dumps(dict(status='complete', output=str(output), focus_rows=len(focus),
                          added_norads=proposal['added_norads'],
                          position_inclusion_authorized=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
