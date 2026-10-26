"""Bounded synthetic detector-to-graph continuity experiment; no capture attestation."""
import time
STARTED = time.monotonic()
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OLD = Path('/srv/bulk/leo/research/ds24-cached-ambiguity-r01/iq')
AUTH = Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01')
CONFIG = REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json'
RATE = 10_000_000
COUNT = 200_000
PERIOD = RATE/750.
TIMES = tuple(float(x) for x in range(16))
SEED = 2026102801
NOISE_RMS = 300.
LAWS = ('sampled_deployed', 'sampled_right', 'continuous')
PRIOR_PREPARATION_SECONDS = 1.639935032
DEPLOYED = Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
DETECTOR_PYTHON = Path('/opt/leo-fast-auto/20261010-r1/venv/bin/python')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


authority = module('measurement_prior_pilot', OLD/'control.py')


def graph_port():
    return module('measurement_graph_port', REPO/'tools/evaluate_ds22_merged_tracks.py')


def detector_command(command, *args):
    env = dict(os.environ, PYTHONPATH=str(DEPLOYED), PYTHONDONTWRITEBYTECODE='1',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    return subprocess.run([str(DETECTOR_PYTHON), str(HERE/'experiment.py'), command, *args],
                          env=env, check=True, text=True, capture_output=True)


def detector_identity():
    import inspect
    from leo.processing.fast_scan import implementation_identity
    from leo.scanner import fast_scan_analysis, fast_scan_detector
    from leo.analysis.starlink import templates, fast_scan_scores
    code, environment = implementation_identity()
    if (code, environment) != (authority.CODE, authority.ENV):
        raise ValueError('deployed detector identity differs')
    modules = (fast_scan_analysis, fast_scan_detector, templates, fast_scan_scores)
    return dict(code_digest=code, environment_digest=environment,
                executable=str(DETECTOR_PYTHON), actual_imported_sources={
                    str(Path(inspect.getfile(m))): sha(inspect.getfile(m)) for m in modules})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=default, allow_nan=False)+'\n')


def config():
    from leo.analysis.polynomial_tracklets import TrackConfig
    return TrackConfig(**json.loads(CONFIG.read_text())['config'])


def frame(law):
    from leo.analysis.starlink.templates import qin_edge_pilot_frame
    if law == 'sampled_deployed':
        return qin_edge_pilot_frame(RATE, 'upper').astype(np.complex128)
    if law == 'sampled_right':
        return authority.pilot(np.arange(round(PERIOD)), 0.)
    raise ValueError(law)


def waveform(law, epoch, count=COUNT):
    """Integer epochs; sampled arms use rounded *frame* anchors, not fixed 13333 repeats."""
    if int(epoch) != epoch:
        raise ValueError('this frozen control supports integer epochs only')
    if law == 'continuous':
        return authority.pilot(np.arange(count), epoch)
    values = frame(law)
    out = np.zeros(count, np.complex128)
    for k in range(-2, int(np.ceil(count/PERIOD))+2):
        start = int(epoch)+round(k*PERIOD)
        left, right = max(0, start), min(count, start+len(values))
        if left < right:
            out[left:right] += values[left-start:right-start]
    return out


def noise(visit, closure=False):
    # Same child and all draw arrays for all laws/epoch scenarios at this visit.
    rng = np.random.default_rng(20261026 if closure else np.random.SeedSequence([SEED, visit]))
    return NOISE_RMS/np.sqrt(2)*(rng.normal(size=(COUNT, 2))+
                                1j*rng.normal(size=(COUNT, 2)))


def sources(t, epochs, closure=False, single=False):
    if closure:
        rows = [dict(name='A', cfo0=100000., rate=0., amplitude=1000., phase=.3,
                     epoch=epochs[0])]
        if not single:
            rows.append(dict(name='B', cfo0=103000., rate=0., amplitude=600., phase=-.8,
                             epoch=epochs[1]))
        return rows
    return [dict(name='A', cfo0=100000., rate=200., amplitude=1000.-400.*t/15,
                 phase=.3, epoch=epochs[0]),
            dict(name='B', cfo0=103000., rate=-200., amplitude=600.+400.*t/15,
                 phase=-.8, epoch=epochs[1])]


def carrier(source, absolute_time):
    t = np.asarray(absolute_time)
    return np.exp(1j*source['phase']+2j*np.pi*(source['cfo0']*t+.5*source['rate']*t*t))


def synthesize(law, t, specs, visit, pilots=None, closure=False):
    local = np.arange(COUNT)/RATE
    clean = np.zeros(COUNT, np.complex128)
    for s in specs:
        p = waveform(law, s['epoch']) if pilots is None else pilots[(law, s['epoch'])]
        clean += s['amplitude']*p*carrier(s, t+local)
    n = noise(visit, closure=closure)
    combined = clean[:, None]+n
    iq = np.stack((combined.real, combined.imag), axis=-1)
    clipped = int(np.count_nonzero((iq < -32768) | (iq > 32767)))
    if clipped:
        raise ValueError('synthetic ADC would clip')
    iq = np.rint(iq).astype('<i2')
    return iq, dict(iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
                    noise_sha256=hashlib.sha256(n.tobytes()).hexdigest(),
                    signal_power=float(np.mean(abs(clean)**2)), clipping_samples=clipped,
                    sources=specs, global_start_seconds=t)


def window(iq):
    meta = json.loads((AUTH/'replay_metadata.json').read_text())
    target = next(t for t in meta['segment_document']['configuration']['targets']
                  if t['target_id'] == meta['first_index']['target_id'])
    return SimpleNamespace(target=target, acquisition=dict(actual_if_center_hz=
        meta['first_index']['acquisition']['actual_if_center_hz']), samples=iq,
        sample_rate_hz=RATE)


def choose(candidates):
    # Same public policy; no fake qualified-capture/UTC authority is constructed.
    complete = [c for c in candidates if c['fractional_epoch_status'] == 'complete'
                and all(c[k] is not None for k in ('fractional_margin',
                    'fractional_epoch_offset_samples', 'fractional_tracking_cfo_hz',
                    'fractional_exact_score', 'fractional_control_score'))]
    eligible = [c for c in complete if c['fractional_margin'] >= .025]
    return max(eligible, key=lambda c: (c['fractional_margin'], -c['candidate_rank'])) if eligible else None


def observation_id(sequence, receiver, visit):
    return 'sha256:'+hashlib.sha256(f'synthetic:{sequence}:RX{receiver}:visit{visit}'.encode()).hexdigest()


def rows_from_slots(slots, sequence, acquired=False):
    rows = []
    for slot in slots:
        if slot['status'] != 'complete':
            continue
        for rx in slot['receivers']:
            c = choose(rx['candidates'])
            if c is None:
                continue
            receiver = int(rx['receiver_id'])
            rows.append(dict(observation_id=observation_id(sequence, receiver, slot['visit']),
                receiver=receiver+1, native_receiver_id=str(receiver), channel=1,
                time_s=slot['time_s']+.01, actual_rf_hz=10940312500.,
                measured_cfo_hz=c['acquired_cfo_hz'] if acquired else c['fractional_tracking_cfo_hz'],
                fractional_margin=c['fractional_margin'], candidate_rank=c['candidate_rank'],
                visit=slot['visit']))
    rows.sort(key=lambda r: (r['receiver'], r['channel'], r['time_s'], r['observation_id']))
    if len(rows) != len({r['observation_id'] for r in rows}):
        raise ValueError('duplicate synthetic graph input')
    return rows


def actual_graph(rows, name):
    tracks, assigned = graph_port().graph_tracks(rows, name, config())
    ids = [x for t in tracks for x in t['observation_ids']]
    if len(ids) != len(set(ids)) or assigned != len(ids):
        raise ValueError('actual graph duplicates input ownership')
    return dict(rows=rows, tracks=tracks, assigned=assigned,
                unresolved_ids=[r['observation_id'] for r in rows if r['observation_id'] not in set(ids)],
                synthetic_clock=True, qualified_capture=False)


def oracle_graphs(name):
    # Full true trajectories, each in its own numerical lane. Never actual selection input.
    result = {}
    for source in ('A', 'B'):
        rows = []
        for rx in (0, 1):
            for i, t in enumerate(TIMES):
                s = next(s for s in sources(t, (127, 127)) if s['name'] == source)
                rows.append(dict(observation_id=observation_id(name+'-oracle-'+source, rx, i),
                    receiver=rx+1, native_receiver_id=str(rx), channel=1, time_s=t+.01,
                    measured_cfo_hz=s['cfo0']+s['rate']*(t+.01), actual_rf_hz=10940312500.,
                    fractional_margin=1., visit=i, candidate_rank=None))
        result[source] = actual_graph(rows, name+'-oracle-'+source)
    return result


def label(cfo, truth):
    period = config().alias_spacing_hz
    distances = [abs((cfo-y+period/2) % period-period/2) for y in truth]
    close = [i for i, x in enumerate(distances) if x <= 450.]
    name = ('A', 'B')[close[0]] if len(close) == 1 else ('ambiguous' if close else 'unmatched')
    return dict(label=name, distances_hz=distances)


def alarm(seconds):
    if seconds <= 0:
        raise TimeoutError('frozen cumulative budget exhausted')
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('frozen numerical deadline')))
    signal.setitimer(signal.ITIMER_REAL, seconds)


def prepare():
    from leo.analysis.starlink.templates import qin_edge_pilot_frame
    identity = json.loads(detector_command('identity').stdout)
    write(HERE/'detector_identity.json', identity)
    # The independent generator's repo template must be exactly the deployed one.
    deployed_template = next(p for p in identity['actual_imported_sources'] if p.endswith('/templates.py'))
    if sha(REPO/'src/leo/analysis/starlink/templates.py') != sha(deployed_template):
        raise ValueError('local generator template differs from deployed detector')
    sampled = frame('sampled_deployed'); right = frame('sampled_right')
    bad = np.flatnonzero(abs(sampled-right) > 5e-7)
    if len(bad) != 68:
        raise ValueError('prior 68-sample boundary authority not reproduced')
    np.testing.assert_array_equal(sampled, qin_edge_pilot_frame(RATE, 'upper'))
    old = json.loads((OLD/'strong_20261026.json').read_text())
    # Real archived detector output through actual row/graph port, before NEW detector results.
    slots = [dict(status='complete', visit=i, time_s=t, receivers=old['receivers']) for i, t in enumerate(TIMES)]
    rows = rows_from_slots(slots, 'archived-port-smoke')
    out = actual_graph(rows, 'archived-port-smoke')
    if len(rows) != 32 or out['assigned'] != 32:
        raise ValueError('actual archived detector-to-graph port failed')
    w = window(np.zeros((COUNT, 2, 2), '<i2'))
    if w.samples.shape != (COUNT, 2, 2) or w.target['edge'] != 'upper':
        raise ValueError('detector window port failed')
    import unittest
    tests = unittest.defaultTestLoader.discover(str(HERE), pattern='test_experiment.py')
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if not result.wasSuccessful():
        raise RuntimeError('owned preparation tests failed')
    import inspect
    from leo.analysis import graph_tracklets, polynomial_tracklets, tracklet_fitting
    modules = (graph_tracklets, polynomial_tracklets, tracklet_fitting)
    actual = {str(Path(inspect.getfile(m))): sha(inspect.getfile(m)) for m in modules}
    actual.update(identity['actual_imported_sources'])
    for m in (graph_tracklets, polynomial_tracklets, tracklet_fitting):
        rel = Path(inspect.getfile(m)).relative_to(Path(inspect.getfile(graph_tracklets)).parents[2])
        if sha(REPO/'src'/rel) != sha(inspect.getfile(m)):
            raise ValueError('deployed graph differs from frozen original graph: '+str(rel))
    write(HERE/'preparation.json', dict(all_passed=True,
        seconds=time.monotonic()-STARTED+PRIOR_PREPARATION_SECONDS,
        prior_failed_identity_and_diagnostic_seconds=PRIOR_PREPARATION_SECONDS,
        actual_imported_sources=actual,
        code_digest=authority.CODE, environment_digest=authority.ENV,
        boundary_mismatch_indices=bad, boundary_mismatch_max=float(max(abs(sampled-right))),
        graph_port_assigned=out['assigned'], tests_run=result.testsRun,
        detector_called=False, capture_attested=False))


def freeze():
    if (HERE/'protocol.json').exists():
        raise FileExistsError('protocol already frozen')
    files = [HERE/'experiment.py', HERE/'test_experiment.py', HERE/'PROTOCOL.md', HERE/'preparation.json',
             HERE/'detector_identity.json',
             HERE.parent/'COORDINATOR_PLAN.md', CONFIG, OLD/'control.py', OLD/'protocol.json',
             OLD/'AMENDMENT02.md', OLD/'strong_20261026.json', AUTH/'replay_metadata.json', authority.FIXTURE]
    files += [REPO/p for p in ('src/leo/processing/fast_scan.py', 'src/leo/scanner/fast_scan_analysis.py',
        'src/leo/scanner/fast_scan_detector.py', 'src/leo/analysis/research/public_tracking_points.py',
        'src/leo/analysis/graph_tracklets.py', 'src/leo/analysis/polynomial_tracklets.py',
        'src/leo/analysis/tracklet_fitting.py', 'tools/evaluate_ds22_merged_tracks.py',
        'src/leo/analysis/starlink/templates.py', 'src/leo/analysis/starlink/fast_scan_scores.py')]
    files += [Path(p) for p in json.loads((HERE/'preparation.json').read_text())['actual_imported_sources']]
    files += [HERE.parent/'measurement_preparation.log', HERE.parent/'measurement_preparation02.log',
              HERE.parent/'measurement_preparation03.log']
    write(HERE/'protocol.json', dict(files={str(p): sha(p) for p in files},
        numerical_budget_seconds=600., preparation_seconds=json.loads((HERE/'preparation.json').read_text())['seconds'],
        max_workers=1, blas_threads=1, paired_detector_calls=70, detector_receivers_per_call=2,
        closure_laws=LAWS, closure_seed=20261026, sequence_seed=SEED, times_s=TIMES,
        sequences=[dict(name=name, law=law, epochs=epochs)
                   for name, epochs in (('coincident', (127, 127)), ('separated', (127, 811)))
                   for law in ('sampled_deployed', 'continuous')],
        graph_config=json.loads(CONFIG.read_text())['config'], operational_adoption=False))


def verify():
    protocol = json.loads((HERE/'protocol.json').read_text())
    for path, digest in protocol['files'].items():
        if sha(path) != digest:
            raise ValueError('frozen input changed: '+path)
    audit = json.loads((HERE.parent/'audit/measurement_preflight.json').read_text())
    if not audit['all_passed'] or audit['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('exact B preflight required')
    return protocol


def run_detector(deadline):
    from leo.scanner.fast_scan_analysis import production_glrt
    protocol = verify()
    identity = detector_identity()
    if (HERE/'execution_detector.json').exists() or (HERE/'slots').exists():
        raise FileExistsError('no detector reruns')
    pilots = {(law, epoch): waveform(law, epoch) for law in LAWS for epoch in (127, 811)}
    all_slots = []
    def detect(name, law, t, specs, visit, seed_visit):
        slot = dict(name=name, law=law, time_s=t, visit=visit, sources=specs)
        start = time.monotonic()
        try:
            alarm(min(20., deadline-time.monotonic()))
            # Closure uses old seed exactly; sequence uses a paired child per visit.
            iq, details = synthesize(law, t, specs, visit if seed_visit == -1 else seed_visit,
                                     pilots, closure=seed_visit == -1)
            slot['input'] = details
            output = production_glrt(window(iq), (0, 1))
            slot.update(status='complete', input=details,
                        receivers=[r.model_dump(mode='json') for r in output])
        except Exception as exc:
            slot.update(status='failed', error=repr(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        slot['worker_seconds'] = time.monotonic()-start
        write(HERE/'slots'/f'{name}_{visit:02}.json', slot)
        all_slots.append(slot)
        return slot
    for law in LAWS:
        for single in (True, False):
            name = 'closure_'+law+('_single' if single else '_overlap')
            detect(name, law, 0., sources(0., (127, 127), closure=True, single=single), 0, -1)
    for spec in protocol['sequences']:
        name = spec['name']+'_'+spec['law']
        slots = [detect(name, spec['law'], t, sources(t, spec['epochs']), i, i)
                 for i, t in enumerate(TIMES)]
        print(json.dumps(dict(sequence=name, complete=sum(s['status']=='complete' for s in slots),
                              slots=16, elapsed=time.monotonic()-STARTED)), flush=True)
    if detector_identity() != identity:
        raise ValueError('deployed identity changed during detector run')
    write(HERE/'execution_detector.json', dict(slots=len(all_slots),
        complete=sum(s['status']=='complete' for s in all_slots),
        identity_before=identity, identity_after=detector_identity(),
        worker_seconds=time.monotonic()-STARTED))


def run():
    protocol = verify()
    if (HERE/'execution.json').exists():
        raise FileExistsError('no reruns')
    deadline = STARTED+600.-protocol['preparation_seconds']
    detector = detector_command('run_detector', '--deadline', str(deadline))
    print(detector.stdout, end='', flush=True)
    sequences = []
    for spec in protocol['sequences']:
        name = spec['name']+'_'+spec['law']
        slots = [json.loads((HERE/'slots'/f'{name}_{i:02}.json').read_text()) for i in range(16)]
        sequence = dict(name=name, definition=spec)
        try:
            alarm(deadline-time.monotonic())
            actual = actual_graph(rows_from_slots(slots, name), name)
            acquired = actual_graph(rows_from_slots(slots, name, acquired=True), name+'-acquired')
            # Seal response-only graph before opening any truth-distance diagnostics.
            graph_path = HERE/'graphs'/f'{name}.json'
            write(graph_path, dict(actual=actual, acquired_stage=acquired))
            sequence.update(status='complete', graph_path=str(graph_path), graph_sha256=sha(graph_path))
            oracle = oracle_graphs(name)
            write(HERE/'graphs'/f'{name}_oracle.json', oracle)
        except Exception as exc:
            sequence.update(status='failed', error=repr(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        sequences.append(sequence)
    all_slots = [json.loads(p.read_text()) for p in sorted((HERE/'slots').glob('*.json'))]
    elapsed = time.monotonic()-STARTED
    write(HERE/'execution.json', dict(slots=len(all_slots), complete=sum(s['status']=='complete' for s in all_slots),
        sequences=sequences, run_worker_seconds=elapsed, preparation_seconds=protocol['preparation_seconds'],
        cumulative_worker_seconds=elapsed+protocol['preparation_seconds'],
        detector_calls_not_retried=True, original_IQ_read=False, new_RF=False, position_fit=False,
        truth_used_for_actual_selection=False, code_digest=authority.CODE, environment_digest=authority.ENV))
    files = [p for p in HERE.rglob('*') if p.is_file() and p.name != 'RF_seal.json'
             and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
    write(HERE/'RF_seal.json', dict(protocol_sha256=sha(HERE/'protocol.json'), all_selected_terminal=True,
        files={str(p): sha(p) for p in files}, no_operational_acceptance=True))
    print('TERMINAL '+json.dumps(dict(complete=sum(s['status']=='complete' for s in all_slots), slots=70,
                                    cumulative_worker_seconds=elapsed+protocol['preparation_seconds'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'freeze', 'run', 'identity', 'run_detector'))
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args()
    if args.command == 'identity':
        print(json.dumps(detector_identity()))
    elif args.command == 'run_detector':
        if args.deadline is None:
            raise ValueError('absolute original deadline required')
        run_detector(args.deadline)
    else:
        {'prepare': prepare, 'freeze': freeze, 'run': run}[args.command]()
