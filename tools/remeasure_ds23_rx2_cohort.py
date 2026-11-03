"""Bounded read-only pilot remeasurement, with stable original observation IDs.

Only the explicit measurement stage imports recording readers. Numeric output
goes to stdout; a non-root orchestrator owns every output artifact.
"""

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import PilotWorkspace
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, DATASET, read, sha, write

OUT = ROOT / 'reports/2026_10_19_ds23_rx2_measurement_cohort'


def selected_points(document, tracks):
    """Resolve original graph IDs through their format's public pure adapter."""
    if 'source' in document:
        from leo.analysis.glrt_frequency_input import frequency_evidence
        evidence, _, _ = frequency_evidence(document)
        source = document['source']
        mapping = {'sha256:'+hashlib.sha256(identity.encode()).hexdigest(): p
                   for identity, p in zip(evidence.ids, source['probes'], strict=True)}
    else:
        from leo.analysis.research.public_tracking_points import public_tracking_points
        rows, _ = public_tracking_points(document)
        source = document
        by_probe = {(p['receiver_id'], p['visit_index'], p['probe_index']): p for p in source['probes']}
        if len(by_probe) != len(source['probes']):
            raise ValueError('duplicate public probe identity')
        mapping = {r['observation_id']: by_probe[(r['native_receiver_id'], r['visit_index'], r['probe_index'])]
                   for r in rows}
    if source['probe_ms'] != 20:
        raise ValueError('this measurement protocol requires the original 20 ms support')
    points = []
    for track in tracks:
        for oid, value in zip(track['observation_ids'], track['values'], strict=True):
            probe = mapping[oid]
            peak = max((c for c in probe['candidates'] if c['passed_fractional_margin_gate']),
                       key=lambda c: (c['fractional_margin'], -c['candidate_rank']))
            period = 1 / 4.4e-6
            difference = (value-peak['fractional_tracking_cfo_hz']+period/2) % period-period/2
            if abs(difference) > 1e-6 or probe['channel'] != track['channel'] or probe['actual_rf_hz'] != track['rf_hz']:
                raise ValueError('original graph point differs from its canonical public winner')
            points.append(dict(observation_id=oid, track_key=track['key'], receiver_id=probe['receiver_id'],
                channel=probe['channel'], edge=probe['edge'], rf_hz=probe['actual_rf_hz'],
                visit_index=probe['visit_index'], probe_index=probe['probe_index'],
                probe_start_ms=probe['probe_start_ms'], visit_start_counter=probe['valid_start_counter'],
                payload_start_sample=probe['payload_start_sample'], peak=peak))
    if len(points) != len({p['observation_id'] for p in points}):
        raise ValueError('selected curves must have exclusive physical probes')
    return source, points


def qualification_points(points):
    """Three evenly spaced points per represented channel, before any new fit."""
    lanes = defaultdict(list)
    for point in points:
        lanes[point['channel']].append(point)
    selected = []
    for channel, lane in sorted(lanes.items()):
        lane.sort(key=lambda p:(p['visit_index'], p['probe_index'], p['observation_id']))
        for k in sorted(set(np.linspace(0, len(lane)-1, min(3, len(lane)), dtype=int))):
            selected.append(lane[k])
    return selected


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = read(DATASET / 'manifest.json')
    members = {m['dataset_label']: m for m in manifest['members']}
    cases = [r['dataset_label'] for r in read(SOURCE / 'sample.json')['selected']]
    plans = []
    for case in cases:
        path = OUT / (case+'_plan.json')
        if path.exists():
            raise FileExistsError('sealed measurement plans are never overwritten')
        result = read(SOURCE / case / 'result.json')
        keys = {r['component'] for r in result['final_node']['seed']['rows'] if r['active_curvature']}
        tracks = [t for t in read(SOURCE / case / 'tracks.json') if t['key'] in keys and t['receiver'] == 2]
        document = read(SOURCE / case / 'tracking.json')
        source, points = selected_points(document, tracks)
        if not 0 < len(points) <= 1200:
            raise ValueError('all seeded RX2 curves must fit the fixed 1200-point bound')
        plan = dict(case=case, tracks=tracks, points=points, qualification_points=qualification_points(points),
            format='fast' if 'source' in document else 'adaptive', sample_rate_hz=source['sample_rate_hz'],
            session_id=source['session_id'], input_manifest_sha256=source['input_manifest_sha256'],
            recording_id=members[case]['recording_id'],
            authorities=members[case]['raw_recording']['segments'],
            max_decoded_bytes=8*1024**3, max_raw_windows=12000, max_points=1200,
            tracking_sha256=sha(SOURCE / case / 'tracking.json'), tracks_sha256=sha(SOURCE / case / 'tracks.json'),
            original_result_sha256=sha(SOURCE / case / 'result.json'),
            selection='every point of every originally seeded active-curvature RX2 graph curve, including masked points',
            no_GPS_TLE_or_residual_selected_points=True, source_sha256=sha(Path(__file__)))
        write(path, plan)
        plans.append(dict(case=case, format=plan['format'], sample_rate_hz=plan['sample_rate_hz'],
                          curves=len(tracks), points=len(points), plan_sha256=sha(path)))
    write(OUT / 'protocol.json', dict(cases=plans, sample_sha256=sha(SOURCE / 'sample.json'),
        original_20_development_scans_not_all_DS23=True, selected_before_new_measurements=True,
        same_fixed_fitter_and_read_budgets_for_all_cases=True, no_new_RF=True,
        source_sha256=sha(Path(__file__)), fitter_sha256=sha(ROOT / 'tools/fast_local_pilot_refinement.py')))


def fit_samples(samples, point, fs, qualify=False):
    start = time.monotonic()
    y = samples[:, 0].astype(float)+1j*samples[:, 1].astype(float)
    peak = point['peak']
    epoch = peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
    center = peak['fractional_tracking_cfo_hz']
    work = FastPilotWorkspace(y, fs, point['edge'], epoch)
    begin = time.monotonic()
    joint = work.fast_joint_fit(center)
    core_seconds = time.monotonic()-begin
    odd = work.frequency_fit(center, subset='odd')
    even = work.frequency_fit(center, subset='even')
    for fit in (joint, odd, even):
        fit['effective_time_from_probe_start_s'] = work.effective_time(fit)
    row = dict(point=point, archived_CFO_hz=center, joint_CFO_epoch_rate=joint,
        odd_frames=odd, even_frames=even, core_seconds=core_seconds,
        samples_per_probe=len(y), sample_rate_hz=fs, seconds=time.monotonic()-start)
    if qualify:
        reference = PilotWorkspace(y, fs, point['edge'], epoch)
        scout = center+np.arange(-600, 601, 100.)
        seed = float(scout[np.argmax(reference.evaluate(scout))])
        begin = time.monotonic()
        fitted = reference.joint_fit(seed)
        row['reference'] = dict(result=fitted, seconds=time.monotonic()-begin)
        from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
        replay = conditioned_glrt64_score(y, fs, epoch_sample=peak['integer_epoch_sample'],
            acquired_cfo_hz=center, edge=point['edge'],
            fractional_epoch_offset_samples=peak['fractional_epoch_offset_samples'])
        row['public_score_replay'] = dict(exact_difference=replay.exact_score-peak['fractional_exact_score'],
            control_difference=replay.control_score-peak['fractional_control_score'])
    return row


def measure(case, qualify=False):
    plan_path = OUT / (case+'_plan.json')
    plan = read(plan_path)
    for name, key in (('tracking', 'tracking_sha256'), ('tracks', 'tracks_sha256'), ('result', 'original_result_sha256')):
        if sha(SOURCE / case / (name+'.json')) != plan[key]:
            raise ValueError('sealed original analysis authority changed')
    requests = plan['qualification_points'] if qualify else plan['points']
    required = defaultdict(list)
    for point in requests:
        required[point['visit_index']].append(point)
    rows, authorities, decoded, windows = [], [], 0, 0
    started = time.monotonic()
    fs = plan['sample_rate_hz']
    for authority in plan['authorities']:
        path = Path(authority['path'])
        if 'sha256:'+sha(path) != authority['sha256']:
            raise ValueError('recording manifest differs from dataset authority')
        if plan['format'] == 'adaptive':
            from leo.storage.native_adaptive_read import NativeAdaptiveReader
            reader = NativeAdaptiveReader(path, expected_file_sha256=authority['sha256'],
                                          max_decoded_bytes=plan['max_decoded_bytes']-decoded)
            if (reader.manifest_sha256 != plan['input_manifest_sha256'] or reader.session_id != plan['session_id']
                    or reader.sample_rate_hz != fs):
                raise ValueError('adaptive tracking is bound to a different recording')
            for visit in sorted(required):
                block = reader.read_visit(visit)
                windows += 1
                for point in required[visit]:
                    if (block.valid_start_counter != point['visit_start_counter']
                            or block.payload_start_sample != point['payload_start_sample']
                            or block.channel != point['channel'] or block.edge != point['edge']
                            or block.actual_rf_hz != point['rf_hz']):
                        raise ValueError('adaptive visit differs from public GLRT geometry')
                    offset = round(point['probe_start_ms']*fs/1000)
                    size = round(.020*fs)
                    if offset < 0 or offset+size > len(block.samples):
                        raise ValueError('probe extends beyond retained visit')
                    values = block.samples[offset:offset+size, block.receiver_ids.index(point['receiver_id'])]
                    binding = dict(point, raw_chunk_sha256=block.chunk_uncompressed_sha256,
                        raw_probe_sha256='sha256:'+hashlib.sha256(values.tobytes()).hexdigest())
                    rows.append(fit_samples(values, binding, fs, qualify))
                    print(case, len(rows), '/', len(requests), 'seconds', round(time.monotonic()-started, 1), file=sys.stderr, flush=True)
            decoded += reader.decoded_bytes
            authorities.append(dict(path=str(path), file_sha256=authority['sha256'],
                canonical_manifest_sha256=reader.manifest_sha256, selected_chunks_fully_hashed=True))
        else:
            from leo.storage.short_window import ShortWindowReader
            reader = ShortWindowReader(path.parent)
            # Fast tracking uses a virtual session across authenticated
            # recording segments; each segment keeps its original session ID.
            recording_id = plan.get('recording_id')
            if recording_id is None:
                member = next(m for m in read(DATASET / 'manifest.json')['members'] if m['dataset_label']==case)
                recording_id = member['recording_id']
            if (not reader.manifest.session_id.startswith(recording_id+'-segment-')
                    or reader.manifest.sample_rate_hz != fs):
                raise ValueError('fast tracking is bound to a different recording geometry')
            for window in reader.windows():
                windows += 1
                decoded += window.samples.nbytes
                if windows > plan['max_raw_windows'] or decoded > plan['max_decoded_bytes']:
                    raise ValueError('fast-recording read budget exceeded')
                visit = window.index.acquisition['global_visit']
                for point in required.get(visit, []):
                    if (window.index.acquisition['sample_start'] != point['visit_start_counter']
                            or point['probe_start_ms'] != 0 or len(window.samples) != round(.020*fs)):
                        raise ValueError('fast window differs from its original public probe')
                    values = window.samples[:, reader.manifest.receiver_ids.index(point['receiver_id'])]
                    binding = dict(point, raw_window_sha256=window.index.iq_sha256)
                    rows.append(fit_samples(values, binding, fs, qualify))
                    if len(rows) % 20 == 0:
                        print(case, len(rows), '/', len(requests), 'seconds', round(time.monotonic()-started, 1), file=sys.stderr, flush=True)
                if len(rows) == len(requests):
                    break
            authorities.append(dict(path=str(path), file_sha256=authority['sha256'],
                selected_windows_and_compressed_chunks_and_indexes_hashed=True,
                whole_decoded_final_chunk_hash_not_claimed_when_iteration_stops_early=True))
        if len(rows) == len(requests):
            break
    if len(rows) != len({r['point']['observation_id'] for r in rows}) or {r['point']['observation_id'] for r in rows} != {p['observation_id'] for p in requests}:
        raise ValueError('measurement did not cover exactly the sealed physical probes')
    result = dict(case=case, rows=rows, qualification_only=qualify,
        panel_metadata=dict(case=case, tracks=plan['tracks'], sample_rate_hz=fs, format=plan['format']),
        plan_sha256=sha(plan_path), source_sha256=sha(Path(__file__)),
        refinement_source_sha256=sha(ROOT / 'tools/fast_local_pilot_refinement.py'),
        reference_source_sha256=sha(ROOT / 'tools/local_pilot_refinement.py'),
        reader_source_sha256=sha(ROOT / 'src/leo/storage' / ('native_adaptive_read.py' if plan['format']=='adaptive' else 'short_window.py')),
        recording_authorities=authorities, raw_windows_read=windows, decoded_bytes=decoded,
        seconds=time.monotonic()-started, all_sealed_requests_measured=True,
        no_GPS_TLE_polynomial_or_satellite_in_local_fit=True, recording_and_tracking_contracts_unchanged=True)
    print(json.dumps(result, default=lambda x:x.tolist() if isinstance(x, np.ndarray) else x.item() if isinstance(x,np.generic) else str(x)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prepare', 'measure', 'qualify'), required=True)
    parser.add_argument('--case')
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare()
    else:
        measure(args.case, args.stage == 'qualify')
