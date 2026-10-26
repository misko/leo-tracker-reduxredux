"""Saved-export adapters, frozen RF path execution and original graph diagnostics."""
import time
STARTED = time.monotonic()
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import unittest
import numpy as np
import continuity as c

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OLD = Path('/srv/bulk/leo/research/ds24-measurement-continuity-r01/measurement')
CONFIG = REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json'
RATE = 10_000_000
PRIOR_PREPARATION_SECONDS = 2.0  # Conservative charge for preserved order-only fixture failure.


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def default(v):
    if isinstance(v, np.ndarray): return v.tolist()
    if isinstance(v, np.generic): return v.item()
    raise TypeError(type(v).__name__)


def write(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False, default=default)+'\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def identity(text):
    return 'sha256:'+hashlib.sha256(text.encode()).hexdigest()


def prepare_port():
    dedup = load_module('continuity_dedup', REPO/'tools/ds23_frame_registration.py')
    protocol = json.loads((OLD/'protocol.json').read_text()); episodes = []
    for spec in protocol['sequences']:
        name = spec['name']+'_'+spec['law']; windows = []; raw_ledger = []
        for i in range(16):
            slot = json.loads((OLD/'slots'/f'{name}_{i:02}.json').read_text())
            if slot['status'] != 'complete':
                raise ValueError('frozen input unavailable')
            start = round(slot['time_s']*RATE)
            for rx in slot['receivers']:
                receiver = int(rx['receiver_id']); wid = identity(f'{name}:RX{receiver}:{start}')
                original = identity(f'synthetic:{name}:RX{receiver}:visit{i}')
                w = dict(window_id=wid, observation_id=original,
                    physical_acquisition_id=identity(f'{name}:{start}'), receiver_id=str(receiver),
                    channel=1, actual_rf_hz=10940312500., time_s=slot['time_s']+.01,
                    sample_rate_hz=RATE, window_start_counter=start, origin_counter=0,
                    duration_samples=200000, candidates=[])
                exported = []
                for peak in rx['candidates']:
                    complete = peak['fractional_epoch_status'] == 'complete' and all(peak[k] is not None for k in
                        ('fractional_epoch_offset_samples', 'fractional_tracking_cfo_hz', 'fractional_exact_score',
                         'fractional_control_score', 'fractional_margin'))
                    if complete:
                        exported.append(dict(candidate_rank=peak['candidate_rank'], integer_epoch_sample=peak['epoch_sample'],
                            fractional_epoch_offset_samples=peak['fractional_epoch_offset_samples'],
                            fractional_tracking_cfo_hz=peak['fractional_tracking_cfo_hz'],
                            fractional_margin=peak['fractional_margin'], passed_fractional_margin_gate=peak['fractional_margin'] >= .025))
                exported.sort(key=lambda x: x['candidate_rank'])
                retained = dedup.unique_peaks(exported, RATE)
                for peak in retained:
                    native = next(x for x in rx['candidates'] if x['candidate_rank'] == peak['rank'])
                    w['candidates'].append(dict(candidate_id=identity(wid+':rank'+str(peak['rank'])),
                        candidate_rank=peak['rank'], cfo_hz=peak['cfo'], margin=peak['margin'],
                        local_epoch_samples=peak['epoch'], global_epoch_samples=c.global_epoch(start, 0, peak['epoch'], RATE),
                        acquired_cfo_hz=native['acquired_cfo_hz']))
                kept = {x['candidate_rank'] for x in w['candidates']}
                raw_ledger.append(dict(window_id=wid, observation_id=original, raw_candidates=rx['candidates'],
                    retained_candidate_ranks=sorted(kept), excluded_ranks=[x['candidate_rank'] for x in rx['candidates']
                                                                        if x['candidate_rank'] not in kept]))
                windows.append(w)
        windows.sort(key=lambda w: (w['receiver_id'], w['channel'], w['actual_rf_hz'], w['time_s']))
        for rx in ('0', '1'):
            c.validate([w for w in windows if w['receiver_id'] == rx], RATE)
        episodes.append(dict(name=name, windows=windows, raw_ledger=raw_ledger))
    return dict(schema='rf-candidate-windows/v1', sample_rate_hz=RATE, frame_rate_hz=750,
                synthetic_clock=True, episodes=episodes)


def graph_for(windows, selected, name):
    port = load_module('continuity_original_graph', REPO/'tools/evaluate_ds22_merged_tracks.py')
    from leo.analysis.polynomial_tracklets import TrackConfig
    cfg = TrackConfig(**json.loads(CONFIG.read_text())['config'])
    by_candidate = {candidate['candidate_id']:w for w in windows for candidate in w['candidates']}
    rows = []
    for node in selected:
        w = by_candidate[node['candidate_id']]
        rows.append(dict(observation_id=w['observation_id'], native_receiver_id=w['receiver_id'],
            receiver=int(w['receiver_id'])+1, channel=w['channel'], actual_rf_hz=w['actual_rf_hz'],
            time_s=w['time_s'], measured_cfo_hz=node['cfo_hz'], fractional_margin=node['margin'],
            candidate_id=node['candidate_id'], candidate_rank=node['candidate_rank'], window_id=w['window_id']))
    rows.sort(key=lambda x: (x['receiver'], x['time_s']))
    tracks, assigned = port.graph_tracks(rows, name, cfg)
    return dict(rows=rows, tracks=tracks, assigned=assigned,
                independent_source_evidence=False, original_quality_gates=True)


def prepare():
    seal = json.loads((OLD/'RF_seal.json').read_text())
    for p, digest in seal['files'].items():
        if sha(p) != digest: raise ValueError('old frozen input changed: '+p)
    port = prepare_port(); write(HERE/'prepared/synthetic_rows.json', port)
    for episode in port['episodes']:
        old = json.loads((OLD/'graphs'/f"{episode['name']}.json").read_text())['actual']
        winners = []
        for rx in ('0', '1'):
            wins = [w for w in episode['windows'] if w['receiver_id'] == rx]
            winners += c.winner_rows(wins)
        reconstructed = graph_for(episode['windows'], winners, episode['name'])
        if reconstructed['rows']:
            a = [(r['observation_id'], r['time_s'], r['measured_cfo_hz']) for r in reconstructed['rows']]
            b = [(r['observation_id'], r['time_s'], r['measured_cfo_hz']) for r in old['rows']]
            if a != b or reconstructed['assigned'] != old['assigned']:
                raise ValueError('actual original-winner/graph port mismatch')
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_continuity.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise RuntimeError('owned test failure')
    write(HERE/'preparation.json', dict(all_passed=True, seconds=time.monotonic()-STARTED+PRIOR_PREPARATION_SECONDS,
        prior_failed_fixture_seconds_charged=PRIOR_PREPARATION_SECONDS,
        source_raw_candidates=sum(len(w['raw_candidates']) for e in port['episodes'] for w in e['raw_ledger']),
        gated_dedup_candidates=sum(len(w['candidates']) for e in port['episodes'] for w in e['windows']),
        windows=sum(len(e['windows']) for e in port['episodes']), tests_run=result.testsRun,
        old_winner_graph_parity=True, new_detector_calls=0, truth_fields_used_by_adapter=False))


def freeze():
    if (HERE/'protocol.json').exists(): raise FileExistsError('already frozen')
    files = [HERE/'continuity.py', HERE/'experiment.py', HERE/'test_continuity.py', HERE/'PROTOCOL.md',
        HERE/'preparation.json', HERE/'prepared/synthetic_rows.json', HERE.parent/'COORDINATOR_PLAN.md',
        CONFIG, REPO/'tools/ds23_frame_registration.py', REPO/'tools/evaluate_ds22_merged_tracks.py',
        REPO/'src/leo/analysis/graph_tracklets.py', REPO/'src/leo/analysis/polynomial_tracklets.py',
        REPO/'src/leo/analysis/tracklet_fitting.py', OLD/'RF_seal.json']
    files += [HERE.parent/'prototype_preparation.log', HERE.parent/'prototype_preparation02.log']
    files += sorted((OLD/'slots').glob('*.json'))
    files += [OLD/'graphs'/f"{e['name']}.json" for e in json.loads((HERE/'prepared/synthetic_rows.json').read_text())['episodes']]
    write(HERE/'protocol.json', dict(files={str(p): sha(p) for p in files}, settings=c.SETTINGS,
        methods=['original_winners', 'cfo_only', 'epoch_cfo'], numerical_budget_seconds=300.,
        preparation_seconds=json.loads((HERE/'preparation.json').read_text())['seconds'],
        workers=1, blas_threads=1, episodes=4, receiver_lanes=8, lane_method_slots=24,
        true_labels_for_selection=False, new_detector_calls=0, operational_acceptance=False))


def alarm(seconds):
    if seconds <= 0: raise TimeoutError('unchanged cumulative cap exhausted')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('frozen cumulative cap')))
    signal.setitimer(signal.ITIMER_REAL, seconds)


def run():
    if (HERE/'execution.json').exists(): raise FileExistsError('no reruns')
    protocol = json.loads((HERE/'protocol.json').read_text())
    for p, digest in protocol['files'].items():
        if sha(p) != digest: raise ValueError('frozen source/input changed: '+p)
    receipt = json.loads((HERE.parent/'audit/prototype_preflight.json').read_text())
    if not receipt['all_passed'] or receipt['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('exact B preflight required')
    deadline = STARTED+300.-protocol['preparation_seconds']
    port = json.loads((HERE/'prepared/synthetic_rows.json').read_text()); records = []
    for episode in port['episodes']:
        for rx in ('0', '1'):
            windows = [w for w in episode['windows'] if w['receiver_id'] == rx]
            for method in protocol['methods']:
                record = dict(episode=episode['name'], receiver_id=rx, method=method)
                began = time.monotonic()
                try:
                    alarm(deadline-time.monotonic())
                    if method == 'original_winners':
                        selected = c.winner_rows(windows)
                        result = dict(paths=[dict(nodes=selected, score=None)],
                            candidate_hypotheses_selected=len(selected), unique_receiver_windows=len(selected),
                            total_receiver_windows=len(windows), windows_without_selected_path=[w['window_id'] for w in windows if not w['candidates']])
                    else:
                        result = c.select_paths(windows, RATE, include_epoch=method == 'epoch_cfo')
                    path = HERE/'selections'/f"{episode['name']}_RX{rx}_{method}.json"
                    # Response-only path checkpoint before graph and any truth analysis.
                    write(path, result)
                    graph_results = [graph_for(windows, p['nodes'], f"{episode['name']}_RX{rx}_{method}_P{i}")
                                     for i, p in enumerate(result['paths'])]
                    graphpath = HERE/'graphs'/path.name; write(graphpath, graph_results)
                    record.update(status='complete', selection_file=str(path), selection_sha256=sha(path),
                                  graph_file=str(graphpath), graph_sha256=sha(graphpath))
                except Exception as exc:
                    record.update(status='failed', error=repr(exc))
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                record['worker_seconds'] = time.monotonic()-began
                records.append(record)
                write(HERE/'execution_partial.json', records)
    write(HERE/'execution.json', dict(records=records, total=24,
        completed=sum(r['status'] == 'complete' for r in records),
        run_seconds=time.monotonic()-STARTED,
        cumulative_worker_seconds=time.monotonic()-STARTED+protocol['preparation_seconds'],
        new_detector_calls=0, truth_evaluation_before_seal=False))
    files = [p for p in HERE.rglob('*') if p.is_file() and p.name != 'RF_seal.json'
             and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
    write(HERE/'RF_seal.json', dict(protocol_sha256=sha(HERE/'protocol.json'), all_selected_terminal=True,
        files={str(p): sha(p) for p in files}, new_detector_calls=0))
    print('TERMINAL '+json.dumps(json.loads((HERE/'execution.json').read_text())))


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('command', choices=('prepare', 'freeze', 'run'))
    args = a.parse_args(); {'prepare': prepare, 'freeze': freeze, 'run': run}[args.command]()
