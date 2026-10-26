"""Earlier-only natural revisit forecasts; unchanged public historical ports."""
import argparse
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import time

import numpy as np

HERE = Path(__file__).resolve().parent
TRACK = Path('/srv/bulk/leo/research/ds25-20261024')
PRIOR = Path('/srv/bulk/leo/research/ds24-ch78-diagnosis-r02/detection')
CHANNELS = [1, 4, 5, 6, 7, 8]
CASES = [f'DS24-{i:04}' for i in range(10, 14)]
HALF = 100000


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def wrap(value, period):
    return (value + period / 2) % period - period / 2


def epoch(candidate):
    return candidate['integer_epoch_sample'] + candidate['fractional_epoch_offset_samples']


def donors(probe, rate):
    """Original-rank selection and duplicate removal, never score ordering."""
    accepted = []
    for c in sorted(probe['candidates'], key=lambda x: x['candidate_rank']):
        if not 0 <= c['candidate_rank'] <= 8 or not c['passed_fractional_margin_gate']:
            continue
        if c['fractional_margin'] < .025:
            raise ValueError('inconsistent persisted donor margin')
        if not any(abs(wrap(epoch(c) - epoch(a), rate / 750)) <= 2 and
                   abs(c['fractional_tracking_cfo_hz'] - a['fractional_tracking_cfo_hz']) <= 200
                   for a in accepted):
            accepted.append(c)
    return accepted[:8]


def scalar_fit(times, values, horizon, floor, allowance):
    x = np.column_stack((np.ones(len(times)), np.asarray(times)))
    y = np.asarray(values)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ beta
    design = np.array([1., horizon])
    leverage = float(design @ np.linalg.inv(x.T @ x) @ design)
    rms = float(np.sqrt(np.mean(residual ** 2)))
    scale = max(floor, rms) * math.sqrt(1 + leverage) + allowance * horizon
    return dict(value=float(design @ beta), intercept=float(beta[0]), rate_per_s=float(beta[1]),
                residual_rms=rms, heuristic_half_width_3scale=3 * scale, leverage=leverage)


def forecast(header, earlier):
    """Only target metadata headers and strictly earlier measurements are read."""
    rate = header['sample_rate_hz']
    period = rate / 750
    if len(earlier) != 3:
        return dict(status='insufficient_earlier_visits', modes=[], primary_mode=None)
    if any(p['valid_start_counter'] >= header['target_start_counter'] or
           p['receiver_id'] != header['receiver_id'] or p['channel'] != header['channel'] or
           p['edge'] != header['edge'] for p in earlier):
        raise ValueError('donor causality or cell ownership violation')
    if len({p['valid_start_counter'] for p in earlier}) != 3:
        raise ValueError('duplicate donor visit')
    earlier = sorted(earlier, key=lambda x: x['valid_start_counter'])
    latest = earlier[-1]
    delta = header['target_start_counter'] - latest['valid_start_counter']
    horizon = delta / rate
    modes = []
    for seed in donors(latest, rate):
        mode = dict(seed_rank=seed['candidate_rank'], status='unavailable', donor_ranks=[],
                    donor_counters=[], horizon_s=horizon, match_counts=[])
        matched = []
        for probe in earlier[:-1]:
            candidates = [c for c in donors(probe, rate) if
                abs(wrap(epoch(c) + (probe['valid_start_counter'] - latest['valid_start_counter'])
                         - epoch(seed), period)) <= 64 and
                abs(c['fractional_tracking_cfo_hz'] - seed['fractional_tracking_cfo_hz']) <= 5000]
            mode['match_counts'].append(len(candidates))
            if len(candidates) == 1:
                matched.append(candidates[0])
        if any(n > 1 for n in mode['match_counts']):
            mode['status'] = 'ambiguous_earlier_matches'
        elif len(matched) != 2:
            mode['status'] = 'missing_earlier_matches'
        else:
            matched.append(seed)
            counters = [p['valid_start_counter'] for p in earlier]
            times = [(c - counters[-1]) / rate for c in counters]
            phases = [wrap(epoch(c) + (count - counters[-1]) - epoch(seed), period)
                      for c, count in zip(matched, counters)]
            timing = scalar_fit(times, phases, horizon, .5, 5.)
            frequency = scalar_fit(times, [c['fractional_tracking_cfo_hz'] for c in matched],
                                   horizon, 50., 200.)
            mode.update(status='complete', donor_ranks=[c['candidate_rank'] for c in matched],
                        donor_counters=counters, donor_times_relative_latest_s=times,
                        donor_phase_samples=phases,
                        donor_CFO_hz=[c['fractional_tracking_cfo_hz'] for c in matched],
                        constant=dict(epoch_samples=float((epoch(seed) - delta) % period),
                                      CFO_hz=seed['fractional_tracking_cfo_hz']),
                        linear=dict(epoch_samples=float((epoch(seed) - delta + timing['value']) % period),
                                    CFO_hz=frequency['value']), timing_fit=timing, CFO_fit=frequency)
        modes.append(mode)
    good = [i for i, m in enumerate(modes) if m['status'] == 'complete']
    return dict(status='available' if good else 'no_unambiguous_three_visit_mode', modes=modes,
                primary_mode=good[0] if good else None, no_target_responses_used=True,
                heuristic_uncertainty_not_calibrated=True)


def prepare():
    old = module('fixed_historical_r02', PRIOR / 'study.py')
    metadata = module('fixed_public_metadata', old.PRIOR / 'influence/raw_metadata.py')
    files = {str(HERE / p): sha(HERE / p) for p in ['PROTOCOL.md', 'study.py', 'test_study.py']}
    slots = []
    for case in CASES:
        path = TRACK / case / 'tracking.json'
        data = load(path)
        probes = data['source']['probes']
        source_path = Path('/srv/bulk/leo/fast-scan-inputs') / (data['source']['session_id'] + '.json')
        files.update({str(path): sha(path), str(source_path): sha(source_path)})
        midpoint = (min(p['valid_start_counter'] for p in probes) +
                    max(p['valid_start_counter'] for p in probes)) / 2
        for channel in CHANNELS:
            visits = sorted([p for p in probes if p['receiver_id'] == 0 and p['channel'] == channel],
                            key=lambda p: p['valid_start_counter'])
            nearest = min(range(len(visits)), key=lambda i: (abs(visits[i]['valid_start_counter'] - midpoint),
                                                            visits[i]['visit_index']))
            chosen = visits[nearest:nearest + 2]
            for ordinal in range(2):
                slot = dict(request_id=f'{case}-CH{channel}-T{ordinal}', case=case, channel=channel,
                            target_ordinal=ordinal, status='missing', cells=[])
                if ordinal >= len(chosen):
                    slot['reason'] = 'second chronological target unavailable'
                    slots.append(slot)
                    continue
                p = chosen[ordinal]
                same = sorted([q for q in probes if q['channel'] == channel and q['edge'] == p['edge']],
                              key=lambda q: q['valid_start_counter'])
                slot.update(status='nominated', probe=dict(p, duration_samples=200000,
                    window_start_counter=p['valid_start_counter']), sample_rate_hz=data['source']['sample_rate_hz'],
                    tracking=dict(path=str(path), sha256=sha(path)),
                    source_input=dict(path=str(source_path), sha256='sha256:' + sha(source_path)))
                try:
                    slot['raw_authority'] = metadata.one(slot)
                except Exception as exc:
                    slot.update(status='missing', reason=repr(exc))
                for rx in [0, 1]:
                    target = next((q for q in same if q['visit_index'] == p['visit_index'] and q['receiver_id'] == rx), None)
                    earlier = [q for q in same if q['receiver_id'] == rx and q['valid_start_counter'] < p['valid_start_counter']][-3:]
                    header = dict(request_id=slot['request_id'], case=case, channel=channel, edge=p['edge'],
                                  receiver_id=rx, sample_rate_hz=slot['sample_rate_hz'],
                                  target_start_counter=p['valid_start_counter'], target_visit_index=p['visit_index'])
                    slot['cells'].append(dict(header=header, earlier=earlier, target_original=target,
                                              original_fullwindow_acquisition_exposed=True))
                slots.append(slot)
    write(HERE / 'panel.json', dict(schema='natural-revisit-panel/v1', cases=CASES, channels=CHANNELS,
                                   target_windows=48, receiver_cells=96, slots=slots,
                                   selection='metadata-only nearest midpoint then next chronological visit'))
    files[str(HERE / 'panel.json')] = sha(HERE / 'panel.json')
    for path in [PRIOR / 'study.py', old.PRIOR / 'recorded/replay.py', old.PRIOR / 'influence/raw_metadata.py']:
        files[str(path)] = sha(path)
    identity = old.replay.runtime_identity()
    auth = load(old.PRIOR / 'recorded/authority.json')
    for record in auth['records']:
        if not record['identity_matches'] or record['runtime_identity'] != [identity['code_digest'], identity['environment_digest']]:
            raise ValueError('historical runtime identity mismatch')
    write(HERE / 'protocol.json', dict(schema='natural-revisit-study/v1', frozen_utc_ns=time.time_ns(), files=files,
        identity=identity, IQ_reads_before_freeze=0, numerical_outcomes_before_freeze=0,
        process_alarm_seconds=580, BLAS_threads=1, no_new_RF=True, no_GPS=True,
        earlier_matching_gates=dict(timing_samples=64, CFO_hz=5000), maximum_seed_modes=8,
        source_case_identity_verified_by_original_parity=True))
    print('frozen', sha(HERE / 'protocol.json'), flush=True)


def checked_protocol():
    for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
        if os.environ.get(key) != '1':
            raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('580-second process bound')))
    signal.alarm(580)
    protocol = load(HERE / 'protocol.json')
    for path, digest in protocol['files'].items():
        if sha(path) != digest:
            raise ValueError('frozen source changed: ' + path)
    return protocol


def predict():
    checked_protocol()
    rows = [dict(**cell['header'], forecast=forecast(cell['header'], cell['earlier']))
            for slot in load(HERE / 'panel.json')['slots'] for cell in slot['cells']]
    write(HERE / 'predictions.json', dict(protocol_sha256=sha(HERE / 'protocol.json'),
        panel_sha256=sha(HERE / 'panel.json'), rows=rows, no_target_responses_used=True))
    print('predictions', len(rows), sha(HERE / 'predictions.json'), flush=True)


def score_half(values, rate, edge, prediction, offset):
    from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
    ep = (prediction['epoch_samples'] - offset) % (rate / 750)
    result = conditioned_glrt64_score(values, rate, epoch_sample=math.floor(ep),
        fractional_epoch_offset_samples=ep - math.floor(ep), acquired_cfo_hz=prediction['CFO_hz'], edge=edge)
    return dataclasses.asdict(result)


def run():
    began = time.monotonic()
    protocol = checked_protocol()
    old = module('frozen_historical_opener', PRIOR / 'study.py')
    if old.replay.runtime_identity() != protocol['identity']:
        raise ValueError('historical runtime changed')
    predictions = load(HERE / 'predictions.json')
    by_key = {(r['request_id'], r['receiver_id']): r for r in predictions['rows']}
    rows = []
    for slot in load(HERE / 'panel.json')['slots']:
        row = dict(request_id=slot['request_id'], case=slot['case'], channel=slot['channel'],
                   status='not_attempted', cells=[])
        try:
            if time.monotonic() - began > 540:
                raise TimeoutError('remaining process budget reserved for final receipt')
            if slot['status'] != 'nominated':
                raise ValueError(slot['reason'])
            window, ids, background, receipt = old.opened(slot)
            row.update(status='complete', parity=receipt)
            for rx_index, rx in enumerate(ids):
                pred = by_key[(slot['request_id'], rx)]
                outcomes = []
                for mode_index, mode in enumerate(pred['forecast']['modes']):
                    if mode['status'] != 'complete':
                        continue
                    outcome = dict(mode_index=mode_index, seed_rank=mode['seed_rank'], variants={})
                    for variant in ['constant', 'linear']:
                        halves = [score_half(background[start:start + HALF, rx_index].astype(np.complex64),
                            window.sample_rate_hz, window.target['edge'], mode[variant], start) for start in [0, HALF]]
                        outcome['variants'][variant] = dict(halves=halves,
                            both_pass=all(h['margin'] >= .025 for h in halves),
                            CFO_difference_hz=abs(halves[0]['tracking_cfo_hz'] - halves[1]['tracking_cfo_hz']),
                            independent_support_consistent=all(h['margin'] >= .025 for h in halves) and
                                abs(halves[0]['tracking_cfo_hz'] - halves[1]['tracking_cfo_hz']) <= 100)
                    outcomes.append(outcome)
                row['cells'].append(dict(receiver_id=rx, forecast_status=pred['forecast']['status'],
                                         primary_mode=pred['forecast']['primary_mode'], outcomes=outcomes))
        except Exception as exc:
            row.update(status='failed', error=repr(exc))
        rows.append(row)
        checkpoint = dict(protocol_sha256=sha(HERE / 'protocol.json'), predictions_sha256=sha(HERE / 'predictions.json'),
            rows=rows, seconds=time.monotonic() - began,
            runtime_identity_unchanged=old.replay.runtime_identity() == protocol['identity'])
        (HERE / 'checkpoint.json').write_text(json.dumps(checkpoint, indent=2, allow_nan=False) + '\n')
        print(slot['request_id'], row['status'], round(time.monotonic() - began, 2), flush=True)
    write(HERE / 'results.json', checkpoint)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'predict', 'run'])
    action = parser.parse_args().action
    {'prepare': prepare, 'predict': predict, 'run': run}[action]()
