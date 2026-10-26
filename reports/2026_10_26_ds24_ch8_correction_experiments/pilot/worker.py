"""Bounded historical paired parity and response analysis; JSON stdout only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
PRIOR = Path('/srv/bulk/leo/research/ds24-detector-response-r01')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def metadata():
    port = module('established_raw_metadata', PRIOR/'influence/raw_metadata.py')
    panel = read(HERE/'panel.json')
    rows = []
    for slot in panel['slots']:
        if slot['status'] != 'nominated':
            continue
        try:
            rows.append(dict(request_id=slot['request_id'], raw_authority=port.one(slot)))
        except Exception as exc:
            rows.append(dict(request_id=slot['request_id'], raw_authority=dict(status='unavailable', error=repr(exc))))
    return dict(panel_sha256=sha(HERE/'panel.json'), IQ_reads=0,
                metadata_helper_sha256=sha(PRIOR/'influence/raw_metadata.py'), rows=rows)


def recorded():
    import numpy as np
    from leo.storage.fast_scan import FastSegmentSource
    from leo.contracts.fast_scan_native import parse_fast_policy
    from leo.scanner.fast_scan_analysis import analyze_window, production_glrt
    from response import compare, symbol_rate_diagnostic
    replay = module('established_replay', PRIOR/'recorded/replay.py')
    panel = read(HERE/'panel.json')
    metadata = read(HERE/'raw_metadata.json')
    if metadata['panel_sha256'] != sha(HERE/'panel.json'):
        raise ValueError('panel changed after metadata binding')
    authority = read(PRIOR/'recorded/authority.json')
    identity = replay.runtime_identity()
    for record in authority['records']:
        if not record['identity_matches'] or record['runtime_identity'] != [identity['code_digest'], identity['environment_digest']]:
            raise ValueError('historical identity differs from original execution')
    for path, expected in panel['source_sha256'].items():
        if sha(path) != expected:
            raise ValueError('frozen nomination source changed')
    by_id = {r['request_id']:r['raw_authority'] for r in metadata['rows']}
    physical = {}
    for slot in panel['slots']:
        if slot['status'] == 'nominated':
            physical.setdefault(slot['physical_id'], []).append(slot)
    if len(physical) > 32:
        raise ValueError('32 physical window budget exceeded')
    rows = []
    reads = calls = 0
    began = time.monotonic()
    def timeout(*_):
        raise TimeoutError('bounded pilot job exceeded 580 seconds')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(580)
    for physical_id, slots in physical.items():
        started = time.monotonic()
        result = dict(physical_id=physical_id, request_ids=[s['request_id'] for s in slots])
        try:
            first = slots[0]
            raw = by_id[first['request_id']]
            if raw['status'] != 'metadata_ready_IQ_and_detector_parity_unverified':
                raise ValueError('raw metadata unavailable')
            if 'sha256:'+sha(raw['index_path']) != raw['index_sha256']:
                raise ValueError('index hash changed')
            source = FastSegmentSource(raw['segment'], start_sequence=raw['local_sequence'], stop_sequence=raw['local_sequence']+1)
            reads += 1
            window = replay.exhaust_one(source)
            if (window.iq_sha256 != raw['index']['iq_sha256'] or window.acquisition != raw['index']['acquisition']
                    or window.target != raw['target'] or window.sample_rate_hz != first['sample_rate_hz']):
                raise ValueError('raw geometry/authority mismatch')
            document = read(first['tracking']['path'])
            expected = {p['receiver_id']:p['candidates'] for p in document['source']['probes']
                        if p['visit_index'] == first['probe']['visit_index'] and p['probe_index'] == first['probe']['probe_index']}
            auth = next(r for r in authority['records'] if r['case'] == first['case'])
            policy = parse_fast_policy(auth['execution']['pipeline_configuration']['stages']['fast-scan'])
            calls += 1
            detection = analyze_window(window, source.receiver_ids, None, policy, detector=production_glrt)
            actual = replay.exported(detection.receivers)
            parity = {str(rx):replay.compare(candidates, actual.get(rx, [])) for rx,candidates in expected.items()}
            if detection.status != 'processed' or not all(p['all_passed'] for p in parity.values()):
                raise ValueError('full historical paired candidate parity failed')
            result.update(status='complete', full_reader_exhausted=True, IQ_sha256=window.iq_sha256,
                          paired_candidate_parity=parity, receiver_ids=list(source.receiver_ids), slots=[])
            for slot in slots:
                item = dict(request_id=slot['request_id'], role=slot['role'], receiver=slot['receiver'],
                            channel=slot['channel'], case=slot['case'], original_candidate=slot['original_candidate'])
                try:
                    p = slot['original_candidate']
                    original = replay.fixed_rank(detection.receivers, slot['native_receiver_id'], p['candidate_rank'])
                    if abs(original.fractional_tracking_cfo_hz-p['fractional_tracking_cfo_hz']) > 1e-6:
                        raise ValueError('fixed original candidate differs')
                    rx = source.receiver_ids.index(slot['native_receiver_id'])
                    iq = window.samples[:, rx, 0].astype(float)+1j*window.samples[:, rx, 1].astype(float)
                    args = (iq, window.sample_rate_hz, slot['probe']['edge'],
                            p['integer_epoch_sample']+p['fractional_epoch_offset_samples'], p['fractional_tracking_cfo_hz'])
                    item.update(status='complete', response=compare(*args))
                    try:
                        item['received_symbol_rate'] = dict(status='complete', **symbol_rate_diagnostic(*args))
                    except Exception as exc:
                        item['received_symbol_rate'] = dict(status='failed', error=repr(exc))
                except Exception as exc:
                    item.update(status='failed', error=repr(exc))
                result['slots'].append(item)
                print(slot['request_id'], item['status'],
                      item.get('response', {}).get('held_symbol_relative_SSE_improvement'), file=sys.stderr, flush=True)
        except Exception as exc:
            result.update(status='failed', error=repr(exc))
        result['seconds'] = time.monotonic()-started
        rows.append(result)
    signal.alarm(0)
    return dict(panel_sha256=sha(HERE/'panel.json'), raw_metadata_sha256=sha(HERE/'raw_metadata.json'),
        source_sha256={str(HERE/name):sha(HERE/name) for name in ('nominate.py','response.py','worker.py','test_response.py')},
        runtime_identity=identity, runtime_identity_unchanged=identity == replay.runtime_identity(),
        physical_window_reads=reads, physical_detector_calls=calls, rows=rows, seconds=time.monotonic()-began,
        full_set_failures=[r['physical_id'] for r in rows if r['status'] != 'complete'],
        original_full_window_acquisition_exposure=True, raw_IQ_copied=False,
        inference_and_admission_unchanged=True, new_RF_collection=False, real_CFO_truth_available=False)


def controls():
    from response import compare, synthetic
    rows = []
    began = time.monotonic()
    for mode in ('channel','flat','wrong_sequence','noise'):
        for seed in range(32):
            result = compare(*synthetic(241000+seed, mode))
            rows.append(dict(mode=mode, seed=241000+seed, **result))
    return dict(rows=rows, seconds=time.monotonic()-began, replicates_per_mode=32,
        channel_gains_independent_per_tone_and_frame=True, noise_independent_complex_Gaussian=True,
        exact_known_timing_and_CFO=True, control_scope='fixed-anchor response evidence, not full acquisition/GLRT gate FPR',
        source_sha256=sha(HERE/'response.py'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['metadata','recorded','controls'])
    args = parser.parse_args()
    json.dump(globals()[args.action](), sys.stdout, indent=2, allow_nan=False)
    print()
