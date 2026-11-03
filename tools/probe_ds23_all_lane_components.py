"""Bounded saved-IQ pilot for every simultaneous-pair lane in three scans.

Pair selection is maximum simultaneous coverage per geometry-qualified lane,
before RF covariance, catalogue nominations or position errors are inspected.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import signal
import sys
import numpy as np

import probe_ds23_same_probe_IQ as iq
from ds23_same_probe_covariance import residual_pair
from probe_ds23_joint_probe_confirmation import BULK as FRESH, OUT as FRESH_REPORT
from run_algo01_ds23_sample import ROOT, DATASET, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_all_lane_components'
BULK = Path('/srv/bulk/leo/research/ds23-all-lane-components-20261020')


def visit_groups(jobs):
    grouped = defaultdict(list)
    if len({j['probe'] for j in jobs}) != len(jobs):
        raise ValueError('one paired-path job per receiver probe required')
    for job in jobs:
        grouped[job['visit_index']].append(job)
    for group in grouped.values():
        if len({j['native_receiver_id'] for j in group}) != len(group) or len({j['sample_counter'] for j in group}) != 1:
            raise ValueError('same visit requires distinct receivers and one exact raw counter')
    return grouped


def prepare():
    OUT.mkdir(parents=True, exist_ok=True); BULK.mkdir(parents=True, exist_ok=True)
    cases = ['DS23-0202', 'DS23-0274', read(FRESH_REPORT/'selection.json')['cases'][0]]
    jobs, selected, bindings = [], [], {}
    for case in cases:
        native = ROOT/'reports/2026_10_20_ds23_same_probe_curves' if case in cases[:2] else FRESH/'curves'
        evaluations, protocol = read(native/'evaluation.json'), read(native/'protocol.json')
        document = read(iq.SOURCE/case/'tracking.json'); source = document.get('source', document)
        bindings[case] = dict(native_evaluation_sha256=sha(native/'evaluation.json'), tracking_sha256=sha(iq.SOURCE/case/'tracking.json'))
        for lane in [r for r in evaluations['rows'] if r['case'] == case and r['status'] == 'complete']:
            pairs = [p for p in lane['pairs'] if all(p['geometry_checks'].values())]
            if not pairs:
                continue
            pair = max(pairs, key=lambda p: (len(p['probes']), p['first'], p['second']))
            paths = {p['key']: p for p in lane['paths']}
            native_job = next(j for j in protocol['jobs'] if j['case'] == case and j['lane'] == lane['lane'])
            group = case+f"_RX{lane['lane'][0]}_CH{lane['lane'][1]}"
            for k, pi in enumerate(pair['probes']):
                probe = source['probes'][pi]
                if source['probe_ms'] != 20 or probe['probe_start_ms'] != 0:
                    raise ValueError('complete original20ms probe required')
                peaks, lifted = [], []
                for role in ('first', 'second'):
                    path = paths[pair[role]]; index = path['probes'].index(pi)
                    peaks.append(native_job['candidates'][path['peak_indices'][index]])
                    lifted.append(path['values'][index])
                jobs.append(dict(case=case, group=group, probe=pi, paired_index=k, time_s=pair['time_s'][k], lane=lane['lane'],
                    visit_index=probe['visit_index'], sample_counter=probe['valid_start_counter'], native_receiver_id=probe['receiver_id'],
                    edge=probe['edge'], first=peaks[0], second=peaks[1], first_lifted_value=lifted[0], second_lifted_value=lifted[1]))
            selected.append(dict(case=case, group=group, lane=lane['lane'], pair=pair, sample_rate_hz=native_job['sample_rate_hz']))
    for case in cases:
        visit_groups([j for j in jobs if j['case'] == case])
    protocol = dict(cases=cases, jobs=jobs, selected=selected, bindings=bindings,
        dataset_manifest_sha256=sha(DATASET/'manifest.json'), maximum_windows_per_case=8192, maximum_export_seconds=120,
        maximum_analysis_seconds_per_probe=20, workers=12, no_new_RF_collection=True,
        no_GPS_or_satellite_ID_used_for_selection=True, RF_correlation_not_used_for_lane_pair_selection=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/probe_ds23_same_probe_IQ.py', ROOT/'tools/ds23_conditional_pilot_components.py']})
    path = BULK/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('all-lane RF protocol changed')
    if not path.exists():
        write(path, protocol)
    write(OUT/'selection.json', dict(cases=cases, lanes=[dict(case=s['case'], group=s['group'], lane=s['lane'], paired_probes=len(s['pair']['probes'])) for s in selected],
        protocol_sha256=sha(path), no_position_fit_yet=True, no_GPS_selection=True))
    print('ALL_LANE_COMPONENTS', len(jobs), 'probes', len(selected), 'lanes', flush=True)


def export(case):
    from leo.storage.short_window import ShortWindowReader
    protocol = read(BULK/'protocol.json')
    if sha(DATASET/'manifest.json') != protocol['dataset_manifest_sha256']:
        raise ValueError('dataset source changed')
    jobs = [j for j in protocol['jobs'] if j['case'] == case]; required = visit_groups(jobs)
    member = next(m for m in read(DATASET/'manifest.json')['members'] if m['dataset_label'] == case)
    def timeout(*_):
        raise TimeoutError('120 second existing-IQ export cap exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(120)
    arrays, points, manifests, visited = {}, [], [], 0
    try:
        for authority in member['raw_recording']['segments']:
            path = Path(authority['path'])
            if 'sha256:'+sha(path) != authority['sha256']:
                raise ValueError('recording manifest changed')
            reader = ShortWindowReader(path.parent); manifests.append(dict(path=str(path), sha256=sha(path)))
            for window in reader.windows():
                visited += 1; visit = window.index.acquisition['global_visit']
                if visit in required:
                    key = f'window_{visit:06d}'; arrays[key] = np.array(window.samples, copy=True)
                    for job in required[visit]:
                        if job['sample_counter'] != window.index.acquisition['sample_start']:
                            raise ValueError('selected raw counter differs')
                        points.append(dict(job, window_key=key, receiver_offset=reader.manifest.receiver_ids.index(job['native_receiver_id']),
                                           raw_window_sha256=window.index.iq_sha256))
                if len(points) == len(jobs) or visited >= 8192:
                    break
            if len(points) == len(jobs) or visited >= 8192:
                break
        if len(points) != len(jobs):
            raise ValueError('bounded export did not find every selected probe')
        meta = dict(case=case, points=points, sample_rate_hz=reader.manifest.sample_rate_hz,
                    protocol_sha256=sha(BULK/'protocol.json'), recording_manifests=manifests, raw_windows_read=visited,
                    selected_raw_window_hashes_verified_by_read_only_adapter=True)
        arrays['metadata_json'] = np.array(json.dumps(meta))
        np.savez_compressed(sys.stdout.buffer, **arrays)
    finally:
        signal.alarm(0)


def analyze_job(job):
    iq.OUT, iq.PANELS = BULK/'fits', BULK/'panels'
    return iq.analyze(job)


def analyze():
    protocol = read(BULK/'protocol.json')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('all-lane RF source changed')
    (BULK/'fits').mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=12) as pool:
        rows = [f.result() for f in as_completed([pool.submit(analyze_job, j) for j in protocol['jobs']])]
    by_probe = {(r['case'], r['probe']): r for r in rows}; summary = []
    for selected in protocol['selected']:
        jobs = [j for j in protocol['jobs'] if j['group'] == selected['group']]
        group = sorted([by_probe[j['case'], j['probe']] for j in jobs], key=lambda r: r['time_s'])
        qualified = [r for r in group if r['status'] == 'complete' and r['two_components_qualified']]
        record = dict(case=selected['case'], group=selected['group'], lane=selected['lane'], total=len(group), qualified=len(qualified))
        if len(qualified) >= 16:
            record['RF_qualified_statistics'] = residual_pair([r['time_s'] for r in qualified], [r['refined_first_value'] for r in qualified],
                [r['refined_second_value'] for r in qualified], selected['pair']['degree'])
        summary.append(record)
    write(BULK/'evaluation.json', dict(rows=rows, summary=summary, protocol_sha256=sha(BULK/'protocol.json'), no_position_fit_yet=True))
    write(OUT/'RF_summary.json', dict(summary=summary, bulk_evaluation_sha256=sha(BULK/'evaluation.json'),
                                    no_DS23_position_gain_claim=True, no_new_RF_collection=True))
    print('ALL_LANE_RF_COMPLETE', [(s['group'], s['qualified'], s.get('RF_qualified_statistics', {}).get('correlation')) for s in summary], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'export', 'analyze']); parser.add_argument('--case')
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare()
    elif args.stage == 'export':
        export(args.case)
    else:
        analyze()
