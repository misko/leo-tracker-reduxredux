"""Frozen bounded controls for the new confirmation-before-cache adapter."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np
from engine import HERE, create
sys.path.insert(0, str(HERE.parent / 'native_tone_rescue'))
import run_tone_rescue_evaluation as study


def write(path, payload):
    with path.open('x') as f:
        json.dump(payload, f, indent=2, allow_nan=False)


def run():
    assert all(os.environ.get(k) == '1' for k in study.THREAD_ENV)
    controls = study.cases_for_stage('controls')
    parents = study.raw_runner.supplemental_negative_parents()
    executions = [(c, 'original') for c in controls] + [
        (c, orientation) for c in parents for orientation in ('original', 'rxswap-v1')]
    assert len(executions) == 66
    parent = json.loads((HERE.parent / 'native_early_profile/point_replay_lock.json').read_text())
    hashes = dict(parent['files'])
    assert all(study.digest(p) == h for p, h in hashes.items())
    hashes.update({str(p.resolve()): study.digest(p) for p in HERE.iterdir() if p.suffix in ('.py', '.md')})
    write(HERE / 'source_lock.json', {'files': hashes,
        'membership': [(c.id, o, c.raw_sha256) for c, o in executions], 'timeout_seconds': 120})
    affinity = os.sched_getaffinity(0)
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('120s bound')))
    signal.alarm(120)
    rows, error = [], None
    started = time.monotonic()
    try:
        os.sched_setaffinity(0, {0})
        for c, orientation in executions:
            raw = study.dataset.load_iq(c)
            if orientation == 'rxswap-v1':
                raw = np.ascontiguousarray(raw[:, (1, 0), :])
                c = study.raw_runner.swapped_case(c, hashlib.sha256(raw).hexdigest())
            raw.setflags(write=False)
            before = hashlib.sha256(raw).hexdigest()
            with ExitStack() as stack:
                detector, engine = create(stack, c.rate, c.edge)
                decisions, timings = study.raw_runner.timed(lambda: study.raw_runner.baseline_call(detector, raw, c))
                additional = engine.confirmation_calls
            assessments = [study.dataset.assess_receiver(d, (), c, rx, profile='baseline_early')
                           for rx, d in enumerate(decisions)]
            assert hashlib.sha256(raw).hexdigest() == before
            rows.append({'case_id': c.id, 'orientation': orientation, 'rate_hz': c.rate,
                         'decisions': study.jsonable(decisions), 'assessments': assessments,
                         'timings': timings, 'additional_confirmation_calls': additional,
                         'input_immutable': True})
    except Exception as exc:
        error = repr(exc)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(study.digest(p) == h for p, h in hashes.items())
    failures = [{'case_id': r['case_id'], 'orientation': r['orientation'], 'assessment': a}
                for r in rows for a in r['assessments'] if a['activity_policy_passed'] is False]
    result = {'complete': error is None and len(rows) == 66 and stable, 'error': error,
              'source_stable': stable, 'elapsed_seconds': time.monotonic()-started,
              'failures': failures, 'rows': rows, 'new_holdout_opened': False}
    write(HERE / 'results.controls.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    run()
