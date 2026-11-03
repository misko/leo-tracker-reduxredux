import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(p):
    return json.loads(p.read_text())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj


def main(ds):
    started=time.monotonic()
    for name,h in read(HERE/'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    helper=module('receiver',REPORTS/'2026_09_29_receiver_holdout/run.py')
    diag=module('scan_diag',REPORTS/'2026_09_29_scan_disagreement/study.py')
    manifest=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    pool=next(s for s in manifest['sets'] if s['dataset']==ds and s['count']==24)
    docs=helper.baseline.load_documents(dict(config=manifest['config'],inputs=[s['input'] for s in pool['scans']]))
    by_id={d['session_id']:d for d in docs}
    def model(items):
        return helper.TrendMixturePosition(items,manifest['config'],helper.baseline.Stationary,.2)
    results=[]
    for donor,target in [('early','middle'),('early','late'),('middle','late')]:
        prior=read(REPORTS/f'2026_09_29_joint16_association_control/{ds}_{donor}_{target}.json')
        assert prior['selected']['qualified']
        x=np.array(prior['selected']['x'])
        scans,tracks=[],[]
        for i,sid in enumerate(prior['sessions']):
            doc=by_id[sid];local=np.array([*x[:2],x[i+2]])
            one=model([doc]);out=one.evaluate(local)
            h,asym=diag.curvature(one,local,1.)
            ha,aa=diag.curvature(one,local,.5)
            discrepancy=float(np.linalg.norm(h-ha)/max(np.linalg.norm(h),1e-12))
            profiled=diag.profile(h,out['gradient'])
            qualified=profiled is not None and max(asym,aa,discrepancy)<.01
            record=dict(session_id=sid,qualified=bool(qualified),discrepancy=discrepancy,asymmetry=max(asym,aa),score=out['score'],hessian=h.tolist(),profiled_hessian=None if profiled is None else profiled[0].tolist())
            localtracks=[]
            for track in doc['tracks']:
                single=model([dict(doc,tracks=[track])]).evaluate(local)
                g=single['gradient']
                pg=None if profiled is None else g[:2]-h[:2,2]/h[2,2]*g[2]
                localtracks.append(dict(session_id=sid,track_id=track['track_id'],receiver=int(track['receiver_id']),window=donor if i<8 else target,score=single['score'],gradient=g.tolist(),profiled_gradient=None if pg is None else pg.tolist()))
            record['score_replay']=abs(sum(t['score'] for t in localtracks)-out['score'])
            record['gradient_replay']=float(np.max(np.abs(sum(np.array(t['gradient']) for t in localtracks)-out['gradient'])))
            assert max(record['score_replay'],record['gradient_replay'])<1e-7
            tracks.extend(localtracks);scans.append(record)
        replay=abs(sum(s['score'] for s in scans)-prior['selected']['score'])
        assert replay<1e-7
        result=dict(dataset=ds,donor=donor,target=target,scans=scans,tracks=tracks,score_replay=replay,estimate_deg=prior['selected']['estimate_deg'],qualified=False)
        if all(s['qualified'] for s in scans):
            h=sum(np.array(s['profiled_hessian']) for s in scans)
            if np.linalg.eigvalsh(h).min()>0:
                for t in tracks:
                    delta=-np.linalg.solve(h,np.array(t['profiled_gradient']))
                    t['downweight_response_km']=delta.tolist()
                    t['response_norm_m']=float(np.linalg.norm(delta)*1000)
                ranked=sorted(tracks,key=lambda t:(-t['response_norm_m'],t['session_id'],t['track_id']))
                top=ranked[:10]
                groups=[]
                for window in (donor,target):
                    for receiver in (0,1):
                        group=[t for t in tracks if t['window']==window and t['receiver']==receiver]
                        delta=sum(np.array(t['downweight_response_km']) for t in group)
                        groups.append(dict(window=window,receiver=receiver,tracks=len(group),response_km=delta.tolist(),response_norm_m=float(np.linalg.norm(delta)*1000)))
                result.update(qualified=True,profiled_hessian=h.tolist(),max_track_response_m=ranked[0]['response_norm_m'],top10_norm_share=sum(t['response_norm_m'] for t in top)/sum(t['response_norm_m'] for t in tracks),top10_vector_response_m=float(np.linalg.norm(sum(np.array(t['downweight_response_km']) for t in top))*1000),top10_ids=[dict(session_id=t['session_id'],track_id=t['track_id']) for t in top],groups=groups)
        with (HERE/f'{ds}_{donor}_{target}.json').open('x') as out:
            json.dump(result,out,indent=2,allow_nan=False)
        results.append(dict(donor=donor,target=target,qualified=result['qualified']))
    with (HERE/f'{ds}.json').open('x') as out:
        json.dump(dict(pairs=results,elapsed_seconds=time.monotonic()-started),out,indent=2)
    print(ds,time.monotonic()-started,flush=True)


if __name__=='__main__':
    main(sys.argv[1])
