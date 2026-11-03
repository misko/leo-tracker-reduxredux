"""Conditional final-stage predictive checks, not end-to-end held-out validation.

Search region, satellite bank and frozen calibration came from the full capture.
Only final position/clock/RF parameters are refit with each block excluded.
No reference position is read. Both c arms share the same region and bank.
"""
import concurrent.futures as futures
from dataclasses import replace
import multiprocessing
import time
import numpy as np
import run_variants as run
from rf_model import RFObjective,fit_rf


def subset(obs,mask):
    indices=np.flatnonzero(mask)
    return replace(obs,window_ids=tuple(obs.window_ids[i] for i in indices),
                   **{k:getattr(obs,k)[mask] for k in ('times_s','measured_hz','rf_hz','receiver','channel','margin')})


def make_objective(factory,obs,bank,prior,score,baseline,template,mask,enabled):
    base=factory(subset(obs,mask),bank,prior,score,receiver_baseline_hz=np.asarray(baseline)[mask])
    # Keep physical clock/RF origins fixed across training and held-out rows.
    base.design=template.base.design[mask].copy()
    q=template.group_basis if enabled else np.zeros((len(template.groups),0))
    return RFObjective(base,gauge=(template.groups,q,template.incidence[mask]))


def task(job):
    label,kind,block=job
    path=run.HERE/'holdout'/f'{label}_{kind}_{block}.json'
    if path.exists():return run.read(path)
    started=time.monotonic()
    _,obs,bank,prior,score=run.engine.context(label,'rf_offsets')
    saved=run.read(run.control_folder(label)/'result.json')['selections']['fitted-c']['result']
    xy=saved['point'];radius=saved['local_radius_km']
    region=run.read(run.control_folder(label)/'regions'/f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json')
    bank=bank.select(region['association']['selected_indices'])
    baseline=np.asarray(region['calibration']['receiver_baseline_hz'])
    fullbase=run.engine.NativeObjective(obs,bank,prior,score,receiver_baseline_hz=baseline)
    template=RFObjective(fullbase)
    if kind=='time':
        mid=(obs.times_s.min()+obs.times_s.max())/2
        held=(obs.times_s<mid) if block==0 else (obs.times_s>=mid)
    else:
        channels=np.rint(obs.rf_hz/1e6).astype(int)
        held=channels==np.unique(channels)[block]
    rows=[]
    for enabled in (False,True):
        train=make_objective(run.engine.NativeObjective,obs,bank,prior,score,baseline,template,~held,enabled)
        test=make_objective(run.engine.PositionObjective,obs,bank,prior,score,baseline,template,held,enabled)
        for arm in ('zero-c','fitted-c'):
            fits=[]
            for seed in ('association','zero-timing','own-continuation'):
                if seed=='own-continuation':
                    start=min(fits,key=lambda r:r.objective).vector
                else:
                    start=np.asarray(region['association']['initial_vector']).copy()
                    if seed=='zero-timing':start[7:]=0.
                fit=fit_rf(train,start,rf_arm=arm,local_center=xy,local_radius_km=radius)
                fits.append(fit)
            accepted=[f for f in fits if f.converged]
            chosen=min(accepted or fits,key=lambda r:r.objective)
            value,gradient,terms=test.evaluate(chosen.vector)
            fasttest=make_objective(run.engine.NativeObjective,obs,bank,prior,score,baseline,template,held,enabled)
            fv,fg,_=fasttest.evaluate(chosen.vector)
            np.testing.assert_allclose(value,fv,atol=1e-6,rtol=0)
            np.testing.assert_allclose(gradient,fg,atol=1e-6,rtol=1e-7)
            rows.append(dict(arm=arm,rf_enabled=enabled,accepted=bool(accepted),
                vector=chosen.vector,train_objective=chosen.objective,heldout_data_nll=terms.nll,
                heldout_windows=int(held.sum()),training_windows=int((~held).sum()),
                train_rf_penalty=train.penalty(chosen.vector),rf_offsets_hz=train.offsets(chosen.vector),
                stationarity=chosen.stationarity,stops=[f.stop_reason for f in fits],
                fit_seconds=sum(f.elapsed_s for f in fits)))
    result=dict(label=label,kind=kind,block=block,point=xy,radius=radius,rows=rows,elapsed_s=time.monotonic()-started)
    run.engine.write(path,result)
    print('HOLDOUT',label,kind,block,[r['accepted'] for r in rows],flush=True)
    return result


def main():
    (run.HERE/'holdout').mkdir(exist_ok=True)
    sources={str(p):run.data.digest(p) for p in (run.HERE/'run_variants.py',run.HERE/'rf_model.py',run.HERE/'holdout.py')}
    protocol=dict(labels=run.WATCH,folds='Two contiguous time halves and each rounded-MHz RF group.',
        scope=__doc__,sources=sources,selection='Training objective only; require strict convergence for paired reporting.',
        starts=['association','zero-timing','own-continuation'],seconds_per_fit=20,iterations_per_fit=600)
    path=run.HERE/'protocol_holdout.json'
    if path.exists():assert run.read(path)==protocol
    else:run.engine.write(path,protocol)
    jobs=[]
    for label in run.WATCH:
        run.engine.CONTEXT[label]=run.data.load(label)
        obs=run.engine.CONTEXT[label][1]
        jobs += [(label,'time',i) for i in range(2)]
        jobs += [(label,'rf',i) for i in range(len(np.unique(np.rint(obs.rf_hz/1e6))))]
    begun=time.monotonic()
    with futures.ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
        pending=[pool.submit(task,j) for j in jobs]
        results=[]
        for future in futures.as_completed(pending):
            results.append(future.result())
            run.engine.write(run.HERE/'progress_holdout.json',dict(completed=len(results),requested=len(jobs),elapsed_s=time.monotonic()-begun))
    run.engine.write(run.HERE/'holdout_results.json',dict(protocol=protocol,results=results,elapsed_s=time.monotonic()-begun))


if __name__=='__main__':main()
