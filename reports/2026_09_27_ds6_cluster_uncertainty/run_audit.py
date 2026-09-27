"""Local model-curvature versus cluster-score covariance, without truth fitting."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_track_influence'))
from run_influence import derivatives,load_model,Objective
from run_baseline import site,REFERENCE_RF_HZ,LIGHT_KM_S,robust_scores


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def covariance(gradients,information,labels):
    """Track-score sandwich with finite-cluster correction and timing nuisance."""
    groups=sorted(set(labels));count=len(groups)
    if np.min(np.linalg.eigvalsh(information))<=1e-6 or np.linalg.cond(information)>1e10:
        return dict(state='unavailable',reason='Non-positive or ill-conditioned observed information',groups=count)
    inv=np.linalg.inv(information)
    if count<=3:return dict(state='unavailable',reason='Too few clusters for three fitted parameters',groups=count,model_covariance=inv.tolist())
    sums=np.array([np.sum(gradients[np.array([label==group for label in labels])],axis=0) for group in groups])
    sums-=sums.mean(axis=0)
    meat=sums.T@sums*count/(count-1)
    cov=inv@meat@inv.T;cov=(cov+cov.T)/2
    return dict(state='complete',groups=count,model_covariance=inv.tolist(),cluster_covariance=cov.tolist())


def map_candidate(model,x):
    t=model.tracks[0];p,v,ids=model.banks[t['track_id']]
    q=(x[2]+5)*4;lo=min(39,max(0,int(np.floor(q))));weight=q-lo
    pos=p[:,lo]*(1-weight)+p[:,lo+1]*weight;vel=v[:,lo]*(1-weight)+v[:,lo+1]*weight
    rec,up=site(*model.coordinates(x));unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
    pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
    score=robust_scores(t['y'][None,:]-pred,t['mask'])[0]
    score=np.where(np.any((unit@up)[:,t['mask']]>=0,axis=-1),score,-np.inf)
    index=int(np.argmax(score));weights=np.exp(score-np.max(score));weights/=weights.sum()
    return int(ids[index]),float(weights[index])


def freeze():
    oldpath=REPORTS/'2026_09_27_ds6_fresh_joint43/protocol.json';old=json.loads(oldpath.read_text())
    paths=[oldpath,REPORTS/'2026_09_27_ds6_fresh_joint43/run_joint43.py',REPORTS/'2026_09_27_ds6_track_influence/run_influence.py']+[REPORTS/name for name in old['files']]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in paths},
        sessions=old['splits']['all'],center=old['center'],steps=[.05,.05,.01],
        estimator='Fixed corrected baseline winners; inverse observed information and score-sandwich covariance; no position refit',
        grouping='Individual tracks, then training-MAP catalogue-row groups shared across RX/channel; identities are inferred, not known',
        qualification='Require positive well-conditioned information and >3 clusters; report unavailable explicitly',
        scope='Local conditional uncertainty diagnostic; no calibrated confidence claim, no proof of an irreducible accuracy floor; no truth loaded')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(limit):
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    done=0
    for session in protocol['sessions']:
        output=HERE/f'{session}.json'
        if output.exists():
            assert json.loads(output.read_text())['protocol_sha256']==digest(HERE/'protocol.json');continue
        if done>=limit:break
        full,x,_=load_model(session,protocol['center'])
        models=[Objective([t],{t['track_id']:full.banks[t['track_id']]},full.center,full.catalogue_size,full.receivers) for t in full.tracks]
        def losses(point):return np.array([-m.evaluate(point,False)['train'] for m in models])
        _,g,h=derivatives(losses,x,np.array(protocol['steps']));info=h.sum(axis=0)
        _,g2,h2=derivatives(losses,x,np.array(protocol['steps'])/2)
        assignments=[map_candidate(m,x) for m in models]
        track_labels=[t['track_id'] for t in full.tracks];object_labels=[a[0] for a in assignments]
        arms={};half={}
        for name,labels in [('track',track_labels),('candidate',object_labels)]:
            arms[name]=covariance(g,info,labels);half[name]=covariance(g2,h2.sum(axis=0),labels)
        result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),x=x.tolist(),
            information=info.tolist(),information_eigenvalues=np.linalg.eigvalsh(info).tolist(),total_gradient=g.sum(axis=0).tolist(),
            tracks=[dict(track_id=t['track_id'],receiver_id=t['receiver_id'],candidate_row=a[0],training_map_mass=a[1],gradient=gradient.tolist())
                for t,a,gradient in zip(full.tracks,assignments,g,strict=True)],arms=arms,half_steps=half)
        with output.open('x') as f:json.dump(result,f,indent=2)
        print(json.dumps(dict(session=session,tracks=len(models),candidate_groups=len(set(object_labels)),states={k:v['state'] for k,v in arms.items()})),flush=True)
        done+=1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--limit',type=int,default=12);args=parser.parse_args()
    if args.freeze:freeze()
    else:
        assert 1<=args.limit<=12
        run(args.limit)
