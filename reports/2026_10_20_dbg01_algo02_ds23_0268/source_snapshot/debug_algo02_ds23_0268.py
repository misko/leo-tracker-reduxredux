"""DBG01 inference for the worst qualified ALGO02 fast scan.

Evaluation coordinates enter only the explicitly supplied diagnostic request.
No source, contract, original measurement or benchmark result is overwritten.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_predictive_linear import attach_predictive_linear
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_inference_audit import disk_grid
from dsx01_radial_restarts import discover_at_start
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from map_dsx01_clean_region import finite_gradient
from probe_algo03_frame_peak_recovery import context as load_context,SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state
from run_dsx01_joint_descent import descend,signature
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile,whitening

CASE='DS23-0268'
OUT=ROOT/'reports/2026_10_20_dbg01_algo02_ds23_0268'
ARMS=('c0','fitted_c')
STARTS=sorted(disk_grid(step_km=2)[1],key=lambda x:(float(np.linalg.norm(x)),*x))
DISCOVERY_STARTS=sorted(disk_grid(step_km=5)[1],key=lambda x:(float(np.linalg.norm(x)),*x))
WORKERS=24


@lru_cache(maxsize=1)
def context():
    scan,node,keep,base,old=load_context(CASE)
    return scan,node,keep,base,old


def build(node,keep,arm,reference,entries,control='baseline'):
    scan,_,_,_,old=context();model=dict(old['hyperparameters_from_pre_RF_TLE_only'])
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    _,receipts=phase_widths(scan,labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    if control=='phase_x2':model['multiplier']*=2
    elif control=='phase_zero_mean':means*=0
    p=make_problem(scan,node,keep,arm,reference,np.array(old['weights']),means,model['multiplier'],model['nu'])
    if control=='bias1000':p.constants*=1000/300
    elif control in ('drift1','smooth50'):
        # Change prior scales in latent coordinates; preserve the physical
        # design read by state()/conditional_frequency() and all gates.
        width=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
        begin=p.hardware.shape[1]+p.smooth.shape[1]
        mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
        groups=np.full(width,-1,int)
        if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
        scales=np.ones(width);scales[-len(p.members):]=.3
        if control=='drift1':scales[[4,6]]=.1
        else:scales[p.hardware.shape[1]:begin]=.25
        powers=np.asarray(old['weights'])
        def calculate(x):
            c=JointMarginal.calculate(p,x);features=c['features']
            raw=p.values-p.q*c['intercept']-features@mean;present=np.unique(p.noise_groups[keep])
            bound=hierarchical_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
                powers=powers[present],prior_groups=None if model['nu'] is None else groups,
                prior_nu=4 if model['nu'] is None else model['nu'])
            bound=scale_posterior(bound,scales);bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
            precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
            bound['conditional_residual_hz']=p.values-p.q*c['intercept']-features@bound['coefficient']
            volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
            bound['residual']=np.r_[bound['residual'],np.sqrt(volume)];c.update(bound)
            return c
        p.calculate=calculate
    elif control=='orbit3':
        p.mode_bank=dict(p.mode_bank,**{k:np.asarray(p.mode_bank[k])*3 for k in ('position_km','velocity_km_s')})
    elif control not in ('baseline','phase_x2','phase_zero_mean'):
        raise ValueError('unknown predeclared control')
    attach_predictive_linear(p,entries,np.asarray(old['weights']))
    calculate=p.calculate
    @lru_cache(maxsize=8)
    def cached(x):return calculate(np.asarray(x))
    p.calculate=lambda x:cached(tuple(np.asarray(x,float)))
    return p


def decomposition(p,x):
    c=p.calculate(x);curved=p.curved_calculate(x) if hasattr(p,'curved_calculate') else c
    a=curved['latent_coefficient'];precision=curved['coefficient_prior_precision']
    nb,ns,nl=p.hardware.shape[1],p.smooth.shape[1],len(p.labels)
    blocks=dict(offset=slice(0,4),drift=slice(4,8),c=slice(8,nb),smooth=slice(nb,nb+ns),
                phase=slice(nb+ns,nb+ns+nl),orbit=slice(nb+ns+nl,len(a)-len(p.members)),
                fragment=slice(len(a)-len(p.members),len(a)))
    prior={k:float(np.sum(a[v]**2*precision[v])) for k,v in blocks.items()}
    data=float(curved['quadratic']-sum(prior.values()))
    terms=dict(weighted_data=data,**{'prior_'+k:v for k,v in prior.items()},
               logvolume=float(curved['logvolume']),noise_Gamma=float(curved['noise_gamma_cost']),
               prior_Gamma=float(curved['prior_gamma_cost']),normalization=float(curved['normalization_constant']),
               predictive_linear=float(c['negative_twice_elbo']-curved['negative_twice_elbo']))
    reconstructed=sum(terms.values())
    if abs(reconstructed-c['negative_twice_elbo'])>1e-6:
        raise ValueError('objective decomposition does not close')
    return dict(terms=terms,reconstruction_error=float(reconstructed-c['negative_twice_elbo']))


def linear_gates(p,x,entries):
    c=p.calculate(x);gates=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=p.scan.tracks[e['track_index']];r=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(r,np.zeros(len(r)),*p.scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        gates.append(dict(component=e['component'],norad=e['norad'],points=e['points'],
            observation_ids=e['observation_ids'],rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),
            compatible=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and
                int(terms['alias'][0])==0 and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0),
            noise={k:v[0] for k,v in noise.items()}))
    return gates


def summary(p,x,entries=(),details=False):
    c=p.calculate(x);state=p.state(x)
    result=dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),
        score=float(p.residual(x)@p.residual(x)),negative_twice_elbo=c['negative_twice_elbo'],
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        active_points=int(p.keep.sum()),predictive_points=sum(e['points'] for e in entries),
        phase_reference=p.reference,state=state,
        gates=retained_metrics(p,x),linear_gates=linear_gates(p,x,entries))
    if details:
        tracks=[]
        frequency,elevation=p.conditional_frequency(x)
        for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
            t=p.scan.tracks[i];active=p.keep[sl]
            if not active.any():continue
            times=t['times'][active];r=c['conditional_residual_hz'][sl][active]
            q=t['rf_hz']/11.5e9
            y=t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
            terms=profile(y[active],q*frequency[sl][active],*whitening(times))
            tracks.append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],norad=row['candidate_norad'],
                times=times,residual_hz=r,noise_sigma_hz=p.point_noise[sl][active],
                maximum_radio_standardized_residual=float(max(abs(r)/p.point_noise[sl][active])),
                profile_noise={k:v[0] for k,v in batch_noise_screen(terms['innovations'],times).items()},
                minimum_elevation_deg=float(elevation[sl][active].min()),alias=int(alias)))
        result.update(tracks=tracks,decomposition=decomposition(p,x))
    return result


def fixed(node,keep,arm,point,entries,control='baseline',details=False):
    reference=np.zeros(len({r['candidate_index'] for r in node['seed']['rows']}));changes=[]
    for _ in range(5):
        p=build(node,keep,arm,reference,entries,control)
        phase=np.clip(p.state(point)['phases'][p.labels],-15,15)
        changes.append(float(max(abs(phase-reference))));reference=phase
    d=summary(p,np.asarray(point),entries,details)
    d['final_phase_change_s']=changes[-1];d['phase_changes_s']=changes
    return p,d


def refit(node,keep,arm,entries,start=(0,0),control='baseline'):
    reference=np.zeros(len({r['candidate_index'] for r in node['seed']['rows']}));x=np.asarray(start,float);history=[]
    for _ in range(5):
        p=build(node,keep,arm,reference,entries,control)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(max(abs(phase-reference)))))
        reference=phase
    return dict(summary(p,x,entries),history=history,final_phase_change_s=history[-1]['phase_change_s'])


def entries_for(old):return old['linear_entries'] if old['linear_paired_valid'] else []


def audit():
    scan,node,keep,base,old=context();request=read(OUT/'request.json');point=np.asarray(request['diagnostic_point'])
    arms={}
    for arm in ARMS:
        saved=old['policy_arms'][arm];entries=entries_for(old);x=np.asarray(saved['endpoint_east_north_km'])
        p=build(node,keep,arm,np.asarray(saved['phase_reference']),entries)
        d=summary(p,x,entries,True)
        difference=d['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(difference)>=1e-5:raise ValueError('original endpoint does not replay')
        metrics=d['gates'];extended=extend_associations(p,x,metrics)
        endpoint_gradient=finite_gradient(lambda z:float(p.calculate(z)['negative_twice_elbo']),x)
        _,at_point=fixed(node,keep,arm,point,entries,details=True)
        gradient=finite_gradient(lambda z:fixed(node,keep,arm,z,entries)[1]['negative_twice_elbo'],point)
        arms[arm]=dict(endpoint=d,diagnostic_point=at_point,objective_replay_difference=difference,
            gradient_at_endpoint=endpoint_gradient,refreshed_gradient_at_diagnostic_point=gradient,
            diagnostic_point_initialized_refit=refit(node,keep,arm,entries,start=point),
            associations=extended,label='Reference position is an evaluation oracle only')
    write(OUT/'audit.json',dict(case=CASE,algorithm='ALGO02-v1',arms=arms))
    return dict(stage='audit')


def discover(index):
    scan,_,_,_,_=context()
    record=discover_at_start(scan,scan.radio_sigma_hz,DISCOVERY_STARTS[index],budget=4)
    node=dict(seed=dict(rows=record['seed']['rows'],state=zero_state(scan)),aliases=record['aliases'])
    write(OUT/f'discovery_{index:02d}.json',dict(node=node,receipt=record['discovery_provenance']))
    return dict(stage='discover',index=index)


def bank():
    scan,node,keep,_,old=context()
    candidates=[copy.deepcopy(node)]
    original=read(SOURCE/CASE/'fit_radio_noise.json')
    candidates.extend(copy.deepcopy(c['node']) for c in original['choices'])
    candidates.extend(read(OUT/f'discovery_{i:02d}.json')['node'] for i in range(13))
    population=[r['component'] for r in node['seed']['rows']]
    needed={e['candidate_index'] for e in entries_for(old)};nodes=[];excluded=[];seen=set()
    for candidate in candidates:
        if [r['component'] for r in candidate['seed']['rows']]!=population:
            raise ValueError('nomination pool changed observation order')
        candidate['seed']['state']=zero_state(scan);key=signature(candidate)
        if key in seen:continue
        seen.add(key);labels={r['candidate_index'] for r in candidate['seed']['rows']}
        if needed-labels:
            excluded.append(dict(signature=key,missing_predictive_candidate_indices=sorted(needed-labels)))
            continue
        nodes.append(candidate)
    write(OUT/'hypothesis_bank.json',dict(nodes=nodes,excluded=excluded,
        raw_unique_hypotheses=len(seen),same_curved_and_predictive_observations=True,
        current_predictive_labels_fixed=True,
        exclusion='A branch cannot silently remove the current predictive satellite factors. Unsupported original predictive families excluded from full-objective comparison.',
        discovery_receipt_sha256={f'discovery_{i:02d}.json':sha(OUT/f'discovery_{i:02d}.json') for i in range(13)},
        finite_whole_assignment_pool_not_exhaustive_catalogue_reassociation=True))
    return dict(stage='bank',eligible=len(nodes),excluded=len(excluded))


def restart(index):
    _,_,keep,_,old=context();nodes=read(OUT/'hypothesis_bank.json')['nodes'];entries=entries_for(old)
    arms={};schedule=[]
    for arm in ARMS:
        refs=[np.zeros(len({r['candidate_index'] for r in n['seed']['rows']})) for n in nodes]
        x=np.asarray(STARTS[index],float);history=[]
        for epoch in range(5):
            problems=[build(n,keep,arm,ref,entries) for n,ref in zip(nodes,refs,strict=True)]
            if arm=='c0':
                # Across identity branches, compare normalized evidence, not
                # incompatible additive residual-coordinate constants.
                for p in problems:
                    residual=p.residual
                    def normalized(z,p=p,residual=residual):
                        r=residual(z);c=p.calculate(z)
                        offset=c['negative_twice_elbo']-float(c['residual']@c['residual'])+1e6
                        if offset<0:raise ValueError('objective padding too small')
                        return np.r_[r,np.sqrt(offset)]
                    p.residual=normalized
                descent=descend(problems,x,max_steps=48);chosen=descent['final_mode'];schedule.append(chosen)
            else:
                chosen=schedule[epoch];fitted=fit(problems[chosen],x,iterations=48)
                descent=dict(parameters=fitted['parameters'],final_mode=chosen,switches=[],stopped=fitted['stopped'],
                    trace=[dict(point=h['parameters'],score=h['score'],mode=chosen) for h in fitted['history']])
            x=np.asarray(descent['parameters']);changes=[]
            for k,p in enumerate(problems):
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                changes.append(float(max(abs(phase-refs[k]))));refs[k]=phase
            history.append(dict(epoch=epoch,descent=descent,selected_mode=chosen,phase_changes_s=changes))
        result=summary(problems[chosen],x,entries)
        arms[arm]=dict(result,history=history,final_mode=chosen,final_phase_change_s=changes[chosen])
    write(OUT/f'restart_{index:02d}.json',dict(start_id=index,start=STARTS[index],arms=arms,
        paired_valid=pair_passes(arms,include_linear=True),
        fitted_c_follows_c0_phase_round_branch_schedule=True,
        conditional_predictive_labels_fixed=True,curved_labels_and_aliases_can_switch_each_c0_step=True))
    return dict(stage='restart',index=index)


def grid(index):
    _,node,keep,_,old=context();points=read(OUT/'request.json')['surface_points'];rows=[]
    for k,point in list(enumerate(points))[index::WORKERS]:
        arms={}
        for arm in ARMS:
            _,d=fixed(node,keep,arm,point,entries_for(old))
            arms[arm]={key:d[key] for key in ('score','negative_twice_elbo','RMS_hz','final_phase_change_s')}
        rows.append(dict(index=k,point=point,arms=arms))
    write(OUT/f'grid_{index:02d}.json',dict(rows=rows))
    return dict(stage='grid',index=index)


def intervention(kind,index):
    scan,node,keep0,base,old=context();keep=keep0.copy();entries=copy.deepcopy(entries_for(old))
    request=read(OUT/'interventions.json');target=request[kind][index];control='baseline'
    if kind=='family':
        for row,sl in zip(base.rows,base.slices,strict=True):
            if row['candidate_norad']==target:keep[sl]=False
        entries=[e for e in entries if e['norad']!=target]
    elif kind=='track':
        for row,sl in zip(base.rows,base.slices,strict=True):
            if row['component']==target:keep[sl]=False
    else:control=target
    pair={arm:refit(node,keep,arm,entries,control=control) for arm in ARMS}
    write(OUT/f'{kind}_{index:02d}.json',dict(kind=kind,target=target,arms=pair,
        deleted_curved_points=int(keep0.sum()-keep.sum()),original_nuisance_design_retained=True,
        deleted_predictive_points=sum(e['points'] for e in entries_for(old))-sum(e['points'] for e in entries),
        paired_gates_valid=pair_passes(pair,include_linear=True),diagnostic_not_GPS_selection_rule=True))
    return dict(stage=kind,index=index)


def execute(job):
    stage,index=job
    return {'audit':lambda _:audit(),'discover':discover,'grid':grid,'restart':restart,
            'family':lambda i:intervention('family',i),'track':lambda i:intervention('track',i),
            'prior':lambda i:intervention('prior',i)}[stage](index)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['audit','discover','bank','analyze'],required=True)
    args=parser.parse_args();started=time.monotonic()
    if args.stage=='bank':print(bank(),flush=True);return
    if args.stage=='audit':jobs=[('audit',0)]
    elif args.stage=='discover':jobs=[('discover',i) for i in range(13)]
    else:
        intervention_request=read(OUT/'interventions.json')
        jobs=[('grid',i) for i in range(WORKERS)]+[('restart',i) for i in range(len(STARTS))]
        jobs += [(kind,i) for kind in ('family','track','prior') for i in range(len(intervention_request[kind]))]
    existing=[];pending=[]
    for stage,index in jobs:
        filename='audit.json' if stage=='audit' else f'{stage}_{index:02d}.json'
        (existing if (OUT/filename).exists() else pending).append((stage,index))
    receipts=[]
    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        futures={executor.submit(execute,job):job for job in pending}
        for future in as_completed(futures):
            r=future.result();receipts.append(r);print(r,flush=True)
            write(OUT/(args.stage+'_progress.json'),dict(completed=len(receipts),pending_total=len(pending)))
    write(OUT/(args.stage+'_execution.json'),dict(receipts=receipts,existing=existing,
        seconds=time.monotonic()-started,all_terminal=True))


if __name__=='__main__':main()
