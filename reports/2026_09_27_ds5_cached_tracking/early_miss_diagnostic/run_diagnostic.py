"""Localize two development regressions without changing the detector."""
from contextlib import ExitStack
from dataclasses import asdict
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'early_confirmed_tracking'))
from engine import NativeEarly, NativeTradeoffDetector, base, positive
from run_controls import study, write


def failures(point):
    if point is None:
        return ['no_observation']
    return [name for name, failed in (
        ('status', point.status != 0), ('support', not point.supported),
        ('bounds', not point.valid_bounds), ('frames', point.support_frames < 2),
        ('fractional_complete', not point.fractional_complete), ('margin', point.margin < .025)) if failed]


def run():
    import os
    import signal
    import time
    assert all(os.environ.get(k) == '1' for k in study.THREAD_ENV)
    receipt_path = HERE.parent / 'early_confirmed_tracking/results.reporting_fix.real.json'
    receipt = json.loads(receipt_path.read_text())
    targets = []
    for row in receipt['rows']:
        for rx, (old, new) in enumerate(zip(row['assessments']['native_tracked'], row['assessments']['early_confirmed'])):
            if old['matched_reference'] and not new['matched_reference']:
                targets.append((row['case_id'], rx))
    assert len(targets) == 2
    cases = {c.id: c for c in study.cases_for_stage('real')}
    hashes = dict(json.loads((HERE.parent / 'early_confirmed_tracking/reporting_fix_lock.json').read_text())['files'])
    for path in (Path(__file__).resolve(), HERE / 'test_diagnostic.py', HERE / 'DESIGN.md', receipt_path):
        hashes[str(path)] = study.digest(path)
    assert all(study.digest(p) == h for p, h in hashes.items())
    write(HERE / 'source_lock.json', {'files': hashes, 'targets': targets, 'offsets': [-1, 0, 1]})
    affinity = os.sched_getaffinity(0)
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('60s bound')))
    signal.alarm(60)
    rows, error = [], None
    started = time.monotonic()
    try:
        os.sched_setaffinity(0, {0})
        for case_id, rx in targets:
            c = cases[case_id]
            raw = study.dataset.load_iq(c)
            before = raw.tobytes()
            with ExitStack() as stack:
                discovery = stack.enter_context(base.NativeGuidedBoundary(c.rate, c.edge))
                confirmation = stack.enter_context(NativeEarly(c.rate, c.edge))
                proposals = discovery.blind(raw, receiver=rx, screen=discovery.screen(raw, receiver=rx))
                points = []
                for proposal in proposals:
                    local = round(proposal.local_epoch_sample)
                    checks = {}
                    for offset in (-1, 0, 1):
                        observation = confirmation.guided(raw, receiver=rx, probe_index=proposal.probe_index,
                            predicted_local_epoch_sample=float(local+offset), scoring_cfo_hz=proposal.acquired_cfo_hz,
                            expected_physical_cfo_hz=proposal.tracking_cfo_hz)
                        checks[str(offset)] = {'observation': asdict(observation) if observation else None,
                                             'failures': failures(observation)}
                    points.append({'proposal': asdict(proposal), 'proposal_failures': failures(proposal), 'checks': checks})
                # Pair only proposals eligible under the frozen discovery veto.
                pairs = {}
                for offset in (-1, 0, 1):
                    eligible = [p['checks'][str(offset)]['observation'] for p in points
                                if not p['proposal_failures'] and not p['checks'][str(offset)]['failures']]
                    pairs[str(offset)] = [
                        [a['probe_index'], b['probe_index']] for a in eligible for b in eligible
                        if b['probe_index'] - a['probe_index'] >= 2
                        and abs(b['tracking_cfo_hz'] - a['tracking_cfo_hz']) <= 8000]
                rows.append({'case_id': case_id, 'receiver': rx, 'points': points, 'pairs_by_offset': pairs})
            assert raw.tobytes() == before
    except Exception as exc:
        error = repr(exc)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        os.sched_setaffinity(0, affinity)
    stable = all(study.digest(p) == h for p, h in hashes.items())
    result = {'complete': error is None and len(rows) == 2 and stable,
              'error': error, 'source_stable': stable, 'rows': rows,
              'elapsed_seconds': time.monotonic()-started,
              'scope': 'Post-hoc development cold acquisition diagnostic; not a causal replay or fresh validation.'}
    write(HERE / 'results.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    run()
