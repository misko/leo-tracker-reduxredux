"""Numerical compatibility on all saved development primary-positive points.

This is not an end-to-end detector evaluation: proposals are supplied from a
previous run and timing excludes discovery and input conversion.
"""
from contextlib import ExitStack
from dataclasses import asdict
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np
from early_profile import HERE, NativeEarly, base, build, verify
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score

sys.path.insert(0, str(HERE.parent / 'native_tone_rescue'))
import run_tone_rescue_evaluation as study


def run():
    output = HERE / 'development_points.json'
    assert not output.exists()
    assert all(os.environ.get(k) == '1' for k in study.THREAD_ENV)
    library = build()
    verify(library)
    source = HERE.parent / 'native_tone_rescue/results.reporting_fix.real.json'
    receipt = json.loads(source.read_text())
    cases = {c.id: c for c in study.cases_for_stage('real')}
    assert len(receipt['rows']) == len(cases) == 64
    assert {r['case_id'] for r in receipt['rows']} == set(cases)
    paths = [Path(__file__).resolve(), HERE / 'early_profile.py', HERE / 'test_early_profile.py',
             HERE / 'DESIGN.md', library, library.with_suffix('.build.json'), source]
    hashes = dict(receipt['source_lock']['files'])
    assert all(base.sha256(Path(p)) == h for p, h in hashes.items())
    hashes.update({str(p): base.sha256(p) for p in paths})
    with (HERE / 'point_replay_lock.json').open('x') as f:
        json.dump({'files': hashes, 'case_ids': list(cases), 'score_at_nearest_integer': True,
                   'maximum_seconds': 120, 'score_tolerance': 1e-5, 'cfo_tolerance_hz': 1.}, f, indent=2)
    affinity = os.sched_getaffinity(0)
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('120s bound')))
    signal.alarm(120)
    rows = []
    error = None
    started = time.monotonic()
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            engines = {}
            for old in receipt['rows']:
                c = cases[old['case_id']]
                raw = study.dataset.load_iq(c)
                before = raw.tobytes()
                key = (c.rate, c.edge)
                if key not in engines:
                    engines[key] = stack.enter_context(NativeEarly(*key))
                for rx, decision in enumerate(old['native_decisions']['native_tracked']):
                    if not decision['active']:
                        continue
                    for member in ('first', 'second'):
                        point = decision['pair'][member]
                        epoch = round(point['local_epoch_sample'])
                        start = point['probe_start_sample']
                        samples = raw[start:start+c.rate//50, rx, 0].astype(float) + 1j * raw[start:start+c.rate//50, rx, 1]
                        python, python_time = study.raw_runner.timed(lambda: conditioned_glrt64_score(
                            samples, c.rate, epoch_sample=epoch, acquired_cfo_hz=point['acquired_cfo_hz'], edge=c.edge))
                        native, native_time = study.raw_runner.timed(lambda: engines[key].guided(
                            raw, receiver=rx, probe_index=point['probe_index'],
                            predicted_local_epoch_sample=float(epoch), scoring_cfo_hz=point['acquired_cfo_hz'],
                            expected_physical_cfo_hz=point['tracking_cfo_hz']))
                        assert native is not None
                        differences = {k: abs(getattr(native, k)-getattr(python, k))
                                       for k in ('exact_score', 'control_score', 'margin', 'tracking_cfo_hz')}
                        rows.append({'case_id': c.id, 'receiver': rx, 'member': member,
                            'probe_index': point['probe_index'], 'epoch': epoch,
                            'python': study.jsonable(python), 'native': asdict(native),
                            'differences': differences, 'python_time': python_time, 'native_time': native_time,
                            'within_tolerance': all(v <= (1. if k == 'tracking_cfo_hz' else 1e-5) for k, v in differences.items())})
                assert raw.tobytes() == before
    except Exception as exc:
        error = repr(exc)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(base.sha256(Path(p)) == h for p, h in hashes.items())
    expected = sum(2 for r in receipt['rows'] for d in r['native_decisions']['native_tracked'] if d['active'])
    result = {'complete': error is None and len(rows) == expected and stable,
              'error': error, 'source_stable': stable, 'expected_points': expected,
              'elapsed_seconds': time.monotonic()-started, 'rows': rows,
              'within_tolerance_count': sum(r['within_tolerance'] for r in rows),
              'new_holdout_iq_opened': False,
              'scope': 'Supplied development hypotheses, rounded integer timing; not a detector benchmark.'}
    with output.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    run()
