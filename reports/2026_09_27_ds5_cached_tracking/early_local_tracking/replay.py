"""Causal development replay against saved application evidence; no speedup claim."""
from contextlib import ExitStack
import hashlib
import json
import os
import signal
import time

from engine_local import HERE, create
from run_controls import study, write
annotate = study._load_module('local_tracking_reporting_adapter',
    HERE.parent / 'early_confirmed_tracking/run_reporting_fix.py').annotate


def run():
    controls = json.loads((HERE / 'results.controls.json').read_text())
    assert controls['complete'] and not controls['failures']
    assert all(os.environ.get(k) == '1' for k in study.THREAD_ENV)
    prior_path = HERE.parent / 'early_confirmed_tracking/results.reporting_fix.real.json'
    prior = json.loads(prior_path.read_text())
    assert prior['complete']
    reference_rows = {r['case_id']: r for r in prior['rows']}
    cases = study.cases_for_stage('real')
    assert len(cases) == len(reference_rows) == 64
    hashes = dict(json.loads((HERE / 'source_lock.json').read_text())['files'])
    for path in (HERE / 'replay.py', HERE / 'REPLAY.md', prior_path,
                 HERE / 'results.controls.json', HERE.parent / 'early_confirmed_tracking/run_reporting_fix.py'):
        hashes[str(path)] = study.digest(path)
    assert all(study.digest(p) == h for p, h in hashes.items())
    write(HERE / 'replay_lock.json', {'files': hashes, 'membership': [c.id for c in cases],
        'reference_source': str(prior_path), 'scope': 'Saved reference inventory; candidate timing only.'})
    rows, error = [], None
    affinity = os.sched_getaffinity(0)
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('60s bound')))
    signal.alarm(60)
    started = time.monotonic()
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            detectors = {}
            for c in cases:
                key = c.rate, c.edge, c.session
                if key not in detectors:
                    detectors[key] = create(stack, c.rate, c.edge)
                detector, port = detectors[key]
                raw = study.dataset.load_iq(c)
                before = hashlib.sha256(raw).hexdigest()
                count = port.confirmation_calls
                decisions, timing = study.raw_runner.timed(lambda: study.raw_runner.baseline_call(detector, raw, c))
                reference = tuple(study.dataset.Pair(p['receiver'],
                    study.dataset.Observation(**p['first']), study.dataset.Observation(**p['second']))
                    for p in reference_rows[c.id]['application_pair_inventory'])
                assessments = [annotate(study.dataset.assess_receiver(d, reference, c, rx, profile='baseline_early'))
                               for rx, d in enumerate(decisions)]
                assert hashlib.sha256(raw).hexdigest() == before
                rows.append({'case_id': c.id, 'rate_hz': c.rate, 'decisions': study.jsonable(decisions),
                    'assessments': assessments, 'timing': timing, 'input_immutable': True,
                    'additional_confirmation_calls': port.confirmation_calls-count})
                # Checkpoint outside timing before any final summarization.
                with (HERE / 'replay_rows.jsonl').open('a') as stream:
                    stream.write(json.dumps(rows[-1], allow_nan=False) + '\n')
    except Exception as exc:
        error = repr(exc)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    summary = {}
    for rate in (2500000, 5000000):
        selected = [r for r in rows if r['rate_hz'] == rate]
        assessments = [a for r in selected for a in r['assessments']]
        summary[str(rate)] = {k: sum(a[k] for a in assessments) for k in (
            'reference_active', 'matched_reference', 'lost_reference', 'additional_or_mismatched')}
        summary[str(rate)].update(visits=len(selected),
            lost_reference_visits=sum(any(a['reference_active'] for a in r['assessments']) and
                not any(a['matched_reference'] for a in r['assessments']) for r in selected),
            cpu_sum_ms=sum(r['timing']['process_cpu_ms'] for r in selected),
            wall_max_ms=max((r['timing']['wall_ms'] for r in selected), default=None))
    stable = all(study.digest(p) == h for p, h in hashes.items())
    result = {'complete': len(rows) == 64 and error is None and stable, 'error': error,
              'source_stable': stable, 'rows': rows, 'summary': summary,
              'elapsed_seconds': time.monotonic()-started,
              'timing_scope': 'Complete candidate call only; no paired application speedup measurement.'}
    write(HERE / 'results.replay.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    run()
