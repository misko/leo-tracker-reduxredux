"""Bounded qualification on original, separately selected recorded sessions."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DATA = REPORT/'dataset'
sys.path.insert(0, str(REPORT/'native_tone_rescue'))
import run_tone_rescue_evaluation as engine

LOCK = HERE/'source_lock.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def membership():
    rows = [r for r in json.loads((DATA/'cases.json').read_text())['cases'] if r['split']=='holdout']
    rows.sort(key=lambda r: (r['rate_hz'],r['session_id'],r['source_start_counter']))
    assert len(rows)==128 and len({r['session_id'] for r in rows})==2
    for rate in (2500000,5000000):
        selected=[r for r in rows if r['rate_hz']==rate]
        assert len(selected)==64 and len({r['session_id'] for r in selected})==1
        assert all(b['source_start_counter']>a['source_start_counter'] for a,b in zip(selected,selected[1:]))
    return rows


def case(row):
    data=engine.dataset
    return data.Case(id=row['case_id'], origin='recorded_holdout', split='holdout',
        cohort='recorded_real_prefix', rate=row['rate_hz'], edge=row['edge'],channel=row['channel'],
        source_counter=row['source_start_counter'],source_end_counter=row['source_end_counter_exclusive'],
        session=row['session_id'], tuning_identity=f"recording:{row['session_id']}:channel:{row['channel']}:edge:{row['edge']}",
        calibration_identity='recording-fixed-unknown-calibration',visit_index=row['visit_index'],
        sequence_id=None,sequence_index=None,raw_path=DATA/row['raw_npy']['path'],
        raw_sha256=row['raw_npy']['sha256'].removeprefix('sha256:'),
        receivers=tuple(data.ReceiverTruth(rx,(),False,'unknown') for rx in (0,1)),
        activity_policy='recorded_unknown',expected_active=None)


def freeze():
    parent=json.loads((REPORT/'native_tone_rescue/source_lock.json').read_text())
    files=dict(parent['files'])
    for path in (Path(__file__),HERE/'test_recorded_tone_holdout.py',HERE/'DESIGN.md',
                 DATA/'cases.json',DATA/'selection_plan.json',
                 REPORT/'native_tone_rescue/source_lock.json',
                 REPORT/'tone_validation/results.timing_adapter.json'):
        files[str(path.resolve())]=digest(path)
    assert all(digest(n)==h for n,h in files.items())
    write(LOCK,{'files':files,'membership':membership(),'frozen_before_holdout_iq':True})


def run(rate):
    target=HERE/f'results.{rate}.json'
    assert not target.exists()
    lock=json.loads(LOCK.read_text()); lockhash=digest(LOCK)
    assert all(digest(n)==h for n,h in lock['files'].items())
    assert lock['membership']==membership()
    cases=[case(r) for r in lock['membership'] if r['rate_hz']==rate]
    assert all(os.environ.get(n)=='1' for n in engine.THREAD_ENV)
    affinity=os.sched_getaffinity(0); assert 0 in affinity
    rows=[];error=None;started=time.monotonic()
    previous=signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('300s bound')))
    signal.alarm(300)
    try:
        os.sched_setaffinity(0,{0})
        with ExitStack() as stack:
            detectors=engine._make_detectors(stack,(rate,cases[0].edge),include_raw=False)
            for index,c in enumerate(cases):
                assert digest(c.raw_path)==c.raw_sha256
                raw=np.load(c.raw_path,allow_pickle=False)
                assert raw.dtype==np.dtype('<i2') and raw.shape==(c.sample_count,2,2)
                raw.setflags(write=False); before=hashlib.sha256(raw).hexdigest()
                methods=['application','native_tracked','tone_rescue'];methods=methods[index%3:]+methods[:index%3]
                outputs={};times={}
                for method in methods:
                    outputs[method],times[method]=engine.raw_runner.timed(
                        lambda:engine._call(method,detectors.get(method),raw,c))
                reference=engine.common.application_inventory(outputs['application'],c)
                decisions={m:engine._decisions(m,outputs[m]) for m in ('native_tracked','tone_rescue')}
                for rx in (0,1):
                    if decisions['native_tracked'][rx].active:
                        assert decisions['native_tracked'][rx]==decisions['tone_rescue'][rx]
                assessments,visits=engine._assess(decisions,reference,c)
                assert hashlib.sha256(raw).hexdigest()==before
                rows.append({'case_id':c.id,'rate_hz':rate,'source_counter':c.source_counter,
                    'session_id':c.session,'channel':c.channel,'edge':c.edge,'method_order':methods,
                    'raw_sha256':c.raw_sha256,'input_immutable':True,'timings':times,
                    'native_decisions':engine.jsonable(decisions),'native_assessments':assessments,
                    'visit_assessments':visits,'application_pair_inventory':engine.jsonable(reference),
                    'tone_rescue_result':engine.jsonable(outputs['tone_rescue']),
                    'primary_decision_parity':engine.primary_parity(outputs)})
                print(json.dumps({'rate':rate,'completed':len(rows),'case':c.id}),flush=True)
    except Exception as caught:
        error=repr(caught)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous);os.sched_setaffinity(0,affinity)
    stable=digest(LOCK)==lockhash and all(digest(n)==h for n,h in lock['files'].items())
    summary=engine.summarize('real',rows)
    quality=summary['by_rate'].get(str(rate),{}).get('quality',{})
    q=quality.get('tone_rescue',{});b=quality.get('native_tracked',{})
    gates={'complete':len(rows)==64 and error is None and stable,
        'retention_97_percent':q.get('miss_fraction') is not None and q['miss_fraction']<=.03,
        'no_lost_positive_visits':q.get('lost_reference_visits')==0,
        'no_new_unmatched_receivers':q.get('additional_or_mismatched_active_receivers',1)<=b.get('additional_or_mismatched_active_receivers',0),
        'tenfold_cpu':summary['by_rate'].get(str(rate),{}).get('methods',{}).get('tone_rescue',{}).get('aggregate_cpu_speedup_vs_application',0)>=10}
    write(target,{'rows':rows,'summary':summary,'gates':gates,'error':error,
        'source_lock_sha256':lockhash,'source_lock_stable':stable,'recorded_holdout_opened':True,
        'affinity_cpu':0,'numerical_threads':1,'elapsed_seconds':time.monotonic()-started})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','2500000','5000000'))
    action=parser.parse_args().action
    freeze() if action=='freeze' else run(int(action))
