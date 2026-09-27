"""Freeze, materialize and evaluate the previously reserved constructed split."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATA = REPORT / 'tg11_diagnostic/dataset'
TONE = REPORT / 'native_tone_rescue'
sys.path.insert(0, str(TONE))
import run_tone_rescue_evaluation as evaluation

spec = importlib.util.spec_from_file_location('reserved_tone_generator', DATA / 'build_dataset.py')
generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)
LOCK = HERE / 'source_lock.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def metadata_equal(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(metadata_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(metadata_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-12)
    return type(a) is type(b) and a == b


def metadata():
    generator.verify_source_lock()
    design = json.loads((DATA / 'design.json').read_text())
    reserved = [r for r in json.loads((DATA / 'cases.json').read_text())['cases']
                if r['split'] == 'validation']
    specs = [s for s in generator.enumerate_specs(design) if s['split'] == 'validation']
    assert len(specs) == len(reserved) == 26
    assert [s['case_id'] for s in specs] == [r['case_id'] for r in reserved]
    for s, row in zip(specs, reserved):
        for rx in (0, 1):
            _, truth = generator.build_receiver(s, rx, design, materialize=False)
            assert metadata_equal(truth, row['receivers'][rx]), row['case_id']
    return design, specs, reserved


def freeze():
    _, specs, reserved = metadata()
    parent = json.loads((TONE / 'source_lock.json').read_text())
    files = dict(parent['files'])
    required = [Path(__file__), HERE / 'test_tone_validation.py', HERE / 'DESIGN.md',
                DATA / 'build_dataset.py', DATA / 'design.json', DATA / 'cases.json',
                DATA / 'source_lock.json', DATA / 'test_tg11_diagnostic_dataset.py',
                DATA.parent / 'DATASET_PLAN.md', TONE / 'source_lock.json',
                TONE / 'results.reporting_fix.real.json']
    for path in required:
        files[str(path.resolve())] = digest(path)
    assert all(digest(name) == value for name, value in files.items())
    assert not any((HERE / 'iq' / (r['case_id']+'.npy')).exists() for r in reserved)
    write_new(LOCK, {'files': files, 'membership': [r['case_id'] for r in reserved],
        'specs_sha256': evaluation.stable_hash(specs), 'frozen_before_validation_iq': True})


def verify():
    lock = json.loads(LOCK.read_text())
    assert all(digest(name) == value for name, value in lock['files'].items())
    return lock


def generate():
    lock = verify()
    design, specs, reserved = metadata()
    assert evaluation.stable_hash(specs) == lock['specs_sha256']
    rows = []
    started = time.monotonic()
    for spec, original in zip(specs, reserved):
        assert time.monotonic()-started < 60
        built = [generator.build_receiver(spec, rx, design, materialize=True) for rx in (0, 1)]
        raw = np.stack([b[0] for b in built], axis=1)
        path = HERE / 'iq' / (spec['case_id']+'.npy')
        path.parent.mkdir(exist_ok=True)
        with path.open('xb') as stream:
            np.save(stream, raw, allow_pickle=False)
        rows.append({**original, 'receivers': [b[1] for b in built],
            'validation_materialized': True,
            'raw_npy': {'path': str(path), 'sha256': digest(path), 'shape': list(raw.shape),
                        'dtype': str(raw.dtype)}})
    verify()
    write_new(HERE / 'generated.json', {'validation_iq_opened': True,
        'source_lock_sha256': digest(LOCK), 'cases': rows,
        'elapsed_seconds': time.monotonic()-started})


def case_from(row):
    data = evaluation.dataset
    receivers = tuple(data.ReceiverTruth(receiver=rx,
        components=tuple(data._diagnostic_component(c, row['rate_hz']*120//1000)
                         for c in row['receivers'][rx]['components']),
        constructed_negative=row['receivers'][rx]['constructed_negative'],
        ambiguity=row['receivers'][rx]['ambiguity']) for rx in (0, 1))
    negative = all(r.constructed_negative for r in receivers)
    return data.Case(id=row['case_id'], origin=row['origin'], split='validation',
        cohort=row['cohort'], rate=row['rate_hz'], edge=row['edge'], channel=row['channel'],
        source_counter=row['source_start_counter'], source_end_counter=row['source_end_counter_exclusive'],
        session=row['session_id'], tuning_identity=row['tuning_identity'],
        calibration_identity='tg11diag-constructed-fixed-calibration',
        visit_index=row['sequence_index'] or 0, sequence_id=row['sequence_id'],
        sequence_index=row['sequence_index'], raw_path=Path(row['raw_npy']['path']),
        raw_sha256=row['raw_npy']['sha256'], receivers=receivers,
        activity_policy='required_inactive' if negative else 'regional_report_only'
            if row['cohort'].startswith('symbol-region') else 'presence_report_only',
        expected_active=False if negative else None)


def run():
    lock = verify()
    generation_path = HERE / 'generated.json'
    generation_hash = digest(generation_path)
    generated = json.loads(generation_path.read_text())
    assert generated['source_lock_sha256'] == digest(LOCK)
    cases = [case_from(row) for row in generated['cases']]
    assert [c.id for c in cases] == lock['membership']
    affinity = os.sched_getaffinity(0)
    assert 0 in affinity
    assert all(os.environ.get(n) == '1' for n in evaluation.THREAD_ENV)
    rows, error = [], None
    started = time.monotonic()
    old_handler = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('120s bound')))
    signal.alarm(120)
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            engines = {g: evaluation._make_detectors(stack, g, include_raw=False)
                       for g in sorted({(c.rate, c.edge) for c in cases})}
            for index, case in enumerate(cases):
                assert digest(case.raw_path) == case.raw_sha256
                raw = np.load(case.raw_path, allow_pickle=False)
                assert raw.dtype == np.dtype('<i2') and raw.shape == (case.sample_count, 2, 2)
                raw.setflags(write=False)
                before = hashlib.sha256(raw).hexdigest()
                order = ['application', 'native_tracked', 'tone_rescue']
                order = order[index%3:] + order[:index%3]
                outputs, timings = {}, {}
                for method in order:
                    outputs[method], timings[method] = evaluation.timed(lambda: evaluation._call(
                        method, engines[(case.rate, case.edge)].get(method), raw, case))
                reference = evaluation.common.application_inventory(outputs['application'], case)
                decisions = {m: evaluation._decisions(m, outputs[m]) for m in ('native_tracked', 'tone_rescue')}
                for rx in (0, 1):
                    if decisions['native_tracked'][rx].active:
                        assert decisions['native_tracked'][rx] == decisions['tone_rescue'][rx]
                assessments, visits = evaluation._assess(decisions, reference, case)
                assert before == hashlib.sha256(raw).hexdigest()
                rows.append({'case_id': case.id, 'rate_hz': case.rate, 'method_order': order,
                    'raw_sha256': case.raw_sha256, 'input_immutable': True,
                    'truth': evaluation.jsonable(case.receivers), 'timings': timings,
                    'native_assessments': assessments, 'visit_assessments': visits,
                    'native_decisions': evaluation.jsonable(decisions),
                    'primary_decision_parity': evaluation.primary_parity(outputs),
                    'application_pair_inventory': evaluation.jsonable(reference),
                    'tone_rescue_result': evaluation.jsonable(outputs['tone_rescue'])})
                print(json.dumps({'completed': len(rows), 'case_id': case.id}), flush=True)
    except Exception as caught:
        error = repr(caught)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        os.sched_setaffinity(0, affinity)
    stable = all(digest(n) == h for n, h in lock['files'].items()) and digest(generation_path) == generation_hash
    summary = evaluation.summarize('diagnostic', rows)
    gates = {
        'complete': len(rows) == 26 and error is None and stable,
        'required_truth': all(a['activity_policy_passed'] is not False for r in rows
                             for a in r['native_assessments']['tone_rescue']),
        'no_unassociated_positive': all(not a['candidate_active'] or a['truth_association']['matched']
                             for r in rows for a in r['native_assessments']['tone_rescue']),
        'tenfold_each_rate': all(v['methods']['tone_rescue']['aggregate_cpu_speedup_vs_application'] >= 10
                                for v in summary['by_rate'].values()) and len(summary['by_rate']) == 2,
    }
    write_new(HERE / 'results.json', {'rows': rows, 'summary': summary, 'gates': gates,
        'error': error, 'source_lock_stable': stable, 'source_lock_sha256': digest(LOCK),
        'generation_sha256': generation_hash, 'validation_iq_opened': True,
        'original_real_holdout_opened': False, 'elapsed_seconds': time.monotonic()-started})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'generate', 'run'))
    {'freeze': freeze, 'generate': generate, 'run': run}[parser.parse_args().action]()
