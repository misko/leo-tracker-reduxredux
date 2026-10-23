"""Frozen native-stage interventions; evaluation GPS is absent from inference."""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import signal
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import experiment as exp
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary
from probe_algo03_feasible_recovery import gate_slacks
from run_algo01_ds23_sample import read, write, sha

OUT=Path(__file__).resolve().parents[1]
FROZEN=Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023')
ARMS=('c0','fitted_c')


def load(case):
    record=read(FROZEN/'raw'/case/'result.json')
    d,_=exp.context(case)
    parent=exp.apply_trial(d,record['ordinary_graph'])
    fragments=read(FROZEN/'raw'/case/'native'/(case+'_persistent5s_selection.json'))['selected']
    return parent,record['ordinary_graph']['kind'],fragments,record


def append(parent,fragments):
    if not fragments:return parent
    scan,entries=exp.paths.native.append_native_paths(parent['scan'],parent['entries'],fragments,exp.paths.native.receiver_basis(parent['scan']))
    return dict(parent,scan=scan,entries=entries)


def selected_fragments(fragments,mode,family=None):
    if mode=='only':return [f for f in fragments if f['norad']==family]
    if mode=='without':return [f for f in fragments if f['norad']!=family]
    if mode=='parent':return []
    if mode=='all':return list(fragments)
    raise ValueError(mode)


def tempered_objective(parent,full,alpha):
    if not 0<=alpha<=1:raise ValueError('weight outside [0,1]')
    return parent+alpha*(full-parent)


def build(parent,changed,kind,arm,reference,alpha):
    p=exp.paths.build(changed,kind,arm,reference)
    if alpha==1:return p
    base=exp.paths.build(parent,kind,arm,reference)
    full=p.calculate
    def calculate(x):
        c=dict(full(x));b=base.calculate(x)
        c['untempered_full_objective']=c['negative_twice_elbo']
        c['negative_twice_elbo']=tempered_objective(b['negative_twice_elbo'],c['negative_twice_elbo'],alpha)
        return c
    p.calculate=calculate
    return p


def id_audit(p,entries):
    curved=[oid for i,sl in zip(p.members,p.slices,strict=True)
            for oid,use in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if use]
    predictive=[oid for e in entries for oid in p.scan.tracks[e['track_index']]['observation_ids']]
    assert len(curved)==len(set(curved)), 'duplicate curved ID'
    assert len(predictive)==len(set(predictive)), 'duplicate predictive ID'
    assert not set(curved)&set(predictive),'curved/predictive physical-ID overlap'
    return dict(curved_points=len(curved),predictive_points=len(predictive),intersection=0,
                curved_ID_sha256=hashlib.sha256(json.dumps(sorted(curved)).encode()).hexdigest(),
                predictive_ID_sha256=hashlib.sha256(json.dumps(sorted(predictive)).encode()).hexdigest())


def refit(parent,changed,kind,arm,alpha):
    x=np.zeros(2);reference=np.zeros(len(parent['means']));history=[]
    for _ in range(5):
        p=build(parent,changed,kind,arm,reference,alpha)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    s=summary(p,x,changed['entries'])
    s.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
             gate_slacks=gate_slacks(p,x,changed['entries']),id_audit=id_audit(p,changed['entries']))
    full=exp.paths.build(changed,kind,arm,s['phase_reference'])
    s['untempered_same_mask_objective']=full.calculate(x)['negative_twice_elbo']
    return s


def execute(job):
    name=job['name'];dest=OUT/'raw'/name;dest.mkdir(parents=True,exist_ok=True)
    if (dest/'result.json').exists():return read(dest/'result.json')['status']
    started=time.monotonic()
    with (dest/'run.log').open('w') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        result=dict(job=job,status='failed')
        try:
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s bounded job')));signal.alarm(240)
            parent,kind,fragments,record=load(job['case'])
            selected=selected_fragments(fragments,job['mode'],job.get('family'))
            changed=append(parent,selected)
            result['added_paths']=[dict(key=f['key'],norad=f['norad'],points=len(f['times']),receiver=f['receiver'],channel=f['channel']) for f in selected]
            result['arms']={a:refit(parent,changed,kind,a,job['alpha']) for a in ARMS}
            result['paired_gates_pass']=exp.qualifies(result['arms'])
            # Coverage is descriptive; no experimental endpoint is adopted.
            result['coverage']=exp.coverage(changed,kind,result['arms'])
            result['parent_IDs_preserved']=exp.preserve(record['ordinary_graph']['coverage'],result['coverage'])
            result['status']='complete'
            if job['mode']=='all' and job['alpha']==1:
                old=read(FROZEN/'raw'/job['case']/'native'/(job['case']+'.json'))['methods']['persistent5s']['arms']
                result['ordinary_replay_max_delta']={a:float(np.max(abs(np.asarray(result['arms'][a]['endpoint_east_north_km'])-old[a]['endpoint_east_north_km']))) for a in ARMS}
                assert max(result['ordinary_replay_max_delta'].values())<1e-7
        except Exception as exc:
            result.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
        finally:
            signal.alarm(0);result['seconds']=time.monotonic()-started
            write(dest/'result.json',result)
    return dict(name=name,status=result['status'],seconds=result['seconds'])


def plan():
    case='DS23-0259'
    selection=FROZEN/'raw'/case/'native'/(case+'_persistent5s_selection.json')
    fragments=read(selection)['selected'];families=sorted({f['norad'] for f in fragments})
    jobs=[dict(name=case+'_all',case=case,mode='all',alpha=1.)]
    jobs.extend(dict(name=f'{case}_{mode}_{family}',case=case,mode=mode,family=family,alpha=1.) for family in families for mode in ('only','without'))
    jobs.extend(dict(name=f'{case}_dose_{alpha}',case=case,mode='all',alpha=alpha) for alpha in (.25,.5,.75))
    protocol=dict(jobs=jobs,source_sha256=sha(Path(__file__)),input_hashes={str(p):sha(p) for p in [selection,FROZEN/'raw'/case/'result.json']},
        c_arms=ARMS,common_starts=[0,0],phase_rounds=5,iterations_per_round=48,job_cap_s=240,
        weighting='graph-parent objective + alpha * (joint full objective - graph-parent objective); diagnostic conditional-evidence tempering',
        same_curved_data_priors_aliases_catalogue_gates=True,linear_points_do_not_learn_calibration=True,
        hypotheses='single added family vs collective interaction; position gradients and mean/covariance decomposition',
        no_production_adoption=True,no_GPS_inference=True,no_future_TLE_no_new_RF=True,
        interpretation='ablation changes observation subset; compare endpoint scores only on common evidence; no GPS-selected pruning')
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/'protocol.json'
    if path.exists():assert read(path)==json.loads(json.dumps(protocol)), 'frozen protocol changed'
    else:write(path,protocol)
    return jobs


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();jobs=plan()
    if not args.freeze_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for f in as_completed([pool.submit(execute,j) for j in jobs]):print(f.result(),flush=True)
