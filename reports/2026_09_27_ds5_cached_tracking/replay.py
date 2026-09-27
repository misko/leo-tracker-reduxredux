"""Bounded causal saved-IQ replay of known-channel GLRT and real blind fallback."""
from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import importlib
import json
import platform
import signal
import sys
import time
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'native'))
import known_state  # noqa: E402,F401
from stress import cache_lookup, prepare_visit  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402
from tracking import Key, Observation, Policy, Tracker, reference_match  # noqa: E402


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scientific(value):
    if isinstance(value, ct.Structure):
        return {name: scientific(getattr(value, name)) for name, _ in value._fields_
                if 'cpu_ms' not in name and 'wall_ms' not in name}
    if isinstance(value, ct.Array):
        return [scientific(item) for item in value]
    return value


def blind_observation(result):
    window = int(result.rank.order[0])
    confirm = result.confirmations[0]
    if not confirm.candidate_count:
        return None
    candidate = confirm.candidates[0]
    return Observation(window, candidate.epoch + candidate.fractional_offset_samples,
                       candidate.tracking_cfo_hz, candidate.exact_score, candidate.control_score,
                       bool(candidate.fractional_complete), 'fitted', candidate.acquired_cfo_hz)


def fast_observation(result, window):
    return Observation(window, result['epoch_samples'], result['tracking_cfo_hz'],
                       result['exact_score'], result['control_score'],
                       bool(result['valid_bounds'] and result['support_frames'] >= 2
                            and result['scored_fractional']
                            and not result['needs_reacquire']), result['timing_semantics'],
                       result.get('scoring_cfo_hz'))


def timed(function, repetitions):
    # Repetitions measure stateless DSP; caller advances causal state only once.
    expected, _ = function()
    measurements = []
    detail = None
    for _ in range(repetitions):
        cpu = time.process_time_ns()
        wall = time.perf_counter_ns()
        actual, detail = function()
        elapsed = time.perf_counter_ns() - wall
        cpu_elapsed = time.process_time_ns() - cpu
        if actual != expected:
            raise ValueError('DSP observation changed across identical repetitions')
        measurements.append({'cpu_ms': cpu_elapsed / 1e6, 'wall_ms': elapsed / 1e6})
    return expected, detail, measurements


def run(args):
    signal.alarm(240)
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_path = args.dataset.resolve()
    payload = json.loads(dataset_path.read_text())
    config = json.loads(args.config.read_text())
    variant = config.get('variant', 'primary')
    if variant not in ('primary', 'forced_state_drop', 'processing_outage', 'wrong_cache'):
        raise ValueError('unsupported stress variant')
    if (type(config['repetitions']) is not int or config['repetitions'] < 3
            or type(config['local_recovery']) is not bool):
        raise ValueError('at least three repetitions and explicit boolean recovery required')
    if args.split == 'holdout':
        if not args.authorize_holdout or config.get('stage') != 'frozen':
            raise ValueError('fresh holdout requires explicitly frozen configuration')
        for name, expected in config['source_sha256'].items():
            if sha256(HERE / name) != expected:
                raise ValueError('source changed after freeze')
        if config['dataset_sha256'] != sha256(dataset_path):
            raise ValueError('dataset changed after freeze')
    cases = sorted((c for c in payload['cases'] if c['split'] == args.split),
                   key=lambda c: (c['session_id'], c['visit_index']))
    if not cases:
        raise ValueError('split is empty')
    module_name = config.get('native_module', 'known_state')
    if module_name not in ('known_state', 'known_state_v2', 'known_state_v3'):
        raise ValueError('unsupported native implementation')
    native_module = importlib.import_module(module_name)
    if module_name == 'known_state_v3':
        native_library = native_module.build_library_v3()
        native_class = native_module.NativeKnownStateV3
    elif module_name == 'known_state_v2':
        native_library = native_module.build_library_v2()
        native_class = native_module.NativeKnownStateV2
    else:
        native_library = native_module.build_library()
        native_class = native_module.NativeKnownState
    blind_mode = config.get('blind_mode', 'packed')
    if blind_mode not in ('packed', 'strided_v4'):
        raise ValueError('unsupported blind mode')
    strided_module = None
    if blind_mode == 'strided_v4':
        if module_name != 'known_state_v3':
            raise ValueError('strided blind prototype requires V3 known-state scoring')
        strided_module = importlib.import_module('blind_strided_v4')
        native_library = strided_module.build_library_v4()
    baseline_library = native_library
    baseline_receipt = json.loads(baseline_library.with_suffix('.so.build.json').read_text())
    if args.split == 'holdout' and (
            sha256(baseline_library) != config['native_binary_sha256']
                or sha256(baseline_library.with_suffix('.so.build.json'))
                != config['native_build_receipt_sha256']):
        raise ValueError('native executable or build receipt changed after freeze')
    if sha256(baseline_library) != baseline_receipt['binary_sha256']:
        raise ValueError('baseline binary changed')
    for name, expected in baseline_receipt['sources_sha256'].items():
        if sha256(name) != expected:
            raise ValueError('baseline source changed')
    source_paths = [HERE / 'tracking.py', HERE / 'replay.py', HERE / 'stress.py',
                    Path(native_module.__file__)]
    if strided_module is not None:
        source_paths.append(Path(strided_module.__file__))
    source_hashes = {str(p.relative_to(HERE)): sha256(p) for p in source_paths}
    policy = Policy(**config['policy'])
    tracker = Tracker(policy)
    repetitions = config['repetitions']
    rows = []
    initialization = time.perf_counter()
    with ExitStack() as stack:
        blind, fast, strided = {}, {}, {}
        for geometry in sorted({(c['rate_hz'], c['edge']) for c in cases}):
            blind[geometry] = stack.enter_context(NativeDwell(
                baseline_library, *geometry, 512))
            fast[geometry] = stack.enter_context(
                native_class(*geometry, library=native_library))
            if strided_module is not None:
                strided[geometry] = stack.enter_context(
                    strided_module.NativeStridedBlindV4(*geometry, library=native_library))
        initialization = time.perf_counter() - initialization
        for case in cases:
            outage = prepare_visit(tracker, case, variant, payload['stress_protocol'])
            raw_path = (dataset_path.parent / case['raw_npy']['path']).resolve()
            if not raw_path.is_relative_to(dataset_path.parent):
                raise ValueError('IQ path outside frozen dataset')
            if sha256(raw_path) != case['raw_npy']['sha256'].removeprefix('sha256:'):
                raise ValueError('IQ hash mismatch')
            raw = np.load(raw_path, allow_pickle=False)
            rate = case['rate_hz']
            if raw.shape != (rate * 120 // 1000, 2, 2) or raw.dtype != np.dtype('<i2'):
                raise ValueError('invalid raw IQ geometry')
            original_hash = hashlib.sha256(raw).hexdigest()
            geometry = (rate, case['edge'])
            for rx in range(2):
                key = Key(case['session_id'], rx, case['channel'], case['edge'], rate)
                start = case['source_start_counter']
                index = case['visit_index']

                def acquire(raw=raw, rx=rx, geometry=geometry):
                    # Include deinterleaving the full dwell in blind cost.
                    samples = np.ascontiguousarray(raw[:, rx, :])
                    result = blind[geometry].run(samples, maximum=1, seeded=False)
                    return blind_observation(result), result

                def acquire_candidate(raw=raw, rx=rx, geometry=geometry, acquire=acquire):
                    if strided_module is None:
                        return acquire()
                    result = strided[geometry].run(raw[:, rx, :], maximum=1, seeded=False)
                    return blind_observation(result), result

                # Separate independent reference, never supplied to Tracker.
                reference_first = (index + rx) % 2 == 0
                if reference_first:
                    reference, reference_detail, baseline_times = timed(acquire, repetitions)
                overhead_cpu, overhead_wall = time.process_time_ns(), time.perf_counter_ns()
                with cache_lookup(tracker, key, case['block_offset'], variant,
                                  payload['stress_protocol']) as injected_cache:
                    prediction, reason = tracker.begin(key, start, index)
                if outage:
                    prediction, reason = None, 'unprocessed_outage'
                state_cpu = (time.process_time_ns() - overhead_cpu) / 1e6
                state_wall = (time.perf_counter_ns() - overhead_wall) / 1e6
                action_times = []
                detail = None
                observation = None
                used_blind = False
                blind_detail = None
                attempted_cache = prediction is not None
                if prediction is not None:
                    left = prediction.window * (rate // 50)

                    def measure(recover=False, raw=raw, left=left, rate=rate,
                                rx=rx, prediction=prediction, geometry=geometry):
                        # Copy only the selected 20ms, never the whole120ms dwell.
                        values = raw[left:left + rate // 50, rx, :]
                        if module_name == 'known_state':
                            values = np.ascontiguousarray(values)
                        options = ({'frame_limit': config.get('frame_limit', 16)}
                                   if module_name != 'known_state' else {})
                        score_cfo = prediction.cfo_hz
                        if module_name == 'known_state_v3':
                            options['expected_physical_cfo_hz'] = prediction.cfo_hz
                            score_cfo = prediction.scoring_cfo_hz
                        result = fast[geometry].measure(values, prediction.epoch_samples,
                                                        score_cfo,
                                                        recover_timing=recover, **options)
                        result['scoring_cfo_hz'] = score_cfo
                        return fast_observation(result, prediction.window), result

                    observation, detail, timings = timed(measure, repetitions)
                    action_times.append(timings)
                    if not tracker.accepts(key, prediction, observation):
                        if config['local_recovery']:
                            observation, detail, timings = timed(lambda: measure(True), repetitions)
                            action_times.append(timings)
                        if not tracker.accepts(key, prediction, observation):
                            observation = None
                            reason = 'failed_prediction'
                        else:
                            reason = 'local_recovery'
                    else:
                        reason = 'cache_hit'
                if observation is None and not outage:
                    observation, blind_detail, timings = timed(acquire_candidate, repetitions)
                    action_times.append(timings)
                    used_blind = True
                overhead_cpu, overhead_wall = time.process_time_ns(), time.perf_counter_ns()
                if observation is not None:
                    tracker.update(key, start, index, observation, discovery=used_blind)
                state_cpu += (time.process_time_ns() - overhead_cpu) / 1e6
                state_wall += (time.perf_counter_ns() - overhead_wall) / 1e6
                candidate_times = [
                    {metric: sum(action[i][metric] for action in action_times)
                     + (state_cpu if metric == 'cpu_ms' else state_wall)
                     for metric in ('cpu_ms', 'wall_ms')}
                    for i in range(repetitions)]
                if not reference_first:
                    reference, reference_detail, baseline_times = timed(acquire, repetitions)
                blind_equal = None
                if used_blind:
                    # Verification is outside measured streaming compute.
                    blind_equal = scientific(blind_detail) == scientific(reference_detail)
                    if not blind_equal:
                        raise ValueError('strided blind scientific outputs differ from reference')
                rows.append({
                    'case_id': case['case_id'], 'session_id': case['session_id'],
                    'visit_index': index, 'block_offset': case.get('block_offset'),
                    'rate_hz': rate, 'edge': case['edge'], 'channel': case['channel'], 'rx': rx,
                    'start_counter': start,
                    'end_counter': case['source_end_counter_exclusive'],
                    'reason': reason, 'attempted_cache': attempted_cache, 'used_blind': used_blind,
                    'processed': not outage, 'injected_wrong_cache': injected_cache,
                    'blind_scientific_fields_equal': blind_equal,
                    'prediction': asdict(prediction) if prediction else None,
                    'reference': asdict(reference) if reference else None,
                    'observation': asdict(observation) if observation else None,
                    'matched_reference': bool(reference and observation
                                               and reference_match(reference, observation, rate)),
                    'reference_positive': bool(reference and reference.positive),
                    'candidate_positive': bool(observation and observation.positive),
                    'reference_timed_first': reference_first,
                    'baseline_times': baseline_times, 'candidate_times': candidate_times,
                    'fast_detail': detail,
                })
            if hashlib.sha256(raw).hexdigest() != original_hash:
                raise ValueError('caller IQ mutated')
    summary = summarize(rows)
    for name, expected in baseline_receipt['sources_sha256'].items():
        if sha256(name) != expected:
            raise ValueError('native source changed during replay')
    if sha256(native_library) != baseline_receipt['binary_sha256']:
        raise ValueError('native binary changed during replay')
    if source_hashes != {str(p.relative_to(HERE)): sha256(p) for p in source_paths}:
        raise ValueError('replay source changed during replay')
    result = {'scope': 'causal saved-IQ server replay; not ARM qualification',
              'split': args.split, 'dataset_sha256': sha256(dataset_path),
              'config_sha256': sha256(args.config), 'config': config,
              'source_sha256': source_hashes,
              'native_build_receipt': baseline_receipt,
              'native_sha256': sha256(native_library),
              'baseline_sha256': sha256(baseline_library),
              'host': platform.uname()._asdict(), 'initialization_seconds': initialization,
              'rows': rows, 'summary': summary}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(summary, indent=2))


def summarize(rows):
    def group(subset):
        costs = {side: {metric: sum(median(r[side][i][metric] for i in range(len(r[side])))
                                    for r in subset)
                        for metric in ('cpu_ms', 'wall_ms')}
                 for side in ('baseline_times', 'candidate_times')}
        return {'receiver_visits': len(subset),
                'actions': dict(Counter(r['reason'] for r in subset)),
                'blind_calls': sum(r['used_blind'] for r in subset),
                'cache_attempts': sum(r['attempted_cache'] for r in subset),
                'reference_positives': sum(r['reference_positive'] for r in subset),
                'matched_reference_positives': sum(r['matched_reference'] for r in subset),
                'lost_reference_positives': sum(r['reference_positive']
                                               and not r['matched_reference']
                                               and r.get('processed', True) for r in subset),
                'unprocessed_reference_positives': sum(r['reference_positive']
                                                       and not r.get('processed', True)
                                                       for r in subset),
                'additional_positive_cases': sum(r['candidate_positive']
                                                and not r['matched_reference'] for r in subset),
                'no_candidate_cases': sum(r['observation'] is None for r in subset),
                'unprocessed_cases': sum(not r.get('processed', True) for r in subset),
                'full_coverage_speedup_eligible': all(r.get('processed', True) for r in subset),
                'candidate_positives': sum(r['candidate_positive'] for r in subset),
                'costs': costs,
                'cpu_speedup': (costs['baseline_times']['cpu_ms']
                                / costs['candidate_times']['cpu_ms'])
                if costs['candidate_times']['cpu_ms'] else None,
                'wall_speedup': (costs['baseline_times']['wall_ms']
                                 / costs['candidate_times']['wall_ms'])
                if costs['candidate_times']['wall_ms'] else None}
    return {'all_visits': group(rows),
            'processed_only': group([r for r in rows if r.get('processed', True)]),
            'accepted_cache_only': group([r for r in rows if not r['used_blind']
                                          and r.get('processed', True)]),
            'by_rate': {str(rate): group([r for r in rows if r['rate_hz'] == rate])
                        for rate in sorted({r['rate_hz'] for r in rows})}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=HERE / 'dataset/cases.json')
    parser.add_argument('--split', choices=('dev', 'holdout'), required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorize-holdout', action='store_true')
    run(parser.parse_args())
