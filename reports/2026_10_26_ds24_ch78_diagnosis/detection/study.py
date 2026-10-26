"""External bounded known-signal injection; historical public ports only."""
import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = Path('/srv/bulk/leo/research/ds24-detector-response-r01')
TRACK = Path('/srv/bulk/leo/research/ds25-20261024')
SOURCES = {'DS24-0010':'fast-77d304bf1cf7d0722413d664ebf1d9e6',
           'DS24-0011':'fast-b5a96b6edc76f7e6a5f0bf9017bab253'}
GRID = [-24, -18, -12, -6]
EPOCH = 4321.25
CFO = 213456.75


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


replay = module('historical_detection_replay', PRIOR/'recorded/replay.py')


def dump(p, x):
    Path(p).write_text(json.dumps(x, indent=2, allow_nan=False)+'\n')


def analytic(size, rate, edge, *, epoch=EPOCH, cfo=CFO, roll=0):
    """Evaluate continuous-time published pilot directly, no sampled template."""
    from leo.analysis.starlink.templates import qin_edge_pilot_states
    indexes = np.arange(528, 536) if edge == 'lower' else np.arange(488, 496)
    signed = np.where(indexes < 512, indexes, indexes-1024)
    frequencies = (signed-signed.mean())*234375.
    states = qin_edge_pilot_states(edge, symbol_roll=roll)
    t = np.arange(size, dtype=float)/rate
    frame_time = np.mod(t-epoch/rate, 1/750.)
    symbol = np.floor(frame_time/4.4e-6).astype(int)
    valid = (symbol >= 2)&(symbol <= 301)
    local = frame_time[valid]-symbol[valid]*4.4e-6-2/15*1e-6
    output = np.zeros(size, dtype=np.complex128)
    active = np.zeros(len(local), complex)
    for tone, f in enumerate(frequencies):
        phase = .5*np.pi*(states[symbol[valid]-2, tone].astype(float)+.5)
        active += np.exp(1j*phase+2j*np.pi*f*local)/np.sqrt(8)
    output[valid] = active
    return output*np.exp(2j*np.pi*cfo*t+.37j)


def injection(background, waveform, db):
    power = float(np.mean(abs(background)**2))
    unit_power = float(np.mean(abs(waveform)**2))
    amplitude = np.sqrt(power*10**(db/10)/unit_power)
    return background+amplitude*waveform, dict(background_mean_complex_power_native=power,
        injection_mean_complex_power_native=amplitude**2*unit_power,
        waveform_scale_native=float(amplitude), pilot_to_background_db=db)


def truth_error(candidate, rate):
    epoch = candidate['integer_epoch_sample']+candidate['fractional_epoch_offset_samples']
    frame = rate/750.
    timing = (epoch-EPOCH+frame/2)%frame-frame/2
    return dict(timing_error_samples=float(timing), cfo_error_hz=candidate['fractional_tracking_cfo_hz']-CFO)


def evaluate(window, receiver_ids, label, db, background):
    from leo.scanner.fast_scan_analysis import production_glrt
    from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
    start = time.monotonic()
    wave = analytic(len(background), window.sample_rate_hz, window.target['edge'])
    injected = np.empty(background.shape, complex)
    powers = []
    for i in range(background.shape[1]):
        if db is None:
            injected[:, i] = background[:, i]
            powers.append(dict(background_mean_complex_power_native=float(np.mean(abs(background[:, i])**2))))
        else:
            injected[:, i], power = injection(background[:, i], wave, db)
            powers.append(power)
    iq = np.stack((injected.real, injected.imag), axis=-1)
    changed = dataclasses.replace(window, samples=iq)
    detection = replay.exported(production_glrt(changed, receiver_ids))
    rows = []
    for i, rx in enumerate(receiver_ids):
        # Exact identical complex64 data representation used by production_glrt.
        values = injected[:, i].astype(np.complex64)
        anchor = conditioned_glrt64_score(values, window.sample_rate_hz,
            epoch_sample=int(EPOCH), fractional_epoch_offset_samples=EPOCH-int(EPOCH),
            acquired_cfo_hz=CFO, edge=window.target['edge'])
        candidates = [dict(**c, **truth_error(c, window.sample_rate_hz)) for c in detection.get(rx, [])]
        recovered = [c for c in candidates if c['passed_fractional_margin_gate']
            and abs(c['timing_error_samples']) <= 2 and abs(c['cfo_error_hz']) <= 100]
        nearest = min(candidates, key=lambda c: abs(c['timing_error_samples'])/2+abs(c['cfo_error_hz'])/100, default=None)
        rows.append(dict(label=label, receiver=rx+1, native_receiver_id=rx, channel=window.target['channel'],
            edge=window.target['edge'], strength_db=db, **powers[i], candidates=candidates,
            blind_recovered=bool(recovered), anchor=dataclasses.asdict(anchor),
            anchor_pass=bool(anchor.margin >= .025), nearest_candidate=nearest,
            any_gatepass=any(c['passed_fractional_margin_gate'] for c in candidates),
            unclaimed_passing_candidates=sum(c['passed_fractional_margin_gate'] for c in candidates)-len(recovered)))
    return dict(rows=rows, seconds=time.monotonic()-start)


def prepare():
    if (HERE/'protocol.json').exists() and not (HERE/'protocol_attempt01.json').exists():
        raise FileExistsError('freeze already exists')
    metadata = module('detection_metadata_port', PRIOR/'influence/raw_metadata.py')
    slots = []
    input_paths = []
    for case, source_id in SOURCES.items():
      track_path = TRACK/case/'tracking.json'
      source_path = Path('/srv/bulk/leo/fast-scan-inputs')/(source_id+'.json')
      input_paths.extend([track_path, source_path])
      tracking = read(track_path)
      probes = tracking['source']['probes']
      midpoint = (min(p['valid_start_counter'] for p in probes)+max(p['valid_start_counter'] for p in probes))/2
      for ch in [1, 4, 7, 8]:
        chosen = min((p for p in probes if p['channel'] == ch and p['receiver_id'] == 0),
                     key=lambda p: (abs(p['valid_start_counter']-midpoint), p['visit_index']), default=None)
        if chosen is None:
            slots.append(dict(channel=ch, status='missing', reason='no RX0 processed probe'))
            continue
        probe = dict(chosen, duration_samples=200000, window_start_counter=chosen['valid_start_counter'])
        slot = dict(request_id=f'{case}-CH{ch}', case=case, channel=ch, probe=probe,
            sample_rate_hz=tracking['source']['sample_rate_hz'], tracking=dict(path=str(track_path), sha256=sha(track_path)),
            source_input=dict(path=str(source_path), sha256='sha256:'+sha(source_path)), status='nominated')
        try:
            slot['raw_authority'] = metadata.one(slot)
        except Exception as exc:
            slot.update(status='missing', reason=repr(exc))
        slots.append(slot)
    identity = replay.runtime_identity()
    auth = read(PRIOR/'recorded/authority.json')
    for case in SOURCES:
        record = next(r for r in auth['records'] if r['case'] == case)
        if not record['identity_matches'] or record['runtime_identity'] != [identity['code_digest'], identity['environment_digest']]:
            raise ValueError('historical runtime identity mismatch')
    dump(HERE/'panel.json', dict(cases=list(SOURCES), selection='nearest processed-scan midpoint per channel, no candidate outcome',
        requested_channels=[1, 4, 7, 8], requested_receivers=[0, 1], slots=slots))
    dump(HERE/'protocol.json', dict(schema='ch78-detection-injection/v1', frozen_utc_ns=time.time_ns(),
        files={str(p):sha(p) for p in [HERE/'PROTOCOL.md', HERE/'panel.json', HERE/'study.py']+input_paths},
        identity=identity, grid_db=GRID, epoch_samples=EPOCH, cfo_hz=CFO,
        truth_tolerances=dict(timing_samples=2, cfo_hz=100), IQ_reads_before_freeze=0,
        process_alarm_seconds=580, BLAS_threads=1, no_new_RF=True, no_GPS=True))
    print(json.dumps(dict(frozen=True, panel=sha(HERE/'panel.json'), slots=[(s['channel'],s['status']) for s in slots])))


def opened(slot):
    from leo.storage.fast_scan import FastSegmentSource
    from leo.scanner.fast_scan_analysis import production_glrt
    a = slot['raw_authority']
    if 'sha256:'+sha(a['index_path']) != a['index_sha256']:
        raise ValueError('index changed')
    source = FastSegmentSource(a['segment'], start_sequence=a['local_sequence'], stop_sequence=a['local_sequence']+1)
    window = replay.exhaust_one(source)
    if window.iq_sha256 != a['index']['iq_sha256'] or window.acquisition != a['index']['acquisition'] or window.target != a['target']:
        raise ValueError('window public authority mismatch')
    expected = {p['receiver_id']:p['candidates'] for p in read(slot['tracking']['path'])['source']['probes']
        if p['visit_index'] == slot['probe']['visit_index'] and p['probe_index'] == 0}
    began = time.monotonic()
    actual = replay.exported(production_glrt(window, source.receiver_ids))
    parity = {str(rx):replay.compare(expected[rx], actual.get(rx, [])) for rx in expected}
    if set(expected) != set(source.receiver_ids) or not all(v['all_passed'] for v in parity.values()):
        raise ValueError('historical paired candidate parity failed')
    background = window.samples[:, :, 0].astype(float)+1j*window.samples[:, :, 1].astype(float)
    return window, source.receiver_ids, background, dict(parity=parity, full_reader_exhausted=True,
        IQ_sha256=window.iq_sha256, parity_detector_seconds=time.monotonic()-began)


def run(probe=False):
    for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
        if os.environ.get(key) != '1':
            raise ValueError('BLAS1 required')
    protocol = read(HERE/'protocol.json')
    for p, h in protocol['files'].items():
        if sha(p) != h:
            raise ValueError('frozen source changed: '+p)
    if replay.runtime_identity() != protocol['identity']:
        raise ValueError('historical runtime changed')
    def timeout(*_):
        raise TimeoutError('580-second process bound')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(580)
    began = time.monotonic()
    results = []
    slots = read(HERE/'panel.json')['slots']
    if probe:
        slots = slots[:1]
    for slot in slots:
        item = dict(request_id=slot.get('request_id'), channel=slot['channel'], status='missing', outcomes=[])
        try:
            if slot['status'] != 'nominated':
                raise ValueError(slot['reason'])
            window, ids, background, receipt = opened(slot)
            item.update(status='complete', receipt=receipt)
            if not probe:
                for strength in [None]+GRID:
                    item['outcomes'].append(evaluate(window, ids, 'recorded', strength, background))
                    print(slot['request_id'], strength, 'done', file=sys.stderr, flush=True)
                # Independent synthetic noise at equal per-RX reference power.
                rng = np.random.default_rng(813260)
                if slot['channel'] == 1:
                    noise = (rng.normal(size=background.shape)+1j*rng.normal(size=background.shape))/np.sqrt(2)
                    for i in range(len(ids)):
                        noise[:, i] *= np.sqrt(np.mean(abs(background[:, i])**2))
                    for strength in [None]+GRID:
                        item['outcomes'].append(evaluate(window, ids, 'clean_noise', strength, noise))
                    wrong = analytic(len(background), window.sample_rate_hz, window.target['edge'], roll=17)
                    wrong_bg = np.column_stack([injection(noise[:, i], wrong, -6)[0] for i in range(len(ids))])
                    item['outcomes'].append(evaluate(window, ids, 'wrong_sequence', None, wrong_bg))
        except Exception as exc:
            item.update(status='failed', error=repr(exc))
        results.append(item)
        dump(HERE/('probe.json' if probe else 'results.json'), dict(protocol_sha256=sha(HERE/'protocol.json'),
            rows=results, seconds=time.monotonic()-began, runtime_identity_unchanged=replay.runtime_identity()==protocol['identity']))
    signal.alarm(0)
    print(json.dumps(dict(seconds=time.monotonic()-began, completed=sum(r['status']=='complete' for r in results), total=len(slots))))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'probe', 'run'])
    args = p.parse_args()
    prepare() if args.action == 'prepare' else run(args.action == 'probe')
