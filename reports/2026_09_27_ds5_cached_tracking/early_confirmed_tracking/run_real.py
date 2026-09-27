"""Paired complete-call replay of the original development corpus."""
from contextlib import ExitStack
import hashlib
import json
import os
import signal
import time

from engine import HERE, NativeTradeoffDetector, base, create
from run_controls import study, write


def summarize(rows):
    output = {}
    for rate in (2500000, 5000000):
        selected = [r for r in rows if r['rate_hz'] == rate]
        methods = {}
        for method in ('application', 'native_tracked', 'early_confirmed'):
            cpu = sum(r['timings'][method]['process_cpu_ms'] for r in selected)
            wall = sorted(r['timings'][method]['wall_ms'] for r in selected)
            entry = {'cpu_sum_ms': cpu, 'cpu_mean_ms': cpu / len(selected) if selected else None,
                     'wall_max_ms': max(wall, default=None), 'wall_over_120ms': sum(t > 120 for t in wall)}
            if method != 'application':
                assessments = [a for r in selected for a in r['assessments'][method]]
                entry.update({k: sum(a[k] for a in assessments) for k in (
                    'reference_active', 'matched_reference', 'lost_reference', 'additional_or_mismatched')})
                entry['lost_reference_visits'] = sum(
                    any(a['reference_active'] for a in r['assessments'][method]) and
                    not any(a['matched_reference'] for a in r['assessments'][method]) for r in selected)
                entry['speedup_vs_application'] = methods['application']['cpu_sum_ms'] / cpu if cpu else None
            methods[method] = entry
        output[str(rate)] = {'visits': len(selected), 'methods': methods}
    return output


def run():
    assert all(os.environ.get(k) == '1' for k in study.THREAD_ENV)
    controls = json.loads((HERE / 'results.controls.json').read_text())
    assert controls['complete'] and not controls['failures']
    cases = study.cases_for_stage('real')
    hashes = dict(json.loads((HERE / 'source_lock.json').read_text())['files'])
    assert all(study.digest(p) == h for p, h in hashes.items())
    for path in (HERE / 'run_real.py', HERE / 'REAL_DESIGN.md', HERE / 'results.controls.json'):
        hashes[str(path)] = study.digest(path)
    write(HERE / 'real_source_lock.json', {'files': hashes, 'case_ids': [c.id for c in cases]})
    affinity = os.sched_getaffinity(0)
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('300s bound')))
    signal.alarm(300)
    rows, error = [], None
    started = time.monotonic()
    try:
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            engines = {}
            for i, c in enumerate(cases):
                key = (c.rate, c.edge, c.session)
                if key not in engines:
                    candidate, port = create(stack, c.rate, c.edge)
                    baseline = NativeTradeoffDetector(stack.enter_context(base.NativeGuidedBoundary(c.rate, c.edge)))
                    engines[key] = candidate, port, baseline
                candidate, port, baseline = engines[key]
                raw = study.dataset.load_iq(c)
                before = hashlib.sha256(raw).hexdigest()
                count = port.confirmation_calls
                order = ['application', 'native_tracked', 'early_confirmed']
                order = order[i % 3:] + order[:i % 3]
                outputs, timings = {}, {}
                for method in order:
                    if method == 'application':
                        fn = lambda: study.common.application_call(raw, c)
                    else:
                        selected = baseline if method == 'native_tracked' else candidate
                        fn = lambda: study.raw_runner.baseline_call(selected, raw, c)
                    outputs[method], timings[method] = study.raw_runner.timed(fn)
                reference = study.common.application_inventory(outputs['application'], c)
                assessments = {method: [study.dataset.assess_receiver(d, reference, c, rx,
                    profile='baseline_early' if method == 'early_confirmed' else 'native_diverse')
                    for rx, d in enumerate(outputs[method])] for method in ('native_tracked', 'early_confirmed')}
                assert hashlib.sha256(raw).hexdigest() == before
                rows.append({'case_id': c.id, 'rate_hz': c.rate, 'method_order': order,
                    'timings': timings, 'assessments': assessments,
                    'decisions': {m: study.jsonable(outputs[m]) for m in assessments},
                    'additional_confirmation_calls': port.confirmation_calls-count,
                    'input_immutable': True, 'application_pair_inventory': study.jsonable(reference)})
                if len(rows) % 8 == 0:
                    print(json.dumps({'completed': len(rows)}), flush=True)
    except Exception as exc:
        error = repr(exc)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(study.digest(p) == h for p, h in hashes.items())
    result = {'complete': len(rows) == 64 and error is None and stable, 'error': error,
              'source_stable': stable, 'rows': rows, 'summary': summarize(rows),
              'elapsed_seconds': time.monotonic()-started, 'new_holdout_opened': False}
    write(HERE / 'results.real.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    run()
