"""Replay bounded CFO linking followed by the common DS26 compact position solve."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES, latlon
import cold_replay as cold

from native_archive import ARCHIVE_BLOCK_CHARS, NativeArchive
from tracker import MAX_CANDIDATES, MAX_LANES, MAX_SEGMENTS, MAX_SUPPORT, TRACKS_PER_LANE
from tracker import Tracker, distinct_candidates


ARM_NAMES = ('c0', 'fitted_c')
DEADLINES = (60., 120.)


def clock():
    return time.perf_counter(), time.process_time()


def delta(start):
    wall, cpu = clock()
    return {'wall_s': wall-start[0], 'cpu_s': cpu-start[1]}


class Replay:
    def __init__(self, file):
        self.archive = NativeArchive(file)
        self.records = iter(self.archive)
        self.tracker = Tracker()
        self.pending = None
        self.exhausted = False
        self.latest_probe_end = None

    def advance(self, stop_s):
        start = clock()
        link = dict(wall_s=0., cpu_s=0.)
        while not self.exhausted:
            record = self.pending or next(self.records, None)
            if record is None:
                self.exhausted = True
                break
            midpoint, raw = record
            received = midpoint + self.archive.probe_s / 2
            if received > stop_s + 1e-8:
                self.pending = record
                break
            self.pending = None
            probe = json.loads(raw)
            lane = (1+probe['receiver_id'], probe['channel'], probe['actual_rf_hz'])
            peaks = distinct_candidates(probe['candidates'])
            linked_at = clock()
            self.tracker.ingest(midpoint, lane, peaks)
            timing = delta(linked_at)
            for field in link:
                link[field] += timing[field]
            self.latest_probe_end = received
        total = delta(start)
        return dict(stream_filter_link=link,
                    archive_decode_and_candidate_dedup={k: total[k]-v for k, v in link.items()})

    def freeze(self):
        doc, info = self.tracker.document()
        digest = hashlib.sha256()
        for tr in doc['tracks']:
            digest.update(repr((tr['receiver'], tr['channel'], tr['rf_hz'], len(tr['times']))).encode())
            digest.update(tr['times'].tobytes())
            digest.update(tr['values'].tobytes())
        info['solver_observations_sha256'] = digest.hexdigest()
        info['latest_probe_end_air_s'] = self.latest_probe_end
        return doc, info


def abstentions(reason):
    return {arm: dict(status='abstain', reason=reason) for arm in ARM_NAMES}


def solve(doc, bank):
    started = clock()
    data = cold.descriptors(doc, bank)
    times = dict(shortlist=delta(started))
    if data is None:
        return dict(arms=abstentions('no_curved_track_with_12_visible_satellites'),
                    descriptor_tracks=0, matched_tracks=0, stages=times)
    started = clock()
    bias = cold.bias_vote(data)
    score, xy, winners, cost = cold.grid_vote(data, bias)
    selected = np.flatnonzero(cost < 12.)
    times['bias_and_grid'] = delta(started)
    arms = {}
    for arm in ARM_NAMES:
        started = clock()
        answer = cold.solve(data, selected, winners, bias, xy, fitted_c=arm == 'fitted_c')
        times[arm] = delta(started)
        if answer['status'] == 'estimate':
            answer['latlon'] = latlon(answer['xy'])
            arms[arm] = answer
        else:
            arms[arm] = dict(status='abstain', reason=answer['status'])
    assignment = data['ids'][selected, winners[selected]]
    groups = data['group'][selected]
    rf = data['rf'][selected]
    within_group_rf = [len(np.unique(rf[groups == lane])) for lane in range(4)]
    return dict(arms=arms, stages=times, descriptor_tracks=len(data['ti']), matched_tracks=len(assignment),
                descriptor_numeric_bytes=sum(value.nbytes for value in data.values()),
                selected_satellites=assignment.tolist(), common_prefit_grid_score=float(score),
                selected_distinct_rf_by_group=within_group_rf,
                c_varies_within_some_receiver_side=bool(max(within_group_rf) > 1))


def endpoint(case, replay, deadline):
    stages = replay.advance(deadline)
    started = clock()
    document, info = replay.freeze()
    stages['freeze_segments'] = delta(started)
    started = clock()
    bank, receipt = cold.build_bank(case, dict(replay.archive.meta, duration_s=deadline),
                                    check_approximation=False)
    stages['causal_orbit_bank'] = delta(started)
    fix = solve(document, bank)
    fix['stages'].update(stages)
    fix.update(stream=info, bank=receipt, bank_numeric_bytes=sum(a.nbytes for a in bank.values()),
               air_deadline_s=deadline, archive_at_end=replay.exhausted)
    return fix, bank


def stream_full(case, path):
    started = clock()
    with path.open(encoding='utf-8') as file:
        replay = Replay(file)
        header = delta(started)
        fix, bank = endpoint(case, replay, replay.archive.meta['duration_s'])
        if not replay.exhausted:
            raise ValueError('full archive has probes beyond its declared final sample')
    total = delta(started)
    fix['stages']['archive_open_and_header'] = header
    return dict(case=case, wall_s=total['wall_s'], cpu_s=total['cpu_s'], **fix), bank


def signature(fix):
    return (fix['stream']['solver_observations_sha256'], fix['arms'], fix.get('selected_satellites'),
            fix.get('common_prefit_grid_score'))


def prefix_check(case, path, full):
    incremental = []
    with path.open(encoding='utf-8') as file:
        started = clock()
        replay = Replay(file)
        initial = delta(started)
        for deadline in DEADLINES:
            started = clock()
            fix, _ = endpoint(case, replay, deadline)
            fix['incremental_wall_s'] = delta(started)['wall_s']
            incremental.append(fix)
        replay.advance(replay.archive.meta['duration_s'])
        _, full_incremental = replay.freeze()
    for fix in incremental:
        deadline = fix['air_deadline_s']
        started = clock()
        with path.open(encoding='utf-8') as file:
            fresh, _ = endpoint(case, Replay(file), deadline)
        fix['fresh_wall_s'] = delta(started)['wall_s']
        fix['independent_replay_exact'] = signature(fresh) == signature(fix)
        assert fix['independent_replay_exact'], (case, deadline)
    matches = full_incremental == full['stream']
    assert matches, case
    return dict(prefixes=incremental, full_tracker_matches_uninterrupted=matches,
                incremental_archive_open_and_header=initial)


def graph_control(case, bank):
    started = clock()
    graph = cold.read(cold.GRAPHS / f'{case}.json')
    fix = solve(graph, bank)
    return dict(graph_track_count=len(graph['tracks']), graph_curved_count=len(graph['curved_indices']),
                graph_read_and_fit=delta(started), **fix)


def run(cases):
    rows, prefix, graph = [], {}, {}
    for case in cases:
        path = cold.INPUT / case / 'native.json'
        full, bank = stream_full(case, path)
        rows.append(full)
        prefix[case] = prefix_check(case, path, full)
        graph[case] = graph_control(case, bank)
        print(f'{case}: {full["wall_s"]:.3f}s, {full["stream"]["solver_segments"]} segments, '
              + ', '.join(f'{arm}={fit["status"]}' for arm, fit in full['arms'].items()), file=sys.stderr)
    return dict(method='Streaming alias-aware alpha-beta tracks to compact causal-TLE position solver',
                timing_scope='Full native candidate archive open, decode, deduplicate, link, freeze, '
                             'causal orbit bank, shortlist, bias/grid and both c fits. Host wall and cpu. '
                             'Prefix and graph controls are separate. IQ and detector execution excluded.',
                cases=rows, checks=dict(causal_prefix=prefix, graph_full=graph, capacities=dict(
                    lanes=MAX_LANES, live_tracks_per_lane=TRACKS_PER_LANE,
                    unique_candidates_per_probe=MAX_CANDIDATES, candidate_track_tests_per_probe=
                    MAX_CANDIDATES*TRACKS_PER_LANE, subsampled_points_plus_latest_per_live_track=MAX_SUPPORT,
                    archived_segments=MAX_SEGMENTS, solver_segments=MAX_SEGMENTS,
                    parser_block_chars=ARCHIVE_BLOCK_CHARS)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, help='smoke test one case and write JSON to stdout')
    args = parser.parse_args()
    result = run([args.case] if args.case else CASES)
    payload = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.case:
        print(payload, end='')
    else:
        (HERE / 'result.json').write_text(payload, encoding='utf-8')


if __name__ == '__main__':
    main()
