"""Bounded new-controller replay of pre-existing exposed development sessions."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

HERE=Path(__file__).resolve().parent
REPORT=HERE.parent
DATA=REPORT/'dataset'
sys.path.insert(0,str(REPORT/'early_local_tracking'))
from engine_local import create
from run_controls import study, write
annotate=study._load_module('expanded_development_reporting',REPORT/'early_confirmed_tracking/run_reporting_fix.py').annotate


def membership():
    source=json.loads((DATA/'cases.json').read_text())['cases']
    selected=[]
    for rate in (2500000,5000000):
        rows=sorted((r for r in source if r['split']=='dev' and r['rate_hz']==rate),key=lambda r:r['source_start_counter'])
        assert len(rows)==64 and len({r['session_id'] for r in rows})==1
        selected.extend(rows[:32])
    assert len(selected)==64
    return selected


def descriptor(row):
    data=study.dataset
    return data.Case(id=row['case_id'],origin='expanded_exposed_development',split='development',
        cohort='recorded_real_prefix',rate=row['rate_hz'],edge=row['edge'],channel=row['channel'],
        source_counter=row['source_start_counter'],source_end_counter=row['source_end_counter_exclusive'],
        session=row['session_id'],tuning_identity=f"recording:{row['session_id']}:channel:{row['channel']}:edge:{row['edge']}",
        calibration_identity='recording-fixed-unknown-calibration',visit_index=row['visit_index'],
        sequence_id=None,sequence_index=None,raw_path=DATA/row['raw_npy']['path'],
        raw_sha256=row['raw_npy']['sha256'].removeprefix('sha256:'),
        receivers=tuple(data.ReceiverTruth(rx,(),False,'unknown') for rx in (0,1)),
        activity_policy='recorded_unknown',expected_active=None)


def run():
    assert all(os.environ.get(k)=='1' for k in study.THREAD_ENV)
    selected=membership();cases=[descriptor(r) for r in selected]
    hashes=dict(json.loads((REPORT/'early_local_tracking/replay_lock.json').read_text())['files'])
    for path in (Path(__file__).resolve(),HERE/'test_membership.py',HERE/'DESIGN.md',
                 DATA/'cases.json',DATA/'selection_plan.json'):
        hashes[str(path)]=study.digest(path)
    assert all(study.digest(p)==h for p,h in hashes.items())
    write(HERE/'source_lock.json',{'files':hashes,'membership':selected,'maximum_seconds':300})
    rows=[];error=None;started=time.monotonic()
    affinity=os.sched_getaffinity(0)
    previous=signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s bound')))
    signal.alarm(300)
    try:
        os.sched_setaffinity(0,{0})
        with ExitStack() as stack:
            engines={}
            for i,c in enumerate(cases):
                key=c.rate,c.edge,c.session
                if key not in engines:engines[key]=create(stack,c.rate,c.edge)
                detector,port=engines[key]
                raw=study.dataset.load_iq(c);before=hashlib.sha256(raw).hexdigest()
                count=port.confirmation_calls
                outputs={};timings={}
                order=['application','candidate'] if i%2==0 else ['candidate','application']
                for method in order:
                    fn=(lambda:study.common.application_call(raw,c)) if method=='application' else (
                        lambda:study.raw_runner.baseline_call(detector,raw,c))
                    outputs[method],timings[method]=study.raw_runner.timed(fn)
                reference=study.common.application_inventory(outputs['application'],c)
                assessments=[annotate(study.dataset.assess_receiver(d,reference,c,rx,profile='baseline_early'))
                             for rx,d in enumerate(outputs['candidate'])]
                assert hashlib.sha256(raw).hexdigest()==before
                row={'case_id':c.id,'rate_hz':c.rate,'decisions':study.jsonable(outputs['candidate']),
                     'assessments':assessments,'application_pair_inventory':study.jsonable(reference),
                     'timings':timings,'method_order':order,'input_immutable':True,
                     'additional_confirmation_calls':port.confirmation_calls-count}
                rows.append(row)
                with (HERE/'rows.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
                if len(rows)%8==0:print(json.dumps({'completed':len(rows)}),flush=True)
    except Exception as exc:error=repr(exc)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous);os.sched_setaffinity(0,affinity)
    stable=all(study.digest(p)==h for p,h in hashes.items())
    # Save authoritative rows before optional analysis, so a summary bug cannot lose a replay.
    result={'complete':len(rows)==64 and error is None and stable,'error':error,'rows':rows,
            'source_stable':stable,'elapsed_seconds':time.monotonic()-started,'new_holdout_opened':False}
    write(HERE/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':run()
