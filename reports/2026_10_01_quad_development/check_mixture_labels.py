"""Bounded single-track coupled-label moves at frozen mixture states."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from mixture_localization import MixtureObjective
from mixture_window_groups import group_keys
from mixture_label_delta import move_gain
from screen_seed_prefix import sealed,digest
from regression_batch import execute,verify_sources
from failure_composition_checks import process_ok

HERE=Path(__file__).resolve().parent
UNITS=tuple(f'{ds}-B01-{size}' for size in ('S1','D1','Q') for ds in ('DS9','DS10','DS11'))


def worker(unit,directory):
    started=time.monotonic();inputs={}
    def read(path):
        value=sealed(path);inputs[str(path)]=digest(path);return value
    single=unit.endswith('S1')
    fit_dir=HERE/'mixture-localization-pilot-v1'/unit/'mixture' if single else HERE/'mixture-window-pilot-v1'/unit
    fitted=read(fit_dir/('result.json' if single else 'mixture.json'));assert fitted['audit']['accepted']
    assert process_ok(read(fit_dir/'launch.json'))
    frozen=read(fit_dir/'sources.json');sources=dict(frozen['source_sha256']);inputs.update(frozen['inputs'])
    campaign='one-start-blas-cold-v1' if single else 'one-start-blas-window-cold-v1'
    parent=read(HERE/campaign/unit/'blas'/(unit+'.json'))
    verify_sources(sources);verify_sources(inputs)
    binding,scans,columns,precision,ports=prepare_window(unit)
    assert binding==parent['binding']==fitted['binding'] and parent['observations']==[list(p.observation_ids) for p in ports]
    state=np.asarray(fitted['fit']['mean']);labels=parent['best']['associations']
    catalogues=[s[0].bank.norad_ids for s in scans];counts=[len(s[2]) for s in scans]
    keys=group_keys(binding['scans'],catalogues,counts,labels)
    track_scans=[(scan_id,cat) for scan_id,cat,n in zip(binding['scans'],catalogues,counts) for _ in range(n)]
    groups={};base_scores=[];all_scores=[]
    def stat(port,index):
        pred=port.predict_selected(state,index)
        if not pred.eligible:raise ValueError('ineligible')
        L=np.linalg.cholesky(pred.covariance);y=np.linalg.solve(L,port.observation-pred.mean)
        return dict(d=len(y),q=float(y@y),logdet=float(2*np.log(np.diag(L)).sum()))
    for j,(p,i,key) in enumerate(zip(ports,labels,keys)):
        base_scores.append(p.score_selected(state,i));all_scores.append(p.score_all(state))
        if key is not None:groups.setdefault(key,{})[j]=stat(p,i)
    model=MixtureObjective(ports,labels,keys,precision,state);baseline=model.evaluate(state,False)[0]
    assert abs(baseline-fitted['fit']['objectives'][-1])<1e-6
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('MIXTURE_LABEL_PLAN.md','test_mixture_label_delta.py'):sources[str(HERE/name)]=digest(HERE/name)
    verify_sources(sources);verify_sources(inputs);save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    rows=[];invalid=[];proposal_counts=[]
    for j,(p,old,key,scores,(scan_id,cat)) in enumerate(zip(ports,labels,keys,all_scores,track_scans)):
        candidates=sorted([i for i in range(p.candidate_count) if i!=old and np.isfinite(scores[i])],key=lambda i:(-scores[i],i))[:2]
        if old!=p.candidate_count and np.isfinite(scores[p.candidate_count]):candidates.append(p.candidate_count)
        proposal_counts.append(len(candidates))
        for candidate in candidates:
            new_key=(scan_id,int(cat[candidate])) if candidate<p.candidate_count else None
            try:
                new_stat=stat(p,candidate) if new_key is not None else None
                physical=p.score_selected(state,candidate);assert np.isfinite(physical)
                np.testing.assert_allclose(physical,scores[candidate],rtol=1e-9,atol=1e-8)
            except (ValueError,np.linalg.LinAlgError) as error:
                invalid.append(dict(track=j,candidate=candidate,reason=str(error)));continue
            gain=move_gain(groups,key,new_key,j,new_stat,physical-base_scores[j])
            rows.append(dict(track=j,old_index=old,new_index=candidate,old_group=key,new_group=new_key,
                physical_gain=float(physical-base_scores[j]),mixture_gain=gain))
    checked=[]
    for row in ([rows[0],max(rows,key=lambda r:r['mixture_gain'])] if rows else []):
        alternative=list(labels);alternative[row['track']]=row['new_index']
        new_keys=group_keys(binding['scans'],catalogues,counts,alternative)
        alternative_model=MixtureObjective(ports,alternative,new_keys,precision,state)
        gain=baseline-alternative_model.evaluate(state,False)[0]
        error=abs(gain-row['mixture_gain']);assert error<1e-6;checked.append(error)
    best=[max((r for r in rows if r['track']==j),key=lambda r:r['mixture_gain'],default=None) for j in range(len(ports))]
    result=dict(unit=unit,size=binding['size'],track_count=len(ports),proposed=sum(proposal_counts),evaluated=len(rows),invalid=invalid,
        moves=rows,best_by_track=best,improving_moves=sum(r['mixture_gain']>1e-6 for r in rows),
        improving_tracks=sum(r is not None and r['mixture_gain']>1e-6 for r in best),
        maximum_gain=max((r['mixture_gain'] for r in rows),default=None),full_reconstruction_errors=checked,
        elapsed_seconds=time.monotonic()-started,
        qualification='Bounded two-alternative-signals plus background, fixed continuous state and epoch values; not global/local-all-label optimality or geographic improvement.')
    verify_sources(sources);verify_sources(inputs);save(directory/'result.json',result)
    print(unit,result['evaluated'],result['improving_moves'],result['maximum_gain'],flush=True)


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=HERE/'mixture-label-check-v1';root.mkdir(exist_ok=False)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory=root/unit;directory.mkdir();size=1 if unit.endswith('S1') else 4 if unit.endswith('-Q') else 2
            launch=execute([sys.executable,str(Path(__file__).resolve()),unit,str(directory)],directory,unit,timeout_s=90*size,env=env)
            save(directory/'launch.json',launch);print(unit,launch['returncode'],flush=True)


if __name__=='__main__':main()
