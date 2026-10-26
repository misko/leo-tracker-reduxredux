"""Cross-receiver and whole-family predictive tests; geography is external."""
import argparse
import copy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import sys
import time
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
from scipy.linalg import solve_triangular
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features

OUT=ROOT/'residual'
MODELS=('baseline','sharedRF50')


def nominate(d):
    p=build(d,'default','c0',np.zeros(len(d['means'])));m=metadata(p);choices=[]
    for j in sorted(set(m['family'][p.keep])):
        selected=p.keep & (m['family']==j)
        if set(m['receiver'][selected])=={1,2}:
            choices.append(dict(family=int(j),norad=int(p.scan.norads[j]),points=int(selected.sum()),
                receiver_points={str(rx):int((selected & (m['receiver']==rx)).sum()) for rx in (1,2)}))
    choices.sort(key=lambda c:(-c['points'],c['norad']))
    return choices


def split(d,family,receiver):
    p=build(d,'default','c0',np.zeros(len(d['means'])));m=metadata(p)
    held=np.asarray(d['keep']) & (m['family']==family)
    if receiver is not None:held &= m['receiver']==receiver
    targets=[copy.deepcopy(e) for e in d['entries'] if e['candidate_index']==family and
             (receiver is None or d['scan'].tracks[e['track_index']]['receiver']==receiver)]
    keys={e['component'] for e in targets}
    train=dict(d,keep=np.asarray(d['keep']) & ~held,
               entries=[copy.deepcopy(e) for e in d['entries'] if e['component'] not in keys])
    assert not (train['keep'] & held).any() and held.any() and train['keep'].any()
    return train,held,targets


def predict(d,train,held_mask,targets,unseen,arm,model,x,path):
    p,c,changes=h.fixed_position_posterior(train,unseen,arm,model,x)
    mean,root,audit=h.held_posterior(p,c,train,unseen)
    m=metadata(p)
    raw=[p.values[held_mask]-p.q[held_mask]*c['intercept'][held_mask]-c['features'][held_mask]@mean]
    design=[c['features'][held_mask]];sigmas=[p.point_noise[held_mask]]
    ids=list(m['ids'][held_mask]);rx=[m['receiver'][held_mask]];ch=[m['channel'][held_mask]]
    times=[m['time'][held_mask]];extra=np.zeros((int(held_mask.sum()),len(targets)))
    if targets:
        view,values,sigma,groups,_=linear_geometry(p,targets);geom=geometry_features(view,x,0.)
        raw.append(values-view.q*geom['intercept']-geom['features']@mean)
        design.append(geom['features']);sigmas.append(sigma);times.append(view.flat_times)
        rr=[];cc=[]
        for e in targets:
            t=p.scan.tracks[e['track_index']]
            assert list(e['observation_ids'])==list(t['observation_ids'])
            ids.extend(t['observation_ids']);rr.extend([t['receiver']]*len(t['times']));cc.extend([t['channel']]*len(t['times']))
        rx.append(np.array(rr));ch.append(np.array(cc));extra=np.vstack((extra,np.eye(len(targets))[groups]*300.))
    assert len(ids)==len(set(ids))
    trainids=set(m['ids'][p.keep])|{oid for e in train['entries'] for oid in e['observation_ids']}
    assert not trainids.intersection(ids)
    raw=np.concatenate(raw);features=np.vstack(design);sigma=np.concatenate(sigmas)*np.sqrt(2)
    rx=np.concatenate(rx);ch=np.concatenate(ch);times=np.concatenate(times)
    u=np.column_stack((solve_triangular(root,features.T,lower=True).T,extra))
    masks={'all':np.ones(len(raw),bool),'RX1':rx==1,'RX2':rx==2,
           'CH1_4':ch<=4,'CH5_8':ch>4,'CH7_8':ch>=7}
    scores={k:h.gaussian_score(raw[a],u[a],sigma[a]) for k,a in masks.items() if a.any()}
    path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,raw=raw,uncertainty=u,sigma=sigma,receiver=rx,channel=ch,time=times,ids=np.asarray(ids))
    return dict(scores=scores,phase_changes=changes,prior_audit=audit,held_points=len(ids),
        curved_points=int(held_mask.sum()),predictive_points=len(ids)-int(held_mask.sum()),
        train_target_ids_disjoint=True,arrays=str(path),arrays_sha256=sha(path),
        scores_are_nonadditive_marginals=True,position_uncertainty_integrated=False)


def freeze():
    cases={}
    for case in CASES:
        d=context(case);choices=nominate(d)
        cases[case]=dict(ranking=choices,selected=choices[0] if choices else None)
    sources=source_manifest();sources[str(Path(__file__))]=sha(__file__)
    write(OUT/'protocol.json',dict(cases=cases,sources=sources,models=MODELS,masks=['whole','RX1','RX2'],
        GPS_used=False,advance='Whole-family all-case own gains positive both arms, sum>=10 each, both predictor movement totals positive each arm; every fit and score converges.'))


def one(job):
    case,maskname=job;started=time.monotonic();cap(300);out=OUT/'results'/f'{case}_{maskname}.json'
    protocol=load(OUT/'protocol.json');result=dict(case=case,mask=maskname,GPS_used=False)
    try:
        verify(protocol['sources']);d=context(case);selected=protocol['cases'][case]['selected']
        if selected is None:
            result.update(status='unavailable',reason='No retained curved family on both receivers')
        else:
            receiver=None if maskname=='whole' else int(maskname[-1]);j=selected['family']
            train,held,targets=split(d,j,receiver);unseen=[j] if receiver is None else []
            result.update(selected=selected,arms={})
            for arm in ARMS:
                fits={model:h.cold_fit(train,unseen,arm,model) for model in MODELS}
                for model,f in fits.items():
                    p=h.build(train,arm,f['reference_used'],model)
                    f['maximum_unclipped_phase_s']=float(np.max(abs(p.state(f['endpoint_east_north_km'])['phases'][p.labels])))
                scores={}
                for model in MODELS:
                    scores[model]={endpoint:predict(d,train,held,targets,unseen,arm,model,
                        fits[endpoint]['endpoint_east_north_km'],OUT/'arrays'/f'{case}_{maskname}_{arm}_{model}_at_{endpoint}.npz') for endpoint in MODELS}
                result['arms'][arm]=dict(fits=fits,crossover=scores)
            verify(protocol['sources']);result['status']='complete'
    except Exception as e:result.update(status='failed',error=repr(e),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-started;write(out,result)
    print(case,maskname,result['status'],round(result['seconds'],2),flush=True)
    return dict(case=case,mask=maskname,status=result['status'],path=str(out),sha256=sha(out))


def run():
    with ProcessPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(one,[(c,m) for c in CASES for m in ('whole','RX1','RX2')]))
    write(OUT/'execution.json',dict(results=results,GPS_used=False))
    files={str(p):sha(p) for p in OUT.rglob('*') if p.is_file() and p.suffix in ('.json','.npz','.py')}
    write(OUT/'RF_seal.json',dict(files=files,GPS_used=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
