"""Nominate residual weak tracks using saved initial calibration, without fits.

The native graph, calibration membership and ownership remain unchanged. All
catalogue candidates reach the existing coarse screen; these are proposals,
never predictive validation or permission to add localization constraints.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import fingerprint
from initial_discovery_probe import load_saved, request_inputs, selected_branch
from probe_initial_discovery_policies import bound_sources, native_counts, native_equivalence

from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.prediction import nominate
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline

ARMS = ('c0', 'fitted_c')


def select_targets(tracks, curved, initial, *, maximum=3):
    """Duration-ranked whole graph tracks outside raw calibration and both owners."""
    if type(maximum) is not int or not 1 <= maximum <= 3:
        raise ValueError('Bounded target prefix of one to three required')
    seen = set()
    for track in tracks:
        ids = track['observation_ids']
        if len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError('Duplicate physical graph support')
        seen.update(ids)
    winner = selected_branch(initial)
    owned = {row['component'] for arm in ARMS
             for row in winner['arms'][arm]['all_graph_associations']['tracks']
             if row.get('compatible')}
    # Exclusion uses physical IDs, including any duplicate graph representations.
    occupied = {oid for track in tracks if track['key'] in owned
                for oid in track['observation_ids']}
    eligible, ledger = [], []
    for i, track in enumerate(tracks):
        if i in curved or set(track['observation_ids']) & occupied:
            continue
        times = np.asarray(track['times'])
        duration = float(np.ptp(times)) if len(times) else 0.0
        reasons = []
        if len(times) < 20:
            reasons.append('fewer_than_20_points')
        if duration < 15:
            reasons.append('shorter_than_15_seconds')
        if (len(track['pieces']) != 1
                or (len(times) > 1 and np.max(np.diff(np.sort(times))) > 5)):
            reasons.append('requires_explicit_fragment_view')
        row = dict(track_index=i, component=track['key'], points=len(times),
                   duration_s=duration, exclusion_reasons=reasons)
        ledger.append(row)
        if not reasons:
            eligible.append(row)
    eligible.sort(key=lambda r: (-r['duration_s'], -r['points'], r['component']))
    return dict(weak_unowned_tracks=len(ledger), eligible_targets=len(eligible),
                targets=eligible[:maximum], ledger=ledger)


def replay_pair(scan, initial):
    """Reconstruct each saved arm at its original reference; perform no optimization."""
    winner = selected_branch(initial)
    base, replay = {}, {}
    for arm in ARMS:
        saved = winner['arms'][arm]
        point = np.asarray(saved['fit']['parameters'])
        problem = NormalPosition(scan, winner['node'], scan.radio_sigma_hz, arm == 'fitted_c',
                                 reference=np.asarray(saved['reference']))
        residual = problem.residual(point)
        score = float(residual @ residual)
        if not np.isfinite(score) or abs(score - saved['fit']['score']) > 1e-5:
            raise ValueError('Original initial score replay mismatch: ' + arm)
        state = problem.state(point)
        if any(not np.allclose(state[k], saved['state'][k], rtol=1e-9, atol=1e-7)
               for k in ('beta', 'phases', 'smooth')):
            raise ValueError('Original initial state replay mismatch: ' + arm)
        base[arm] = problem, point, {}
        replay[arm] = dict(score=score, saved_score=saved['fit']['score'],
                           score_difference=score - saved['fit']['score'], state_matches=True)
    return base, replay


def nominate_targets(scan, base, selection, *, focus_norad=None):
    """Focus affects reporting only, after unchanged nomination over the full bank."""
    rows = []
    for target in selection['targets']:
        i = target['track_index']
        track = scan.tracks[i]
        mask = np.ones(len(track['times']), bool)
        offers, receipt = nominate(dict(scan=scan), base, i, mask, 12)
        unique = {}
        for offer in sorted(receipt['offers'], key=lambda row: row['cost']):
            unique.setdefault(offer['candidate_index'], offer)
        selected = {r['candidate_index'] for r in offers}
        ranking = [dict(rank=rank + 1, norad=int(scan.norads[j]),
                        selected=j in selected, **offer)
                   for rank, (j, offer) in enumerate(unique.items())]
        focus = [r for r in ranking if r['norad'] == focus_norad]
        rows.append(dict(target=target, selected_offers=offers, offer_ranking=ranking,
                         nomination_receipt=receipt,
                         focus_offer=focus[0] if focus else None,
                         focus_rank_scope=('cost rank of unique top-three offers per arm/position; '
                                           'not a full-catalogue fine-fit rank'),
                         focus_absence_reason=None if focus else 'not in coarse nomination offers',
                         full_target_used_for_proposal_only=True,
                         training_fold_shortlist_reuse_authorized=False,
                         predictive_validation_performed=False,
                         position_inclusion_authorized=False))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--focus-norad', type=int)
    parser.add_argument('--maximum-targets', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--timeout', type=int, choices=range(1, 111), default=110)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    equivalence = native_equivalence(request['backend_manifest'], manifest)
    sources = bound_sources(args.source_root.resolve())
    paths = [Path(__file__), args.request, args.native_manifest,
             *(Path(__file__).with_name(name) for name in (
                 'initial_discovery_probe.py', 'probe_initial_discovery_policies.py',
                 'census_algo07v5_initial_controls.py'))]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    plan = dict(status='plan', request_path=str(args.request.resolve()),
                request_sha256=canonical_digest(request), identity=job['identity'],
                source_root=str(args.source_root.resolve()), sources=sources, bindings=bindings,
                manifest_sha256=canonical_digest(manifest), native_equivalence=equivalence,
                policy='initial-weak-whole-track-nomination-probe-v1',
                maximum_targets=args.maximum_targets, minimum_points=20, minimum_span_s=15,
                target_order='descending duration, descending point count, component key',
                candidates='all original initial causal bank candidates; no NORAD filter',
                candidate_limit=12, phase_grid_s=np.arange(-15., 15.1, 3.),
                prior='previous', genuine_previous=False, focus_norad=args.focus_norad,
                focus_used_only_after_proposals=True, timeout_s=args.timeout,
                affinity=sorted(os.sched_getaffinity(0)),
                BLAS_threads=os.environ.get('OPENBLAS_NUM_THREADS'), GPS_used=False,
                optimizer_calls=0, predictive_validation_performed=False,
                position_inclusion_authorized=False)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value,
                                             allow_nan=False) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began = time.perf_counter()
    try:
        if sorted(os.sched_getaffinity(0)) != [20] or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin CPU20 and one BLAS thread')
        with stage_deadline(args.timeout):
            saved = load_saved(request, job, store)
            initial = saved['evidence']['audit']['initial']
            initial_hash = fingerprint(initial)
            prepared = saved['evidence']['preparation']
            sources = bound_sources(args.source_root.resolve())
            plan['sources'] = sources
            save('plan.json', plan)
            backend = ProcessBound(manifest, output / 'native-receipts')
            noise = (json.dumps(prepared['noise'], default=_json_value,
                                sort_keys=True, allow_nan=False) + '\n').encode()
            scan = _context(prepared, SearchRegion(tuple(job['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False, bound=backend)
            selection = select_targets(scan.tracks, scan.curved, initial,
                                       maximum=args.maximum_targets)
            base, replay = replay_pair(scan, initial)
            start = time.perf_counter()
            rows = nominate_targets(scan, base, selection, focus_norad=args.focus_norad)
            seconds = time.perf_counter() - start
            if (fingerprint(initial) != initial_hash
                    or bound_sources(args.source_root.resolve()) != sources
                    or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest
                           for p, digest in bindings.items())):
                raise ValueError('Saved evidence, bound source or input changed')
            result = dict(plan, status='complete', selection=selection, rows=rows,
                          catalogue_candidates=len(scan.norads),
                          catalogue_sha256=fingerprint(scan.sky),
                          focus_in_catalogue=bool(np.any(scan.norads == args.focus_norad)),
                          receipt_sha256=saved['sha256'], preparation_sha256=fingerprint(prepared),
                          initial_sha256=initial_hash, initial_evidence_unchanged=True,
                          context_replay=replay, native_counts=native_counts(backend),
                          nomination_seconds=seconds, elapsed_seconds=time.perf_counter() - began)
            save('result.json', result)
    except BaseException as exc:
        save('failure.json', dict(status='failed', error_type=type(exc).__name__, error=str(exc),
                                  elapsed_seconds=time.perf_counter() - began))
        raise
    print(json.dumps(dict(status='complete', output=str(output), targets=len(rows),
                          nomination_seconds=seconds, position_inclusion_authorized=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
