import hashlib
import json
import time
from pathlib import Path

from scores import predictive,scale_model

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_30_ds10_scale_weighting'


def read(path):return json.loads(path.read_text())


def main():
    started=time.monotonic();plan=read(BASE/'plan.json')
    for name,digest in plan['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    helper=scale_model.helper
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=plan['inputs']))
    model=helper.TrendMixturePosition(docs,plan['config'],helper.baseline.Stationary,.2)
    x=plan['baseline']['x']
    ratios={arm:{(w['session_id'],w['track_id']):w[arm] for w in plan['weights']} for arm in ['constant','variable']}
    reference={}
    for arm in ['baseline','constant','variable']:
        m=model if arm=='baseline' else scale_model.Scaled(docs,plan['config'],ratios[arm])
        scored=m.evaluate(x,gradient=False,held=True)
        reference[arm]={(r['session_id'],r['track_id']):r for r in scored['rows']}
    rows=[];max_audit=0.
    for i,(doc,engine) in enumerate(zip(docs,model.models,strict=True)):
        for track in doc['tracks']:
            key=(doc['session_id'],track['track_id'])
            pred,visible=engine.prediction(track,[*x[:2],x[i+2]])
            arms={}
            for arm in ['baseline','constant','variable']:
                ratio=1. if arm=='baseline' else ratios[arm].get(key,1.)
                result=predictive(track['y'],track['times_s'],track['mask'],pred,visible,100.*ratio)
                ref=reference[arm][key]
                audit=max(abs(result['training']-ref['training_log_score']),abs(result['joint']-ref['held_log_score']))
                assert audit<1e-7
                max_audit=max(max_audit,audit)
                arms[arm]=result
            rows.append(dict(session_id=key[0],track_id=key[1],supported=key in ratios['variable'],
                             held_observations=int((~track['mask']).sum()),arms=arms))
    summary={}
    for arm in ['constant','variable']:
        scan_rows=[]
        for sid in plan['sessions']:
            subset=[r for r in rows if r['session_id']==sid]
            scan_rows.append(dict(session_id=sid,**{score:sum(r['arms'][arm][score]-r['arms']['baseline'][score] for r in subset) for score in ['joint','marginal_sum']}))
        summary[arm]=dict(joint_gain=sum(r['joint'] for r in scan_rows),marginal_sum_gain=sum(r['marginal_sum'] for r in scan_rows),
                          joint_scans_improved=sum(r['joint']>0 for r in scan_rows),marginal_scans_improved=sum(r['marginal_sum']>0 for r in scan_rows),scans=scan_rows)
    paths=[BASE/'plan.json',HERE/'run.py',HERE/'scores.py',HERE/'test_scores.py',HERE/'PROTOCOL.md']
    result=dict(rows=rows,summary=summary,max_score_audit=max_audit,elapsed_seconds=time.monotonic()-started,
                hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'results.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:{n:v for n,v in s.items() if n!='scans'} for k,s in summary.items()},indent=2))
    print('audit',max_audit,'seconds',result['elapsed_seconds'])


if __name__=='__main__':main()
