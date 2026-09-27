"""Apply the unchanged fixed-window diagnostic to expanded development."""
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
sys.path.insert(0,str(REPORT/'distributed_proposal'))
import diagnostic as search_module
study=search_module.study
write=search_module.write
adapter=study._load_module('expanded_proposals_descriptors',REPORT/'expanded_development/run_hash_adapter.py')


def targets(rows):
    return [(r['case_id'],rx) for r in rows for rx,d in enumerate(r['decisions']) if not d['active']]


def run():
    assert all(os.environ.get(k)=='1' for k in study.THREAD_ENV)
    source=REPORT/'expanded_development/results.hash_adapter.json'
    prior=json.loads(source.read_text());assert prior['complete']
    refs={r['case_id']:r for r in prior['rows']}
    cases={r['case_id']:adapter.descriptor(r) for r in adapter.original.membership()}
    selected=targets(prior['rows'])
    hashes=dict(json.loads((REPORT/'distributed_proposal/source_lock.json').read_text())['files'])
    hashes.update(json.loads((REPORT/'expanded_development/hash_adapter_lock.json').read_text())['files'])
    for path in (Path(__file__).resolve(),HERE/'test_targets.py',HERE/'DESIGN.md',source):
        hashes[str(path)]=study.digest(path)
    assert all(study.digest(p)==h for p,h in hashes.items())
    write(HERE/'source_lock.json',{'files':hashes,'targets':selected,'probes':[0,5,10],'maximum_seconds':120})
    rows=[];error=None;started=time.monotonic();affinity=os.sched_getaffinity(0)
    previous=signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s bound')))
    signal.alarm(120)
    try:
        os.sched_setaffinity(0,{0})
        with ExitStack() as stack:
            engines={}
            for case_id,rx in selected:
                c=cases[case_id];key=c.rate,c.edge
                if key not in engines:
                    engines[key]=search_module.LocalConfirmedEngine(
                        stack.enter_context(search_module.NativeToneGuided(*key)),
                        stack.enter_context(search_module.NativeEarly(*key)))
                engine=engines[key]
                raw=study.dataset.load_iq(c);before=hashlib.sha256(raw).hexdigest()
                reference=tuple(study.dataset.Pair(p['receiver'],study.dataset.Observation(**p['first']),
                    study.dataset.Observation(**p['second'])) for p in refs[case_id]['application_pair_inventory'])
                for probe in (0,5,10):
                    count=engine.confirmation_calls
                    events,timing=study.raw_runner.timed(lambda:search_module.search(raw,c,rx,probe,engine))
                    pair=None
                    if events and events[-1]['accepted']:
                        event=events[-1];points=[]
                        for name in ('seed','confirmation'):
                            p=event[name]
                            points.append(study.dataset.Observation(rx,p['probe_index'],p['probe_start_sample'],
                                p['dwell_epoch_sample'],p['tracking_cfo_hz'],p['margin']))
                        points.sort(key=lambda p:p.probe_index);pair=study.dataset.Pair(rx,*points)
                    assessment=study.dataset.assess_receiver(pair,reference,c,rx,profile='baseline_early')
                    row={'case_id':case_id,'receiver':rx,'rate_hz':c.rate,'probe':probe,'events':events,
                         'timing':timing,'assessment':assessment,'raw_confirmation_calls':engine.confirmation_calls-count}
                    rows.append(row)
                    with (HERE/'rows.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
                assert hashlib.sha256(raw).hexdigest()==before
    except Exception as exc:error=repr(exc)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous);os.sched_setaffinity(0,affinity)
    stable=all(study.digest(p)==h for p,h in hashes.items())
    result={'complete':len(rows)==len(selected)*3 and error is None and stable,'error':error,
            'source_stable':stable,'target_count':len(selected),'rows':rows,'elapsed_seconds':time.monotonic()-started,
            'scope':'Exposed development proposal diagnostic; no primary cost or causal rescue state.'}
    write(HERE/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':run()
