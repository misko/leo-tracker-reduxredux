"""Fixed 159-ID public-input replay, with exact eight-row historical reuse."""
import time
STARTED = time.monotonic()
import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PRIOR = Path('/srv/bulk/leo/research/ds24-detector-response-r01')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
DEPLOYED = Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
PYTHON = '/opt/leo-fast-auto/20261010-r1/venv/bin/python'
POINTS = PRIOR / 'influence/report/complete_selected_owner_points.csv'
REFINER = PRIOR / 'measurement/refiner.py'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


old = module('immutable_recorded_replay', PRIOR / 'recorded/replay.py')
sha = old.sha
load = old.load


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, default=old.encode, allow_nan=False)
        stream.write('\n')


def reuse_matches(request, previous):
    keys = ('case', 'role', 'complete_owner', 'native_observation_id', 'original_observation',
            'tracking', 'source_input', 'source_session_id', 'recording_id',
            'raw_recording_authority_digest', 'probe', 'original_candidate')
    return all(request[key] == previous[key] for key in keys) and all(
        request['raw_authority'][key] == previous['raw_authority'][key]
        for key in ('segment', 'segment_manifest_sha256', 'index_path', 'index_sha256',
                    'local_sequence', 'index', 'target', 'sample_rate_hz', 'receiver_ids'))


def physical_key(request):
    p = request['probe']
    return (request['case'], p['visit_index'], p['probe_index'], p['window_start_counter'])


def make_requests():
    points = list(csv.DictReader(POINTS.open()))
    assert len(points) == 159 and len({p['native_id'] for p in points}) == 159
    previous = load(PRIOR / 'influence/window_requests.json')
    templates = {r['case']: r for r in previous}
    requests = []
    for case in ('DS24-0010', 'DS24-0011'):
        tracking = load(SOURCE / case / 'tracking.json')
        observations = {o['observation_id']: o for o in load(SOURCE / case / 'observations.json')}
        source = tracking['source']
        origin = tracking['clock_anchor']['sample_counter']
        fs = source['sample_rate_hz']
        template = templates[case]
        for point in sorted((p for p in points if p['case'] == case), key=lambda p: (float(p['time_s']), p['native_id'])):
            o = observations[point['native_id']]
            assert o['measured_cfo_hz'] == float(point['native_CFO_Hz'])
            matches = [p for p in source['probes'] if p['receiver_id'] == o['native_receiver_id'] and p['channel'] == o['channel']
                       and abs((p['valid_start_counter'] - origin) / fs + p['probe_start_ms'] / 1000 + source['probe_ms'] / 2000 - o['time_s']) < 1e-8]
            if len(matches) != 1:
                raise ValueError('original unique probe missing: ' + point['native_id'])
            p = matches[0]
            candidates = [c for c in p['candidates'] if c['passed_fractional_margin_gate']]
            candidate = max(candidates, key=lambda c: (c['fractional_margin'], -c['candidate_rank']))
            assert candidate['fractional_tracking_cfo_hz'] == o['measured_cfo_hz']
            assert candidate['fractional_margin'] == o['fractional_margin']
            requests.append(dict(request_id=case + '_' + point['native_id'].split(':')[1], case=case, role=point['role'],
                complete_owner=point['owner'], native_observation_id=point['native_id'], original_observation=o,
                tracking=dict(path=str(SOURCE / case / 'tracking.json'), sha256=sha(SOURCE / case / 'tracking.json')),
                **{key: template[key] for key in ('source_input', 'source_session_id', 'recording_id', 'raw_recording_authority_digest')},
                probe=dict(visit_index=p['visit_index'], probe_index=p['probe_index'], receiver_id=p['receiver_id'], channel=p['channel'],
                           actual_rf_hz=p['actual_rf_hz'], time_s=o['time_s'], window_start_counter=p['valid_start_counter'] + round(p['probe_start_ms'] * fs / 1000),
                           origin_counter=origin, duration_samples=round(source['probe_ms'] * fs / 1000)),
                original_candidate=candidate, acquired_cfo_hz=None))
    return requests


def prepare():
    if (HERE / 'protocol.json').exists():
        raise FileExistsError('preserve freeze')
    requests = make_requests()
    write(HERE / 'requests_before_authority.json', requests)
    began = time.monotonic()
    command = ['sudo', '-n', '-u', 'leo', 'env', 'PYTHONPATH=' + str(DEPLOYED), 'PYTHONDONTWRITEBYTECODE=1',
               'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1', 'MKL_NUM_THREADS=1', PYTHON, '-B', str(PRIOR / 'influence/raw_metadata.py')]
    result = subprocess.run(command, input=json.dumps(requests), capture_output=True, text=True, timeout=90)
    write(HERE / 'metadata_receipt.json', dict(returncode=result.returncode, seconds=time.monotonic() - began, stderr=result.stderr, stdout=result.stdout))
    if result.returncode:
        raise RuntimeError('metadata authority failed; no retry')
    authority = {r['request_id']: r['raw_authority'] for r in json.loads(result.stdout)}
    previous = {r['native_observation_id']: r for r in load(PRIOR / 'influence/window_requests.json')}
    previous_result = load(PRIOR / 'recorded/results.json')
    identity = old.runtime_identity()
    assert previous_result['identity_before'] == previous_result['identity_after'] == identity
    assert previous_result['refiner_sha256'] == sha(REFINER)
    reused = []
    for request in requests:
        request['raw_authority'] = authority[request['request_id']]
        if request['raw_authority']['status'] != 'metadata_ready_IQ_and_detector_parity_unverified':
            raise ValueError('raw authority unavailable; preserve fixed denominator')
        request['reused_prior_request_id'] = None
        if request['native_observation_id'] in previous:
            prev = previous[request['native_observation_id']]
            if not reuse_matches(request, prev):
                raise ValueError('previous request cannot be reused exactly')
            record = next(r for r in previous_result['records'] if r['request_id'] == prev['request_id'])
            assert record['status'] == 'complete' and all(p['all_passed'] for p in record['candidate_parity'].values())
            request['reused_prior_request_id'] = prev['request_id']
            reused.append(request['native_observation_id'])
    assert len(reused) == 8
    # Multiple selected receivers in one physical window would share one detector call.
    groups = {}
    for r in requests:
        if not r['reused_prior_request_id']:
            groups.setdefault(physical_key(r), []).append(r['request_id'])
    ordered = sorted(groups)
    batches = [[groups[key] for key in ordered[i::2]] for i in range(2)]
    assert len(groups) <= 151
    write(HERE / 'requests.json', requests)
    write(HERE / 'batches.json', batches)
    tests = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(unittest.defaultTestLoader.discover(str(HERE), pattern='test_complete.py'))
    if not tests.wasSuccessful():
        raise RuntimeError('owned tests failed')
    write(HERE / 'preparation.json', dict(all_passed=True, tests=tests.testsRun, metadata_only=True, IQ_reads=0, detector_calls=0,
        seconds=time.monotonic() - STARTED + 5., initial_inspection_allowance_seconds=5., total_ids=159,
        reused_ids=reused, unique_new_physical_windows=len(groups), batch_counts=list(map(len, batches)), identity=identity))
    freeze()


def freeze():
    requests = load(HERE / 'requests.json')
    tests = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(unittest.defaultTestLoader.discover(str(HERE), pattern='test_complete.py'))
    if not tests.wasSuccessful():
        raise RuntimeError('owned tests failed')
    write(HERE / 'preparation02.json', dict(all_passed=True, tests=tests.testsRun, seconds=load(HERE / 'preparation.json')['seconds'] + time.monotonic() - STARTED + 1.,
        failed_freeze_allowance_seconds=1., metadata_not_repeated=True, payload_reads=0, detector_calls=0))
    paths = [Path(__file__), HERE / 'PROTOCOL.md', HERE / 'test_complete.py', HERE / 'requests.json', HERE / 'batches.json',
             HERE / 'requests_before_authority.json', HERE / 'metadata_receipt.json', HERE / 'preparation.json', ROOT / 'COORDINATOR_PLAN.md', ROOT / 'EVALUATION_SCOPE.md',
             POINTS, PRIOR / 'recorded/replay.py', PRIOR / 'influence/raw_metadata.py', PRIOR / 'recorded/authority.json',
             PRIOR / 'influence/window_requests.json', PRIOR / 'recorded/results.json', PRIOR / 'recorded/RF_seal.json', REFINER]
    paths += [Path(r['tracking']['path']) for r in requests]
    paths += [Path(p) for p in load(PRIOR / 'recorded/protocol.json')['files']]
    paths += [HERE / n for n in ('preparation02.json', 'failed_freeze01.json', 'complete_preparation01.py') if (HERE / n).exists()]
    public = {r['source_input']['path']: r['source_input']['sha256'].removeprefix('sha256:') for r in requests}
    public.update({r['raw_authority']['index_path']: r['raw_authority']['index_sha256'].removeprefix('sha256:') for r in requests})
    write(HERE / 'protocol.json', dict(schema='complete-owner-refinement/v1', files={str(p): sha(p) for p in sorted(set(paths))},
        public_data_bindings=public, public_data_verified_at_metadata_and_service_worker=True,
        maximum_new_paired_detector_calls=151, cap_cumulative_worker_seconds=480., preparation_seconds=load(HERE / 'preparation02.json')['seconds'],
        coordinator_reserve_seconds=5., workers=2, BLAS_threads=1, total_slots=159, prior_reused_slots=8,
        descriptive_polynomial_degree=2, original_CFO_fallback_no_drop=True, no_graph_orbit_position_GPS=True))
    print('FROZEN ' + sha(HERE / 'protocol.json'), flush=True)


def verify():
    protocol = load(HERE / 'protocol.json')
    approval = load(ROOT / 'audit/measurement_preflight.json')
    if not approval['all_passed'] or approval['protocol_sha256'] != sha(HERE / 'protocol.json'):
        raise ValueError('exact independent preflight required')
    for path, digest in protocol['files'].items():
        if sha(path) != digest:
            raise ValueError('frozen file changed: ' + path)
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError('BLAS1 required')
    return protocol


def worker(index):
    protocol = verify()
    for path, digest in protocol['public_data_bindings'].items():
        if sha(path) != digest:
            raise ValueError('public native input/index changed: ' + path)
    from leo.storage.fast_scan import FastSegmentSource
    from leo.contracts.fast_scan_native import parse_fast_policy
    from leo.scanner.fast_scan_analysis import analyze_window, production_glrt
    import numpy as np
    refiner = module('unchanged_continuous_refiner', REFINER)
    requests = {r['request_id']: r for r in load(HERE / 'requests.json')}
    batch = load(HERE / 'batches.json')[index]
    authority = load(PRIOR / 'recorded/authority.json')
    identity = old.runtime_identity()
    assert identity == load(HERE / 'preparation.json')['identity']
    allowance = (protocol['cap_cumulative_worker_seconds'] - protocol['preparation_seconds'] - protocol['coordinator_reserve_seconds']) / 2
    deadline = STARTED + allowance
    calls = 0
    records = []
    status = 'terminal'
    def timeout(*_):
        raise TimeoutError('fixed per-worker share of original480second cap')
    signal.signal(signal.SIGALRM, timeout)
    for group in batch:
        stage = 'before_read'
        current = []
        checkpoint = {}
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('worker budget exhausted before request')
            signal.setitimer(signal.ITIMER_REAL, remaining)
            first = requests[group[0]]
            a = first['raw_authority']
            source = FastSegmentSource(a['segment'], start_sequence=a['local_sequence'], stop_sequence=a['local_sequence'] + 1)
            assert source.manifest_digest == a['segment_manifest_sha256']
            stage = 'public_payload_read'
            window = old.exhaust_one(source)
            assert window.iq_sha256 == a['index']['iq_sha256']
            assert window.acquisition == a['index']['acquisition'] and window.target == a['target']
            assert window.sample_rate_hz == a['sample_rate_hz'] and tuple(source.receiver_ids) == tuple(a['receiver_ids'])
            assert window.acquisition['sample_start'] == first['probe']['window_start_counter']
            assert len(window.samples) == first['probe']['duration_samples']
            assert window.target['rf_center_hz'] - window.target['lnb_lo_hz'] - window.acquisition['actual_if_center_hz'] == 0
            tracking = load(first['tracking']['path'])
            expected = {p['receiver_id']: p['candidates'] for p in tracking['source']['probes']
                        if p['visit_index'] == first['probe']['visit_index'] and p['probe_index'] == first['probe']['probe_index']}
            assert set(expected) == set(source.receiver_ids)
            auth = next(x for x in authority['records'] if x['case'] == first['case'])
            policy = parse_fast_policy(auth['execution']['pipeline_configuration']['stages']['fast-scan'])
            stage = 'paired_detector'
            calls += 1
            result = analyze_window(window, source.receiver_ids, None, policy, detector=production_glrt)
            checkpoint['full_original_replay_result'] = result.model_dump(mode='json')
            assert result.status == 'processed'
            actual = old.exported(result.receivers)
            parity = {str(rx): old.compare(expected[rx], actual.get(rx, [])) for rx in expected}
            checkpoint['candidate_parity'] = parity
            assert all(v['all_passed'] for v in parity.values())
            stage = 'fixed_original_rank_refinement'
            for request_id in group:
                request = requests[request_id]
                peak = old.fixed_rank(result.receivers, request['probe']['receiver_id'], request['original_candidate']['candidate_rank'])
                candidate = next(c for c in actual[request['probe']['receiver_id']] if c['candidate_rank'] == peak.candidate_rank)
                assert old.compare([request['original_candidate']], [candidate])['all_passed']
                rx_index = source.receiver_ids.index(request['probe']['receiver_id'])
                values = window.samples[:, rx_index, 0].astype(float) + 1j * window.samples[:, rx_index, 1].astype(float)
                refined, correlations = refiner.refine(values, window.sample_rate_hz, window.target['edge'], peak.acquired_cfo_hz,
                    peak.epoch_sample, peak.fractional_epoch_offset_samples, peak.fractional_residual_cfo_hz,
                    peak.fractional_exact_score, peak.fractional_control_score)
                current.append(dict(request_id=request_id, status='complete', IQ_sha256=window.iq_sha256, full_reader_exhausted=True,
                    full_original_replay_result=result.model_dump(mode='json'), candidate_parity=parity,
                    original_replayed_candidate=peak.model_dump(mode='json'), refinement=refined,
                    correction_delta_hz=refined['corrected_tracking_cfo_hz'] - peak.fractional_tracking_cfo_hz,
                    correlations=dict(exact_values_real=correlations['exact_values'].real, exact_values_imag=correlations['exact_values'].imag,
                        control_values_real=correlations['control_values'].real, control_values_imag=correlations['control_values'].imag, times_s=correlations['times_s'])))
            records.extend(current)
        except Exception as exc:
            records.extend(current)
            done = {r['request_id'] for r in records}
            records.extend(dict(request_id=rid, status='failed', failed_stage=stage, error=repr(exc), **checkpoint) for rid in group if rid not in done)
            status = 'stopped_after_error'
            break
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    done = {r['request_id'] for r in records}
    records.extend(dict(request_id=rid, status='not_attempted', error=status) for group in batch for rid in group if rid not in done)
    print(json.dumps(dict(worker=index, status=status, records=records, paired_detector_calls=calls, seconds=time.monotonic() - STARTED,
        allowance_seconds=allowance, identity_before=identity, identity_after=old.runtime_identity()), default=old.encode, allow_nan=False), flush=True)


def correction(request, record, reused):
    original = request['original_observation']['measured_cfo_hz']
    complete = record['status'] == 'complete'
    qualified = complete and bool(record['refinement']['numerical_frequency_qualified'])
    proposed = record['refinement']['corrected_tracking_cfo_hz'] if complete else None
    return dict(case=request['case'], role=request['role'], native_observation_id=request['native_observation_id'],
        complete_owner=request['complete_owner'], time_s=request['probe']['time_s'], original_cfo_hz=original,
        corrected_cfo_hz=proposed if qualified else original, proposed_refined_cfo_hz=proposed,
        correction_delta_hz=proposed-original if qualified else 0., numerical_frequency_qualified=qualified,
        numerical_margin_qualified=complete and bool(record['refinement']['numerical_margin_qualified']),
        payload_and_parity_complete=complete, status=record['status'], reused_prior_result=reused,
        fallback_to_original=not qualified, error=record.get('error'))


def run():
    protocol = verify()
    if (HERE / 'execution.json').exists():
        raise FileExistsError('one run only')
    write(HERE / 'execution.json', dict(protocol_sha256=sha(HERE / 'protocol.json'), no_retry=True, workers=2))
    def launch(index):
        command = ['sudo', '-n', '-u', 'leo', 'env', 'PYTHONPATH=' + str(DEPLOYED), 'PYTHONDONTWRITEBYTECODE=1',
                   'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1', 'MKL_NUM_THREADS=1', PYTHON, '-B', str(Path(__file__)), 'worker', '--index', str(index)]
        allowance = (480. - protocol['preparation_seconds'] - 5.) / 2
        began = time.monotonic()
        with (HERE / f'worker{index}.json').open('x') as out, (HERE / f'worker{index}_stderr.log').open('x') as err:
            process = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=True)
            timed_out = False
            try:
                code = process.wait(timeout=allowance + 2.)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait()
                timed_out = True
        return dict(returncode=code, seconds=time.monotonic()-began, timed_out=timed_out, outer_bound_seconds=allowance+2.)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(launch, range(2)))
    requests = load(HERE / 'requests.json')
    workers = []
    records = {}
    for index, process in enumerate(codes):
        try:
            value = load(HERE / f'worker{index}.json')
            if process['returncode']:
                raise ValueError('worker process failed')
            value['process'] = process
            workers.append(value)
            records.update({r['request_id']: r for r in value['records']})
        except Exception as exc:
            workers.append(dict(worker=index, status='process_failed', seconds=process['seconds'],
                                paired_detector_calls=None, process=process, error=repr(exc)))
    previous = {r['request_id']: r for r in load(PRIOR / 'recorded/results.json')['records']}
    rows = []
    for request in requests:
        reused = bool(request['reused_prior_request_id'])
        record = previous[request['reused_prior_request_id']] if reused else records.get(request['request_id'], dict(status='not_attempted', error='worker unavailable'))
        rows.append(correction(request, record, reused))
    summary = dict(schema='complete-owner-native-corrections/v1', rows=rows, coverage_complete=all(r['payload_and_parity_complete'] for r in rows),
        all_frequency_qualified=all(r['numerical_frequency_qualified'] for r in rows), total_slots=159, reused_slots=8,
        preparation_seconds=protocol['preparation_seconds'], workers=[{k:v for k,v in w.items() if k!='records'} for w in workers],
        cumulative_worker_seconds=protocol['preparation_seconds'] + sum(p['seconds'] for p in codes),
        native_delta_without_graph_rewrap=True, same_vector_both_c_arms=True, no_position_GPS=True)
    assert len(rows) == len({r['native_observation_id'] for r in rows}) == 159
    write(HERE / 'corrections.json', summary)
    paths = [HERE / 'protocol.json', HERE / 'execution.json', HERE / 'corrections.json']
    paths += [HERE / f'worker{i}{suffix}' for i in range(2) for suffix in ('.json', '_stderr.log')]
    write(HERE / 'RF_seal.json', dict(protocol_sha256=sha(HERE / 'protocol.json'), files={str(p): sha(p) for p in paths},
        coverage_complete=summary['coverage_complete'], all_frequency_qualified=summary['all_frequency_qualified']))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','workers')}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'freeze', 'worker', 'run'))
    parser.add_argument('--index', type=int, choices=(0,1))
    args = parser.parse_args()
    {'prepare': prepare, 'freeze': freeze, 'run': run, 'worker': lambda: worker(args.index)}[args.action]()
