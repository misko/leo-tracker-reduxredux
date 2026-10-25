"""Read-only original GLRT peak and graph ownership trace; no orbit fitting."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / 'ds25-20261024/DS24-0013'
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
PARENT = HERE.parent.parent / 'ds24-fast-identifiability-r01/transfer/ownership/DS24-0013/parent.json'
WINDOWS = {3: (210., 245.), 4: (235., 270.), 5: (210., 270.)}
TIDS = {3: 2, 4: 0, 5: 1}
PERIOD = 1 / 4.4e-6


def read(p):
    return json.loads(Path(p).read_bytes())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(name, data):
    with (HERE / name).open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def winner(candidates):
    eligible = [c for c in candidates if c['passed_fractional_margin_gate'] is True]
    return max(eligible, key=lambda c: (c['fractional_margin'], -c['candidate_rank'])) if eligible else None


def lane_owner(track, lane):
    selected = [lane[i] for i in track['indices']]
    assert [p['observation_id'] for p in selected] == track['observation_ids']
    assert [p['time_s'] for p in selected] == track['times']
    delta = np.asarray(track['values']) - np.asarray([p['measured_cfo_hz'] for p in selected])
    return {p['observation_id']: track['key'] for p in selected}, delta


def csv_write(name, rows):
    with (HERE / name).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def freeze():
    inputs = [SOURCE / n for n in ['tracking.json', 'tracks.json', 'observations.json', 'prepared.json', 'input_receipt.json']]
    inputs += [PARENT, Path(__file__), HERE / 'test_trace.py', HERE / 'PROTOCOL.md',
               REPO / 'src/leo/analysis/research/public_tracking_points.py',
               REPO / 'tools/evaluate_ds22_merged_tracks.py', REPO / 'tools/evaluate_ds22_public_tracks.py']
    write('protocol.json', dict(files={str(p): sha(p) for p in inputs}, windows=WINDOWS,
        source_track_ids=TIDS, graph_minus_native_CFO_Hz=-2*PERIOD, maximum_processing_seconds=180,
        no_orbit_scores=True, no_position_fits=True, GPS_used=False, no_input_mutation=True))


def run():
    began = time.monotonic()
    protocol = read(HERE / 'protocol.json')
    assert all(sha(p) == h for p, h in protocol['files'].items())
    from leo.analysis.research.public_tracking_points import public_tracking_points
    source = read(SOURCE / 'tracking.json')['source']
    public, public_meta = public_tracking_points(source)
    native = {r['observation_id']: r for r in public}
    observations = read(SOURCE / 'observations.json')
    assert set(native) == {r['observation_id'] for r in observations}
    for p in observations:
        for key in ['receiver', 'channel', 'time_s', 'measured_cfo_hz', 'actual_rf_hz']:
            assert p[key] == native[p['observation_id']][key]
    tracks = read(SOURCE / 'tracks.json')
    owners, shifts = {}, {}
    for track in tracks:
        lane = [p for p in observations if (p['receiver'], p['channel'], p['actual_rf_hz']) ==
                (track['receiver'], track['channel'], track['rf_hz'])]
        mapping, delta = lane_owner(track, lane)
        assert not set(mapping) & set(owners)
        owners.update(mapping)
        shifts[track['key']] = delta
    coverage = read(PARENT)['coverage']
    accepted = {a: set(d['accepted_observation_ids']) for a, d in coverage.items()}
    assert accepted['c0'] == accepted['fitted_c']
    accepted = accepted['c0']
    fs, origin, width = source['sample_rate_hz'], source['timing']['session_start_device_sample_counter'], source['probe_ms']
    selected = {ch: next(t for t in tracks if t['receiver'] == 2 and t['channel'] == ch and
                         f'-T{TIDS[ch]:03d}-' in t['key']) for ch in WINDOWS}
    for t in selected.values():
        assert np.max(abs(shifts[t['key']] + 2*PERIOD)) < 1e-7
    native_by_time = {(p['native_receiver_id'], p['valid_start_counter']): p for p in public}
    local_winners, peaks, probes, track_rows = [], [], [], []
    for pi, probe in enumerate(source['probes']):
        ch = probe['channel']
        if probe['receiver_id'] != 1 or ch not in WINDOWS:
            continue
        start = probe['valid_start_counter'] + round(probe['probe_start_ms']*fs/1000)
        stamp = (start-origin)/fs + width/2000
        if not WINDOWS[ch][0] <= stamp <= WINDOWS[ch][1]:
            continue
        chosen = winner(probe['candidates'])
        point = native_by_time.get((probe['receiver_id'], start))
        assert (point is None) == (chosen is None)
        oid = point['observation_id'] if point else ''
        common = dict(channel=ch, time_s=stamp, probe_list_index=pi,
            visit_index=probe['visit_index'], probe_index=probe['probe_index'], device_start_counter=start,
            actual_RF_Hz=probe['actual_rf_hz'], winner_native_id=oid,
            original_graph_owner=owners.get(oid, ''), baseline_accepted=oid in accepted,
            selected_source=oid in selected[ch]['observation_ids'])
        probes.append(common | dict(archived_peak_count=len(probe['candidates']),
                                   passing_peak_count=sum(c['passed_fractional_margin_gate'] is True for c in probe['candidates'])))
        for ci, c in enumerate(probe['candidates']):
            is_winner = c is chosen
            row = common | dict(candidate_list_index=ci, original_candidate_rank=c['candidate_rank'],
                passed_original_fractional_gate=c['passed_fractional_margin_gate'], is_public_winner=is_winner,
                native_CFO_Hz=c['fractional_tracking_cfo_hz'], graph_gauge_CFO_Hz=c['fractional_tracking_cfo_hz']-2*PERIOD,
                fractional_margin=c['fractional_margin'], fractional_epoch_offset_samples=c['fractional_epoch_offset_samples'])
            peaks.append(row)
            if is_winner:
                assert c['fractional_tracking_cfo_hz'] == point['measured_cfo_hz']
                local_winners.append(row)
    for ch, bounds in WINDOWS.items():
        for track in tracks:
            if track['receiver'] != 2 or track['channel'] != ch:
                continue
            for ix, oid, stamp, value in zip(track['indices'], track['observation_ids'], track['times'], track['values'], strict=True):
                if bounds[0] <= stamp <= bounds[1]:
                    track_rows.append(dict(channel=ch, component=track['key'], native_lane_index=ix,
                        native_id=oid, time_s=stamp, original_graph_CFO_Hz=value,
                        common_graph_gauge_CFO_Hz=native[oid]['measured_cfo_hz']-2*PERIOD,
                        own_graph_minus_native_Hz=value-native[oid]['measured_cfo_hz'], selected_source=track is selected[ch],
                        baseline_accepted=oid in accepted))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), layout='constrained')
    colors = plt.get_cmap('tab10')
    summary = []
    for row, ch in enumerate((3, 4, 5)):
        ww = [p for p in local_winners if p['channel'] == ch]
        pp = [p for p in peaks if p['channel'] == ch and not p['is_public_winner']]
        tt = [t for t in tracks if t['receiver'] == 2 and t['channel'] == ch and
              any(WINDOWS[ch][0] <= s <= WINDOWS[ch][1] for s in t['times'])]
        for col in (0, 1):
            ax = axes[row, col]
            ax.scatter([p['time_s'] for p in pp], [p['graph_gauge_CFO_Hz']/1000 for p in pp],
                s=12, marker='x', color='#bbbbbb', alpha=.6, label='Archived other peak (same probe)')
            ax.scatter([p['time_s'] for p in ww], [p['graph_gauge_CFO_Hz']/1000 for p in ww],
                s=15, color='#333333', label='Native GLRT winner')
            for j, tr in enumerate(tt):
                rr = [p for p in track_rows if p['component'] == tr['key']]
                label = tr['key'].split('-RX2-')[1].split('-RF')[0]
                ax.plot([p['time_s'] for p in rr], [p['common_graph_gauge_CFO_Hz']/1000 for p in rr],
                    '.-', ms=5, lw=2 if tr is selected[ch] else .8, color=colors(j), label=label)
            aa = [p for p in ww if p['baseline_accepted']]
            ax.scatter([p['time_s'] for p in aa], [p['graph_gauge_CFO_Hz']/1000 for p in aa],
                s=42, facecolors='none', edgecolors='#1b824d', label='Baseline accepted')
            ax.set(xlabel='Scan time (s)', ylabel='CFO in common native −2-period gauge (kHz)',
                title=f'RX2 CH{ch}: '+('all archived peaks' if col == 0 else 'selected-source detail'))
            ax.set_xlim(*WINDOWS[ch]);ax.grid(alpha=.2)
            if col:
                y = np.asarray(selected[ch]['values']) / 1000
                ax.set_ylim(y.min()-10, y.max()+10)
            ax.legend(fontsize=7, loc='best')
        source_rows = [p for p in ww if p['selected_source']]
        gaps = np.diff(selected[ch]['times'])
        summary.append(dict(channel=ch, selected_component=selected[ch]['key'],
            whole_source_points=len(selected[ch]['observation_ids']), window=WINDOWS[ch],
            local_probes=sum(p['channel']==ch for p in probes), local_native_winners=len(ww),
            local_selected_source_points=len(source_rows), local_archived_other_peaks=len(pp),
            local_other_peak_gate_passes=sum(p['passed_original_fractional_gate'] is True for p in pp),
            local_probes_without_winner=sum(p['channel']==ch and not p['winner_native_id'] for p in probes),
            local_other_graph_owners=[t['key'] for t in tt if t is not selected[ch]],
            complete_source_final_gap_s=float(gaps[-1]), complete_source_largest_gap_s=float(gaps.max()),
            complete_native_IDs=selected[ch]['observation_ids']))
    fig.suptitle('Original native GLRT and graph ownership: no new extraction or reassignment\n'
        'Same −2-period shift for every winner/peak; additional peaks are not independent observations')
    fig.savefig(HERE/'native_ownership.png', dpi=150);fig.savefig(HERE/'native_ownership.pdf');plt.close(fig)
    csv_write('native_winners.csv', local_winners);csv_write('archived_peaks.csv', peaks)
    csv_write('probes.csv', probes);csv_write('graph_points.csv', track_rows)
    assert all(sha(p)==h for p,h in protocol['files'].items())
    assert time.monotonic()-began < 180
    write('results.json', dict(rows=summary, seconds=time.monotonic()-began,
        native_winner_count=len(public), full_graph_ownership_verified=True, raw_receiver_index=1,
        public_receiver=2, selection_exposed=True, graph_gauge_Hz=-2*PERIOD,
        source_protocol_sha256=sha(HERE/'protocol.json'), no_new_RF=True, no_position_fits=True,
        no_orbit_scores=True, GPS_used=False, observation_policy=public_meta['observation_policy']))
    write('seal.json',dict(files={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name!='seal.json'}))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true')
    freeze() if parser.parse_args().freeze else run()
