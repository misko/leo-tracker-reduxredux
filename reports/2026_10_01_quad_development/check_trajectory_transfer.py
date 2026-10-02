"""Bounded complete-block predictive transfer, with alternating and forward folds."""
import fcntl
import json
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from common import independent_tracks
from trajectory_mixture import fit,predict,design
from trajectory_robust_control import robust_fit,density
from screen_seed_prefix import sealed,digest
from regression_batch import execute,verify_sources
from failure_composition_checks import process_ok
from check_receiver_curvature import save
HERE=Path(__file__).resolve().parent


def worker(unit,directory):
    selection=sealed(HERE/'selection.json');capture=next(r for r in selection['captures'] if r['unit_id']==unit)
    assert capture['block_id'] in ('DS9-B02','DS10-B02','DS11-B02')
    pilot=sealed(HERE/'trajectory-mixture-v1.json');verify_sources(pilot['sources'])
    control=sealed(HERE/'trajectory-robust-control-v1.json');verify_sources(control['sources'])
    root=HERE/'prepared'/unit
    paths=[HERE/'selection.json',root/'observations.json',root/'evidence.json',root/'orbits.json']
    obs,evidence,orbits=[json.loads(p.read_text()) for p in paths[1:]]
    assert obs['session_id']==evidence['session_id']==capture['session_id']
    assert obs['manifest_sha256']==capture['manifest_sha256']
    assert digest(root/'observations.json')==evidence['source']['sha256']==orbits['observation_sha256']
    retained,excluded=independent_tracks(evidence);lookup={r['track_id']:r for r in obs['tracks']};records=[]
    for track in retained:
        raw=lookup[track['track_id']];t=np.array(raw['times_s']);y=np.array(raw['measured_hz']);n=len(t)
        np.testing.assert_array_equal(y,track['measured_hz'])
        masks=[('alternating',p,np.arange(n)%2==p) for p in (0,1)]+[('forward',0,np.arange(n)<n//2)]
        folds=[]
        for sigma in (100.,300.):
            for split,fold,train in masks:
                held=~train;model=fit(t[train],y[train],sigma);base=predict(model,t[held],y[held],single=True);mix=predict(model,t[held],y[held])
                delta=2*(model['mixture_loglik']-model['single_loglik'])
                chosen=model['status']=='mixture' and delta>4*np.log(train.sum());strict=model['status']=='mixture' and delta>8*np.log(train.sum())
                robust=robust_fit(t[train],y[train],sigma)
                rll=float(density(y[held]-robust['offset']-design(t[held],robust['center'],robust['scale'])@np.array(robust['beta']),sigma).sum()) if robust['converged'] else None
                b=float(base.sum());gain=float((mix-base).sum())
                folds.append(dict(split=split,fold=fold,sigma_hz=sigma,training_points=int(train.sum()),held_points=int(held.sum()),
                    mixture_status=model['status'],mixture_selected=bool(chosen),double_penalty_selected=bool(strict),
                    model=model,robust=robust,baseline_score=b,raw_gain=gain,selected_gain=gain if chosen else 0.,
                    double_penalty_gain=gain if strict else 0.,robust_score=rll,policy_vs_robust=b+(gain if chosen else 0.)-rll if rll is not None else None))
        records.append(dict(track_id=track['track_id'],points=n,folds=folds))
    inputs={str(p):digest(p) for p in paths}
    sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    sources[str(HERE/'TRAJECTORY_TRANSFER_PLAN.md')]=digest(HERE/'TRAJECTORY_TRANSFER_PLAN.md')
    verify_sources(sources);verify_sources(inputs)
    save(directory/'sources.json',dict(source_sha256=sources,inputs=inputs))
    save(directory/'result.json',dict(unit=unit,block=capture['block_id'],tracks=records,excluded_tracks=len(excluded),
        qualification='Development block transfer of radio surrogate; forward split is conditional on full-capture upstream track construction. No localization or GPS.'))
    print(unit,len(records),flush=True)


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    selection=sealed(HERE/'selection.json')
    units=[r['unit_id'] for r in selection['captures'] if r['block_id'] in ('DS9-B02','DS10-B02','DS11-B02')];assert len(units)==12
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=HERE/'trajectory-transfer-v1';root.mkdir(exist_ok=False)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in units:
            directory=root/unit;directory.mkdir()
            launch=execute([sys.executable,str(Path(__file__).resolve()),unit,str(directory)],directory,unit,timeout_s=90,env=env)
            save(directory/'launch.json',launch);print(unit,launch['returncode'],launch['elapsed_seconds'],flush=True)
            assert process_ok(launch)


if __name__=='__main__':main()
