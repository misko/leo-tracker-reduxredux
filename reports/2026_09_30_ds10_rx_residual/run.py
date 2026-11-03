import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
SOURCE=REPORTS/'2026_09_29_ds10_geographic'


def read(path):
    return json.loads(path.read_text())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    started=time.monotonic()
    plan_path=SOURCE/'plan.json'
    fit_path=SOURCE/'fits/N24_h0/result.json'
    plan,baseline=read(plan_path),read(fit_path)
    hashes={}
    for obj in [plan,baseline]:
        for name,digest in obj['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            hashes[name]=digest
    assert baseline['selected']['qualified']
    sessions=baseline['sessions']
    assert sessions==plan['panels']['N24'] and len(sessions)==24
    by_id={r['session_id']:r for r in plan['captures']}
    inputs=[read(SOURCE/'exports'/by_id[s]['unit_id']/'validated.json')['input'] for s in sessions]
    helper=module('budget',REPORTS/'2026_09_29_scan_budget/run.py').helper
    transfer_path=REPORTS/'2026_09_29_candidate_rx_transfer/transfer.py'
    transfer=module('rx_transfer',transfer_path)
    shape_path=REPORTS/'2026_09_29_donor_residual_transfer/residual.py'
    shape=module('residual_shape',shape_path).shape
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=inputs))
    model=helper.TrendMixturePosition(docs,plan['config'],helper.baseline.Stationary,.2)
    x=baseline['selected']['x']
    scored=model.evaluate(x,gradient=False,held=True)
    assert abs(scored['score']-baseline['selected']['score'])<1e-7
    assert abs(sum(r['held_log_score'] for r in scored['rows'])-baseline['selected']['held_score'])<1e-7
    posterior={(r['session_id'],r['track_id']):r for r in scored['rows']}
    cases=[]
    excluded=[]
    for i,(doc,entry,engine) in enumerate(zip(docs,inputs,model.models,strict=True)):
        assert doc['session_id']==sessions[i]
        meta_path=next(Path(a['path']) for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.json'))
        bank_path=next(Path(a['path']) for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.npz'))
        meta={r['track_id']:r for r in read(meta_path)['tracks']}
        with np.load(bank_path,allow_pickle=False) as bank:
            for track in doc['tracks']:
                p=posterior[doc['session_id'],track['track_id']]
                weights=np.asarray(p['weights_given_signal'])
                slot=int(np.argmax(weights))
                probability=float(weights[slot]*p['signal_responsibility'])
                key=dict(session_id=doc['session_id'],track_id=track['track_id'])
                if probability<.5:
                    excluded.append(dict(key,reason='weak_candidate'))
                    continue
                pred,visible=engine.prediction(track,[*x[:2],x[i+2]])
                assert visible[slot]
                residual=track['y']-pred[slot]
                stats=shape(track['times_s'],residual,track['mask'])
                if stats is None:
                    excluded.append(dict(key,reason='short_training_support'))
                    continue
                index=meta[track['track_id']]['index']
                # Reused helper names the grouping field number; here it is strictly a scan-local catalogue index.
                identity=int(bank[f'candidate_ids_{index}'][slot])
                cases.append(dict(key,unit_id='DS10_N24',number=identity,identity_namespace='scan_local_catalogue_index',
                                  receiver_id=track['receiver_id'],rf_hz=track['rf_hz'],times=list(track['times_s']),
                                  residual=residual.tolist(),mask=track['mask'].tolist(),shape=stats,signal_probability=probability))
    rows=[]
    for c in cases:
        same,other=transfer.predict(c,cases),transfer.predict(c,cases,False)
        t,e=transfer.training(c)
        rows.append(dict(session_id=c['session_id'],track_id=c['track_id'],number=c['number'],receiver_id=c['receiver_id'],
                         candidate_predictor=same,other_predictor=other,zero=transfer.error(c,0),
                         candidate=transfer.error(c,same['slope'] if same else 0),
                         other=transfer.error(c,other['slope'] if other else 0),own=transfer.error(c,transfer.slope(t,e))))
    groups=dict(all=rows,supported=[r for r in rows if r['candidate_predictor']],
                matched=[r for r in rows if r['candidate_predictor'] and r['other_predictor']])
    summary={k:transfer.summarize(v) for k,v in groups.items()}
    summary['scans']={sid:transfer.summarize([r for r in groups['supported'] if r['session_id']==sid]) for sid in sessions}
    summary['receivers']={rx:transfer.summarize([r for r in groups['supported'] if r['receiver_id']==rx]) for rx in sorted({r['receiver_id'] for r in rows})}
    summary.update(tracks=len(posterior),excluded=len(excluded),elapsed_seconds=time.monotonic()-started)
    for p in [plan_path,fit_path,HERE/'run.py',HERE/'PROTOCOL.md',transfer_path,shape_path,REPORTS/'2026_09_29_contemporaneous_residual/study.py']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'results.json').open('x') as out:
        json.dump(dict(cases=cases,rows=rows,exclusions=excluded,summary=summary,hashes=hashes),out,indent=2,allow_nan=False)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['scans','receivers']},indent=2))


if __name__=='__main__':
    main()
