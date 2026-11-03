"""Bounded matched scoring of all 20 audited DS26/DS27 residual sources."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import traceback
import numpy as np
from sgp4.api import Satrec
from evidence import components,marginal,age_penalty
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from prototype_dsx01_continuous_position import latlon

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'2026_10_31_find_glrt_association'
ALIASES=np.arange(-4,5)
POLICIES=('48_fixed','72_fixed','72_age_scaled','72_age_scaled_recency24')


def read(p):return json.loads(Path(p).read_text())


def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,allow_nan=False,default=lambda v:v.tolist())+'\n')


def split(times,seed):
    groups=np.floor(times/12).astype(int);unique=np.unique(groups);rng=np.random.default_rng(seed)
    chosen=rng.choice(unique,max(1,round(len(unique)/3)),replace=False)
    held=np.isin(groups,chosen);train=~held
    for g in chosen:train&=(times<g*12-2)|(times>=(g+1)*12+2)
    return train,held,chosen


def parameters(policy,age):
    return (5. if policy.endswith('fixed') else 5.*max(1.,age/24.),
            age_penalty(age) if policy.endswith('recency24') else 0.)


def run_case(case,step=.1):
    receipt=read(SOURCE/'cases'/case/'receipt.json');meta=receipt['scan_receipt']
    expanded=read(SOURCE/'cases'/case/'expanded_search.json')
    records=read(SOURCE/'causal72.json')['scans'][case]['elements']
    # The prior investigation screened the complete causal catalogue. Preserve
    # its union across c arms, models, and phase bounds; do not whitelist winners.
    finalists=sorted({n for z in expanded for n in z['finalists'] if str(n) in records})
    ages={n:(meta['cutoff_utc_ns']-records[str(n)]['element_epoch_utc_ns'])/3.6e12 for n in finalists}
    for n in finalists:
        r=records[str(n)];cut=meta['cutoff_utc_ns']
        if not 0<=ages[n]<=72 or not cut-72*3600e9<=r['collected_utc_ns']<=cut:
            raise ValueError('Noncausal or out-of-window element')
    sat=tuple(Satrec.twoline2rv(*records[str(n)]['lines']) for n in finalists)
    grid=np.arange(-40.,341.);cat=ElementSetCatalogue(tuple(map(str,finalists)),tuple(finalists),sat)
    p,v,good=ecef_states(cat,meta['origin_utc_ns'],grid)
    phases=np.linspace(-15,15,int(round(30/step))+1)
    results=[]
    for target in expanded:
        source=target['source'];fid=source['fragment_id'];saved=read(SOURCE/'cases'/case/(fid+'.json'))
        times=np.asarray(saved['times_s']);q=source['rf_hz']/11.5e9
        rows=[];arrays={};splits=[]
        for seed in [20261031,94721,4081]:
            train,held,groups=split(times,seed)
            if train.sum()>=8 and held.sum()>=4:
                splits.append((seed,train,held));arrays[f'train_{seed}']=train;arrays[f'held_{seed}']=held
        for arm in ['c0','fitted_c']:
            y=np.asarray(saved['corrected_hz'][arm]);position=receipt['positions'][arm]
            for k,n in enumerate(finalists):
                if n not in target['finalists'] or not good[k]:continue
                bank=dict(time_s=grid,position_km=np.broadcast_to(p[k],(len(phases),*p[k].shape)),
                          velocity_km_s=np.broadcast_to(v[k],(len(phases),*v[k].shape)))
                f,e=paired_phase_frequency(bank,np.tile(times,len(phases)),np.repeat(np.arange(len(phases)),len(times)),phases,*latlon(position))
                f=f.reshape(len(phases),-1)*q;e=e.reshape(len(phases),-1);visible=e.min(axis=1)>=0
                if not visible.any():continue
                full=components(y,f,visible,times,ALIASES,PERIOD)
                group_comps={seed:(components(y,f,visible,times,ALIASES,PERIOD,train),
                                  components(y,f,visible,times,ALIASES,PERIOD,train|held)) for seed,train,held in splits}
                for policy in POLICIES:
                    if policy.startswith('48') and ages[n]>48:continue
                    sigma,penalty=parameters(policy,ages[n]);m=marginal(full,phases,sigma)
                    if not np.isfinite(m['score']):continue
                    a,kphi=m['alias_index'],m['phase_index'];coef=m['beta'];res=m['residual']
                    noise={k:v[0].item() for k,v in batch_noise_screen(res[None,:],times).items()}
                    folds=[]
                    for seed,train,held in splits:
                        tr,union=group_comps[seed];mt=marginal(tr,phases,sigma);mu=marginal(union,phases,sigma)
                        # Score ratio integrates the training posterior; phase
                        # and coefficients are not refitted on held observations.
                        folds.append(dict(seed=seed,training_score=mt['score']+penalty,
                                          held_predictive_score=mu['score']-mt['score'],
                                          training_points=int(train.sum()),held_points=int(held.sum())))
                    row=dict(case=case,fragment_id=fid,arm=arm,policy=policy,norad=n,age_h=ages[n],
                             score=m['score']+penalty,likelihood_score=m['score'],recency_penalty=penalty,
                             rms_hz=m['rms_hz'],phase_s=m['phase_s'],phase_prior_sigma_s=sigma,
                             phase_boundary_mass=m['phase_boundary_mass'],offset_hz=float(coef[0]),rate_hz_s=float(coef[1]),
                             alias=int(ALIASES[a]),noise=noise,minimum_elevation_deg=float(e[kphi].min()),
                             physical_screen_pass=bool(m['rms_hz']<=450 and abs(coef[0])<=3000 and abs(coef[1])<=2 and noise['noise_screen_pass']),
                             integration_penalty=m['integration_penalty'],maximum_component_score=m['maximum_component_score'],
                             clutter_score=float(2*len(times)*np.log(PERIOD)),folds=folds)
                    rows.append(row)
                    key=f'{arm}_{policy}_{n}'
                    arrays[key+'_residual']=res;arrays[key+'_orbit']=f[kphi]
                    arrays[key+'_prediction']=f[kphi]+full['design']@coef-ALIASES[a]*PERIOD
                    arrays[key+'_phase_weights']=m['weights'].sum(axis=0)
        summaries=[]
        for arm in ['c0','fitted_c']:
            for policy in POLICIES:
                ranked=sorted([r for r in rows if r['arm']==arm and r['policy']==policy],key=lambda r:r['score'])
                if len(ranked)<2:raise ValueError('Fewer than two visible finalists')
                winner=ranked[0];runner=ranked[1];fold_winners=[]
                for seed,train,held in splits:
                    ordered=sorted(ranked,key=lambda r:next(f['training_score'] for f in r['folds'] if f['seed']==seed))
                    w=ordered[0];wf=next(f for f in w['folds'] if f['seed']==seed)
                    fold_winners.append(dict(seed=seed,norad=w['norad'],held_predictive_score=wf['held_predictive_score']))
                summaries.append(dict(arm=arm,policy=policy,winner=winner,runner_up=runner,
                                      margin=runner['score']-winner['score'],training_fold_winners=fold_winners))
        for arm in ['c0','fitted_c']:arrays[arm+'_corrected_hz']=np.asarray(saved['corrected_hz'][arm])
        arrays.update(times_s=times,phases_s=phases,values_hz=np.asarray(saved['values_hz']))
        folder=ROOT/'cases'/case;folder.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(folder/(fid+'.npz'),**arrays)
        result=dict(source=source,positions=receipt['positions'],summaries=summaries,candidate_rows=rows,
                    full_72h_catalogue_count=len(records),shortlist_norads=target['finalists'],
                    propagation_failures=[n for n,g in zip(finalists,good) if not g],
                    phase_step_s=step,policy='Frozen inherited radio calibration at published ALGO05 endpoints; conditional candidate comparison, not acceptance')
        write(folder/(fid+'.json'),result);results.append(dict(case=case,fragment_id=fid,rows=len(rows)))
        print(case,fid,'complete',len(rows),'candidate-policy-arm rows',flush=True)
    return results


def safe(case):
    try:return run_case(case)
    except Exception:
        e=traceback.format_exc();write(ROOT/'cases'/case/'failure.json',dict(error=e));print(case,e,flush=True);return []


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case');parser.add_argument('--workers',type=int,default=4);a=parser.parse_args()
    cases=sorted({r['case'] for r in read(SOURCE/'targets.json') if not a.case or r['case']==a.case})
    write(ROOT/'protocol.json',dict(cases=cases,policies=POLICIES,noise_hz=150,bias_sigma_hz=300,rate_sigma_hz_s=.5,
        phase_limit_s=15,phase_step_s=.1,age_scaled_phase_sigma='5 seconds * max(1, age_hours/24)',
        age_identity_prior='relative weight 2**(-max(0,age_hours-48)/24)',aliases=ALIASES,
        nuisance_scope='one phase, offset and rate per contiguous source; receiver fixed; no additional orbital modes',
        candidate_nomination='Reuse prior complete-catalogue coarse shortlist union; full-point phase integration for every finalist',
        validation='3 randomized 12-second group holdouts with 2-second guard, conditional on full-data shortlist and frozen radio model',
        GPS_used=False,future_TLE_used=False,production_changed=False,
        parent_calibration='Inherited sealed normal equations at published ALGO05 endpoints; not a fresh ALGO04 run',
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'targets.json',SOURCE/'causal72.json']}))
    with ProcessPoolExecutor(max_workers=a.workers,max_tasks_per_child=1) as pool:results=list(pool.map(safe,cases))
    write(ROOT/'run.json',dict(results=results,source=str(SOURCE),completed_sources=sum(map(len,results))))
