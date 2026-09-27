"""Fixed early/middle/late proposal study on every inactive development RX."""
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'early_local_tracking'))
from engine_local import LocalConfirmedEngine, NativeEarly, positive
from run_controls import study, write
from native_rescue_detector import (acquire_symbolwise, conditioned_glrt64_score,
    ReceiverFrequencyCalibration, SymbolwiseAcquisitionConfig, SameRxRescueDetector, circular_samples)
from native_tone_guided import NativeToneGuided


def compatible(a, b, rate):
    if not positive(a) or not positive(b) or a.receiver != b.receiver:
        return False
    if abs(a.probe_index - b.probe_index) < 2:
        return False
    predicted = SameRxRescueDetector._transport_epoch(rate, a.local_epoch_sample, a.probe_index, b.probe_index)
    return (abs(circular_samples(b.local_epoch_sample-predicted, rate))/rate <= 2e-6
            and abs(a.tracking_cfo_hz-b.tracking_cfo_hz) <= 8000)


def search(raw, case, receiver, probe_index, engine):
    start = probe_index * case.rate // 100
    probe = raw[start:start+case.rate//50, receiver, 0].astype(float) + 1j*raw[start:start+case.rate//50, receiver, 1]
    acquired = acquire_symbolwise(probe, case.rate,
        ReceiverFrequencyCalibration(receiver_id=str(receiver), center_hz=0., calibration_sha256='0'*64),
        edge=case.edge, config=SymbolwiseAcquisitionConfig(maximum_probe_samples=len(probe),
            retained_candidate_count=10, candidate_epoch_separation_samples=5, candidate_cfo_separation_hz=10000.))
    events = []
    for candidate in acquired.candidates:
        score = conditioned_glrt64_score(probe, case.rate, epoch_sample=candidate.refined_epoch_sample,
            acquired_cfo_hz=candidate.absolute_cfo_hz, edge=case.edge)
        event = {'rank': candidate.rank, 'epoch': candidate.refined_epoch_sample,
                 'acquired_cfo_hz': candidate.absolute_cfo_hz, 'python_score': study.jsonable(score),
                 'seed': None, 'confirmation': None, 'accepted': False}
        if score.margin >= .025:
            seed = engine.guided(raw, receiver=receiver, probe_index=probe_index,
                predicted_local_epoch_sample=float(candidate.refined_epoch_sample),
                scoring_cfo_hz=candidate.absolute_cfo_hz, expected_physical_cfo_hz=score.tracking_cfo_hz)
            event['seed'] = asdict(seed) if seed else None
            if positive(seed):
                second = probe_index + 2 if probe_index <= 8 else probe_index - 2
                epoch = SameRxRescueDetector._transport_epoch(case.rate, float(candidate.refined_epoch_sample), probe_index, second)
                confirmation = engine.guided(raw, receiver=receiver, probe_index=second,
                    predicted_local_epoch_sample=epoch, scoring_cfo_hz=candidate.absolute_cfo_hz,
                    expected_physical_cfo_hz=score.tracking_cfo_hz)
                event['confirmation'] = asdict(confirmation) if confirmation else None
                event['accepted'] = compatible(seed, confirmation, case.rate)
        events.append(event)
        if event['accepted']:
            break
    return events


def run():
    assert all(os.environ.get(k) == '1' for k in study.THREAD_ENV)
    prior_path = HERE.parent / 'early_local_tracking/results.replay.json'
    prior = json.loads(prior_path.read_text()); assert prior['complete']
    ref_path = HERE.parent / 'early_confirmed_tracking/results.reporting_fix.real.json'
    refs = {r['case_id']: r for r in json.loads(ref_path.read_text())['rows']}
    cases = {c.id: c for c in study.cases_for_stage('real')}
    targets = [(r['case_id'], rx) for r in prior['rows'] for rx,d in enumerate(r['decisions']) if not d['active']]
    hashes = dict(json.loads((HERE.parent/'early_local_tracking/replay_lock.json').read_text())['files'])
    # Tone-rescue port has separately pinned science and build dependencies.
    hashes.update(json.loads((HERE.parent/'native_tone_rescue/source_lock.json').read_text())['files'])
    for path in (Path(__file__).resolve(), HERE/'test_diagnostic.py', HERE/'DESIGN.md', prior_path, ref_path):
        hashes[str(path)] = study.digest(path)
    assert all(study.digest(p)==h for p,h in hashes.items())
    write(HERE/'source_lock.json', {'files': hashes, 'targets': targets, 'probes': [0,5,10]})
    rows, error = [], None
    affinity = os.sched_getaffinity(0)
    previous = signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('120s bound')))
    signal.alarm(120); started = time.monotonic()
    try:
        os.sched_setaffinity(0,{0})
        with ExitStack() as stack:
            engines = {}
            for case_id,rx in targets:
                c = cases[case_id]; key = c.rate,c.edge
                if key not in engines:
                    engines[key] = LocalConfirmedEngine(stack.enter_context(NativeToneGuided(*key)), stack.enter_context(NativeEarly(*key)))
                engine = engines[key]
                raw = study.dataset.load_iq(c); before=hashlib.sha256(raw).hexdigest()
                reference = tuple(study.dataset.Pair(p['receiver'], study.dataset.Observation(**p['first']),
                    study.dataset.Observation(**p['second'])) for p in refs[case_id]['application_pair_inventory'])
                for probe in (0,5,10):
                    count = engine.confirmation_calls
                    events,timing = study.raw_runner.timed(lambda:search(raw,c,rx,probe,engine))
                    pair = None
                    if events and events[-1]['accepted']:
                        event=events[-1]; points=[]
                        for name in ('seed','confirmation'):
                            p=event[name]
                            points.append(study.dataset.Observation(rx,p['probe_index'],p['probe_start_sample'],
                                p['dwell_epoch_sample'],p['tracking_cfo_hz'],p['margin']))
                        points.sort(key=lambda p:p.probe_index)
                        pair=study.dataset.Pair(rx,*points)
                    assessment=study.dataset.assess_receiver(pair,reference,c,rx,profile='baseline_early')
                    row={'case_id':case_id,'receiver':rx,'rate_hz':c.rate,'probe':probe,'events':events,
                         'timing':timing,'assessment':assessment,'raw_confirmation_calls':engine.confirmation_calls-count}
                    rows.append(row)
                    with (HERE/'rows.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
                assert hashlib.sha256(raw).hexdigest()==before
    except Exception as exc:
        error=repr(exc)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous);os.sched_setaffinity(0,affinity)
    stable=all(study.digest(p)==h for p,h in hashes.items())
    result={'complete':len(rows)==len(targets)*3 and error is None and stable,'error':error,
        'target_count':len(targets),'source_stable':stable,'elapsed_seconds':time.monotonic()-started,'rows':rows,
        'scope':'Development proposal diagnostic; supplied inactive membership, not an end-to-end detector.'}
    write(HERE/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':run()
