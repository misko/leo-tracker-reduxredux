"""Random whole-family validation of a recovered track's position influence.

This tests transfer of the position contribution under frozen identities and
graph selection. Per-family held likelihoods are marginal composite scores,
not a joint evidence over correlated receiver uncertainty.
"""
import argparse
import copy
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import training_factory
from leo.analysis.research.grouped_prediction import family_folds
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached
from predictive_new_family import NewFamily
from prototype_dsx01_continuous_position import latlon


def validation_inputs(d):
    base,_=d['problems']['c0']
    scan=copy.copy(d['scan']);scan.radio_sigma_hz=150.;scan.fixed_window_noise=dict(extra_parameter_BIC_gain=0,per_observation_noise_sigma_hz={})
    # Held scores use exactly the original retained points, not rejected pieces
    # or new observations elsewhere on a partially retained graph track.
    held_scan=copy.copy(scan);held_scan.tracks=list(scan.tracks);held_scan.rx_basis=list(scan.rx_basis)
    for i,sl in zip(base.members,base.slices,strict=True):
        mask=d['keep'][sl];t=scan.tracks[i]
        held_scan.tracks[i]=dict(t,times=t['times'][mask],values=t['values'][mask],
                                observation_ids=[o for o,k in zip(t['observation_ids'],mask,strict=True) if k])
        held_scan.rx_basis[i]=scan.rx_basis[i][mask]
    return scan,held_scan,np.ones(len(d['powers'])),training_factory(d)


def held_entries(base,held_scan,held):
    entries={}
    for row,i,sl,alias in zip(base.rows,base.members,base.slices,base.alias,strict=True):
        if not held[sl].any():continue
        t=held_scan.tracks[i];j=row['candidate_index']
        entries.setdefault(j,[]).append(dict(track_index=i,candidate_index=j,norad=int(base.scan.norads[j]),alias=int(alias),points=len(t['times']),
                                              component=t['key'],observation_ids=t['observation_ids']))
    return entries


def run(args):
    start=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json')
    inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv);base,_=d['problems']['c0']
    labels=np.array(base.labels)[base.flat_labels];splits=family_folds(labels,d['keep'],seed=args.seed)
    scan,held_scan,powers,factory=validation_inputs(d);target=NewFamily(scan,pr['targets'],d['model'])
    write(out/'protocol.json',dict(job=pr['job'],targets=pr['targets'],source_trial=str(args.trial),seed=args.seed,
        folds=[r for _,_,r in splits],fixed_noise_hz=150,weights='unit; training-only learned precision',
        old_predictive_rows_used=False,held_score='marginal per family; composite across families',
        target_conditions_held_receiver=False,frozen_graph_and_identities=True,frozen_aliases=True,position_uncertainty_integrated=False,
        held_phase_step_s=.1,target_phase_step_s=.1,
        GPS_used=False,phase_rounds=5,maxiter=48,maxfun=240,regional_start=[0,0],box_width_km=25,
        criteria='exploratory paired score changes; no new promotion threshold selected'))
    results=[]
    for train,held,receipt in splits:
        entries=held_entries(base,held_scan,held)
        fold=dict(split=receipt,variants={})
        for variant,include in [('control',False),('plus_target',True)]:
            pair={}
            for arm in ('c0','fitted_c'):
                reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
                for _ in range(5):
                    p=make_event_problem(scan,d['node'],train,arm,reference,powers,d['means'],d['model'],[],base_problem_factory=factory);cached(p)
                    def objective(z):
                        c=p.calculate(z);return c['negative_twice_elbo']+float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)+(target.evaluate(p,z,powers,[]) if include else 0.)
                    opt=minimize(objective,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
                        options=dict(maxiter=48,maxfun=240,eps=.001,ftol=1e-10,gtol=1e-4,maxls=20))
                    x=np.array(opt.x);phase=np.clip(p.state(x)['phases'][p.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
                    history.append(dict(x=x,objective=float(opt.fun),success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,phase_change_s=delta))
                scores=[]
                for j,ee in entries.items():
                    predictor=NewFamily(held_scan,ee,d['model'],allow_uncalibrated_label=True)
                    score=predictor.evaluate(p,x,powers,[]);scores.append(dict(norad=int(scan.norads[j]),candidate_index=j,points=sum(e['points'] for e in ee),
                        negative_twice_log_density=score,components=[e['component'] for e in ee],observations=[o for e in ee for o in e['observation_ids']]))
                pair[arm]=dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),held_families=scores,history=history,phase_reference=p.reference,
                               optimizer_success=bool(opt.success),final_phase_change_s=delta)
                print(pr['job']['label'],receipt['fold'],variant,arm,'held families',len(scores),'seconds',round(time.monotonic()-start,1),flush=True)
            fold['variants'][variant]=pair;write(out/f"fold-{receipt['fold']}-{variant}.json",pair)
        results.append(fold);write(out/f"fold-{receipt['fold']}.json",fold)
    write(out/'result.json',dict(job=pr['job'],targets=pr['targets'],folds=results,no_production_change=True,seconds=time.monotonic()-start))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['study','trial','output']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--seed',type=int,default=20261029);run(p.parse_args())
