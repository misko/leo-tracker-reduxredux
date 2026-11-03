"""Frozen-endpoint full-catalogue diagnostics; future TLEs are never inference."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
import numpy as np
from sgp4.api import Satrec

from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_ds23_frequency_events import OUT as EVENTS,parameters,cached
from ds23_frequency_events import make_event_problem,attach_event_predictive
from run_algo01_ds23_sample import ROOT,read,write
from prototype_dsx01_continuous_position import latlon
from analyze_dsx01_fixed_site import ecef_states
from leo.sky.propagation import ElementSetCatalogue
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry,phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile,PERIOD
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

CASE='DS23-0268'
OUT=ROOT/'reports/2026_10_20_ds23_0268_remaining_tracks'
ARMS=('c0','fitted_c')


def fine_receiver_basis(times):
    """Normalize on a fixed scan grid, never on a particular track's support."""
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    grid=np.linspace(0,300,301)
    scale=np.linalg.norm(projected_receiver_basis(grid))/np.linalg.norm(projected_receiver_basis(grid,spacing_s=10,width_s=15))
    return scale*projected_receiver_basis(times,spacing_s=10,width_s=15)


@lru_cache(maxsize=1)
def load():
    scan,node,_,base,old=context(CASE)
    saved=read(EVENTS/CASE/'receiver_reentry.json');coverage=read(EVENTS/CASE/'receiver_reentry_coverage.json')
    powers,means,hyper=parameters(scan,base,old);problems={}
    for arm in ARMS:
        r=saved['arms'][arm];x=np.asarray(r['endpoint_east_north_km'])
        p=make_event_problem(scan,node,np.asarray(saved['mask'],bool),arm,np.asarray(r['phase_reference']),powers,means,hyper,saved['events'])
        attach_event_predictive(p,old['linear_entries'],powers);cached(p)
        assert abs(p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo'])<1e-3
        problems[arm]=(p,x)
    return scan,base,saved,coverage,problems


def family_frequency(p,x,j,bank=None,corrected=True,times=None):
    scan=p.scan;state=p.state(x);times=scan.times if times is None else np.asarray(times)
    source=scan.sky if bank is None else bank
    sub=dict(time_s=source['time_s'],position_km=source['position_km'][[j]],velocity_km_s=source['velocity_km_s'][[j]])
    phase=np.asarray([state['phases'][j]])
    f,e=paired_phase_frequency(sub,times,np.zeros(len(times),int),phase,*latlon(x))
    if corrected and j in p.supported:
        local=p.labels.index(j);k=p.supported.index(j);begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
        modes=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*local:3*local+3],
            velocity_km_s=p.mode_bank['velocity_km_s'][3*local:3*local+3])
        derivative=paired_frequency_modes(sub,modes,times,np.zeros(len(times),int),phase,*latlon(x))
        f+=derivative@p.calculate(x)['coefficient'][begin+3*k:begin+3*k+3]
    return f,e


def corrected_observation(p,x,i):
    t=p.scan.tracks[i];s=p.state(x);q=t['rf_hz']/11.5e9
    return t['values']-p.scan.hardware(t,s['beta'])-q*p.scan.rx_basis[i]@s['smooth'][t['receiver']-1]


def banks():
    scan,*_=load();output=OUT/'postscan_bank.npz'
    if output.exists():return
    post=read(OUT/'postscan_tles.json');numbers=list(map(int,scan.norads));records=post['versions']
    chosen=[records[str(n)] if str(n) in records else scan.elements[str(n)] for n in numbers]
    cat=ElementSetCatalogue(tuple(str(n) for n in numbers),tuple(numbers),tuple(Satrec.twoline2rv(*r['lines']) for r in chosen))
    position,velocity,usable=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
    if not usable.all():raise ValueError('postscan diagnostic propagation failed')
    np.savez_compressed(output,time_s=scan.sky['time_s'],position_km=position,velocity_km_s=velocity,norad=scan.norads)
    write(OUT/'postscan_bank_receipt.json',dict(available=len(records),fallback_to_causal=post['missing'],
        diagnostic_only=True,search_position_unchanged=True))


def inventory():
    scan,base,saved,coverage,problems=load();owned=set(coverage['arms']['c0']['associated_observation_ids']);ranking=[]
    for i,t in enumerate(scan.tracks):
        unknown=[o for o in t['observation_ids'] if o not in owned]
        if not unknown:continue
        nominee=next((r['candidate_norad'] for r in base.rows if r['component']==t['key']),None)
        ranking.append(dict(track_index=i,component=t['key'],receiver=t['receiver'],channel=t['channel'],
            points=len(t['times']),unassociated_points=len(unknown),start_s=float(t['times'][0]),end_s=float(t['times'][-1]),
            span_s=float(np.ptp(t['times'])),pieces=len(t['pieces']),curved=i in scan.curved,nominee=nominee))
    ranking.sort(key=lambda r:r['span_s'],reverse=True)
    observations=read(SOURCE/CASE/'observations.json');graph_ids={o for t in scan.tracks for o in t['observation_ids']}
    write(OUT/'inventory.json',dict(case=CASE,ranking=ranking,total_GLRT=len(observations),
        associated=len(owned),unassociated=len(observations)-len(owned),graph_owned=len(graph_ids),
        unassociated_graph_points=len(graph_ids-owned),outside_graph=len({o['observation_id'] for o in observations}-graph_ids),
        current_model='receiver_reentry',position_not_refitted=True))
    print('Unassociated graph tracks',len(ranking),'curved',sum(r['curved'] for r in ranking),flush=True)


def detail(terms,k,noise,phase,norad,elevation):
    return dict(norad=int(norad),phase_s=float(phase),rms_hz=float(terms['rms'][k]),bias_hz=float(terms['bias'][k]),
        alias=int(terms['alias'][k]),cost=float(terms['cost'][k]),minimum_elevation_deg=float(elevation[k].min()),
        noise={name:value[k] for name,value in noise.items()},
        passing=bool(terms['rms'][k]<=450 and abs(terms['bias'][k])<=3000 and noise['noise_screen_pass'][k] and elevation[k].min()>=0),
        residual_hz=terms['residual'][k])


def screen():
    scan,base,saved,coverage,problems=load();ranking=read(OUT/'inventory.json')['ranking']
    all_times=scan.times;phases=np.linspace(-15,15,121);post=dict(np.load(OUT/'postscan_bank.npz'))
    # Evaluate geometry once per phase/catalogue on the union of observation times.
    observed={arm:{r['track_index']:corrected_observation(p,x,r['track_index']) for r in ranking}
              for arm,(p,x) in problems.items()}
    for kind,bank in (('causal',scan.sky),('postscan',post)):
        destination=OUT/(kind+'_screen.json')
        if destination.exists():continue
        records={arm:{r['track_index']:dict(best_passing=None,best_by_norad={},passing_norads=set()) for r in ranking} for arm in ARMS}
        for phase_index,phase in enumerate(phases):
            geometry=prepare_phase_geometry(bank,all_times,np.full(len(scan.norads),phase))
            for arm,(p,x) in problems.items():
                frequency,elevation,_=phase_linear_frequency(geometry,*latlon(x))
                for row in ranking:
                    i=row['track_index'];t=scan.tracks[i];ix=scan.index[i];e=elevation[:,ix]
                    terms=profile(observed[arm][i],t['rf_hz']/11.5e9*frequency[:,ix],*scan.white[i])
                    noise=batch_noise_screen(terms['innovations'],t['times'])
                    visible=e.min(axis=1)>=0
                    valid=visible&(terms['rms']<=450)&(abs(terms['bias'])<=3000)&noise['noise_screen_pass']
                    storage=records[arm][i];storage['passing_norads'].update(map(int,scan.norads[valid]))
                    if valid.any():
                        j=int(np.argmin(np.where(valid,terms['cost'],np.inf)))
                        if storage['best_passing'] is None or terms['cost'][j]<storage['best_passing']['cost']:
                            storage['best_passing']=detail(terms,j,noise,phase,scan.norads[j],e)
                    # Rank by the original curve evidence only; no post-TLE-derived phase priors.
                    cost=np.where(visible,terms['cost'],np.inf)
                    for j in np.argsort(cost)[:5]:
                        if not np.isfinite(cost[j]):continue
                        n=int(scan.norads[j]);previous=storage['best_by_norad'].get(n)
                        if previous is None or cost[j]<previous['cost']:
                            storage['best_by_norad'][n]=detail(terms,j,noise,phase,n,e)
                    # Always retain the original nominee, even when not top five.
                    if row['nominee'] is not None:
                        j=int(np.flatnonzero(scan.norads==row['nominee'])[0]);n=int(scan.norads[j])
                        previous=storage['best_by_norad'].get(n)
                        if visible[j] and (previous is None or terms['cost'][j]<previous['cost']):
                            storage['best_by_norad'][n]=detail(terms,j,noise,phase,n,e)
            if (phase_index+1)%20==0:print(kind,'phase',phase_index+1,'/',len(phases),flush=True)
        payload={}
        for arm,values in records.items():
            payload[arm]=[]
            for row in ranking:
                storage=values[row['track_index']];candidates=sorted(storage['best_by_norad'].values(),key=lambda r:r['cost'])
                payload[arm].append(dict(**row,candidates=candidates[:6],nominee_best=storage['best_by_norad'].get(row['nominee']),
                    passing_norads=sorted(storage['passing_norads']),
                    best_passing=storage['best_passing'],
                    independent_phase_screen_not_shared_family_acceptance=True))
        write(destination,dict(case=CASE,kind=kind,arms=payload,phase_grid_s=phases,catalogue_candidates=len(scan.norads),
            frozen_RF_position_and_hardware=True,no_new_candidate_orbit_modes=True,
            no_GPS_used=True,future_TLE_used=kind=='postscan',postscan_not_a_localization_result=True))
        print('Saved',destination,flush=True)


def refine():
    """Check fine phase intervals; a coarse grid must not manufacture rejection."""
    scan,base,saved,coverage,problems=load();post=dict(np.load(OUT/'postscan_bank.npz'))
    for kind,bank in (('causal',scan.sky),('postscan',post)):
        source=OUT/(kind+'_screen.json');output=OUT/(kind+'_refined.json')
        if not source.exists() or output.exists():continue
        document=read(source);payload={}
        for arm,(p,x) in problems.items():
            payload[arm]=[]
            for row in document['arms'][arm]:
                if not row['curved']:continue
                i=row['track_index'];t=scan.tracks[i];y=corrected_observation(p,x,i);q=t['rf_hz']/11.5e9
                candidates=[]
                for candidate in row['candidates'][:4]:
                    n=candidate['norad'];j=int(np.flatnonzero(scan.norads==n)[0]);center=candidate['phase_s']
                    local=dict(time_s=bank['time_s'],position_km=bank['position_km'][[j]],velocity_km_s=bank['velocity_km_s'][[j]])
                    trials=[]
                    for phase in np.linspace(max(-15,center-.3),min(15,center+.3),61):
                        g=prepare_phase_geometry(local,t['times'],np.array([phase]));f,e,_=phase_linear_frequency(g,*latlon(x))
                        terms=profile(y,q*f,*scan.white[i]);noise=batch_noise_screen(terms['innovations'],t['times'])
                        trials.append(detail(terms,0,noise,phase,n,e))
                    best=min(trials,key=lambda r:r['cost']);passing=[r for r in trials if r['passing']]
                    candidates.append(dict(best=best,best_passing=min(passing,key=lambda r:r['cost']) if passing else None,
                        passing_phase_range_s=[min(r['phase_s'] for r in passing),max(r['phase_s'] for r in passing)] if passing else None))
                candidates.sort(key=lambda r:r['best']['cost'])
                payload[arm].append(dict(**{k:v for k,v in row.items() if k not in ('candidates','nominee_best','best_passing')},
                    refined=candidates))
        write(output,dict(kind=kind,arms=payload,phase_step_s=.01,top_coarse_candidates=4,diagnostic_only=True))


def reentry_job(name,keys,choice=0):
    from algo02_scan import pair_passes
    from probe_ds23_frequency_events import refit
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    output=OUT/'reentry'/(name+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():return dict(name=name,cached=True)
    scan,base,saved,coverage,problems=load();node=copy.deepcopy(context(CASE)[1]);old=context(CASE)[4]
    keep=np.asarray(saved['mask'],bool).copy();proposals=read(OUT/'causal_refined.json')['arms']['c0'];changes=[]
    for key in keys:
        r=next(r for r in proposals if key in r['component']);candidate=r['refined'][choice]['best']
        component=r['component'];j=int(np.flatnonzero(scan.norads==candidate['norad'])[0])
        for k,row in enumerate(node['seed']['rows']):
            if row['component']==component:
                changes.append(dict(component=component,original_norad=row['candidate_norad'],norad=candidate['norad']))
                row['candidate_index']=j;row['candidate_norad']=candidate['norad'];node['aliases'][k]=candidate['alias']
        sl=next(sl for row,sl in zip(base.rows,base.slices,strict=True) if row['component']==component);keep[sl]=True
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']});_,receipts=phase_widths(scan,labels)
    hyper=old['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,hyper['shrinkage'])
    pair={arm:refit(scan,node,keep,arm,np.asarray(saved['powers']),means,hyper,saved['events'],old['linear_entries']) for arm in ARMS}
    result=dict(name=name,changes=changes,added_curved_points=int(keep.sum()-np.asarray(saved['mask'],bool).sum()),
        arms=pair,paired_valid=pair_passes(pair,include_linear=True),mask=keep,node=node,
        original_position_evidence_never_removed=True,all_original_priors_and_event_time_retained=True,
        cold_start_km=[0,0],rounds=5,position_steps_per_round=48,GPS_used=False,future_TLE_used=False)
    write(output,result);print(name,'added',result['added_curved_points'],'valid',result['paired_valid'],flush=True)
    return dict(name=name,paired_valid=result['paired_valid'],added_curved_points=result['added_curved_points'])


def reentry():
    jobs=dict(family_66797=['RX1-CH4-T006','RX1-CH5-T005'],family_59342=['RX2-CH5-T001'],
        family_63963=['RX1-CH7-T003'],family_69445=['RX2-CH4-T001'],family_64333=['RX1-CH7-T000'],
        family_67953=['RX1-CH2-T005'],all_local_passing=['RX1-CH4-T006','RX1-CH5-T005','RX2-CH5-T001','RX1-CH7-T003','RX2-CH4-T001'])
    results=[]
    with ProcessPoolExecutor(max_workers=7) as executor:
        for future in as_completed([executor.submit(reentry_job,name,keys) for name,keys in jobs.items()]):
            results.append(future.result())
    write(OUT/'reentry_execution.json',dict(receipts=results,full_pipeline_not_rerun=True,
        graph_and_GLRT_unchanged=True,association_proposals_from_RF_only_frozen_endpoint_screen=True))


def alternate():
    reentry_job('CH7_alternative_69468',['RX1-CH7-T000'],1)


def transfer():
    """Learn an extra receiver trend from other accepted families, never CH7."""
    scan,base,saved,coverage,problems=load();target=next(i for i,t in enumerate(scan.tracks) if 'RX1-CH7-T000-' in t['key'])
    t=scan.tracks[target];window=(t['times'].min()-10,t['times'].max()+10);mid=np.mean(window);span=np.ptp(window)/2
    outputs={}
    for arm,(p,x) in problems.items():
        c=p.calculate(x);training=[]
        for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
            control=scan.tracks[i];use=p.keep[sl]&(control['times']>=window[0])&(control['times']<=window[1])
            if control['receiver']==1 and i!=target and use.sum()>=6:
                training.append(dict(component=control['key'],norad=row['candidate_norad'],
                    times=control['times'][use],residual=c['conditional_residual_hz'][sl][use],
                    q=np.full(int(use.sum()),control['rf_hz']/11.5e9),
                    weight=np.sqrt(saved['powers'][k]*c['noise_precision'][k])/p.point_noise[sl][use]))
        if len({r['norad'] for r in training})<2:raise ValueError('independent-family calibration support required')
        times=np.concatenate([r['times'] for r in training]);raw=np.concatenate([r['residual'] for r in training])
        q=np.concatenate([r['q'] for r in training]);w=np.concatenate([r['weight'] for r in training])
        groups=np.concatenate([np.full(len(r['times']),k) for k,r in enumerate(training)])
        r=next(r for r in read(OUT/'causal_refined.json')['arms'][arm] if r['track_index']==target)
        baseline=np.asarray(r['refined'][0]['best']['residual_hz']);tests=[]
        for model in ('affine','smooth'):
            def basis(a):
                if model=='affine':return np.column_stack((np.ones(len(a)),(a-mid)/span))*200
                centers=np.arange(window[0],window[1]+.01,10)
                return 200*np.exp(-.5*((a[:,None]-centers)/15)**2)
            for law in ('additive','RF_scaled'):
                u=basis(times)*(q[:,None] if law=='RF_scaled' else 1)
                constants=np.eye(len(training))[groups]*300;features=np.column_stack((u,constants));weighted=features*w[:,None]
                coefficient=np.linalg.solve(np.eye(features.shape[1])+weighted.T@weighted,weighted.T@(raw*w))
                prediction=basis(t['times'])@coefficient[:u.shape[1]]
                if law=='RF_scaled':prediction*=t['rf_hz']/11.5e9
                corrected=baseline-prediction;corrected-=corrected.mean()
                noise=batch_noise_screen(corrected[None,:],t['times'])
                tests.append(dict(model=model,law=law,predicted_correction_hz=prediction,residual_hz=corrected,
                    rms_hz=float(np.sqrt(np.mean(corrected**2))),noise={k:v[0] for k,v in noise.items()}))
                if model=='smooth' and law=='RF_scaled':
                    loo=[]
                    for omitted in sorted({r['norad'] for r in training}):
                        use=np.asarray([training[k]['norad']!=omitted for k in groups]);a=features[use]*w[use,None]
                        coefficient=np.linalg.solve(np.eye(features.shape[1])+a.T@a,a.T@(raw[use]*w[use]))
                        prediction=basis(t['times'])@coefficient[:u.shape[1]]*t['rf_hz']/11.5e9
                        corrected=baseline-prediction;corrected-=corrected.mean();noise=batch_noise_screen(corrected[None,:],t['times'])
                        loo.append(dict(omitted_family=omitted,rms_hz=float(np.sqrt(np.mean(corrected**2))),
                            noise={k:v[0] for k,v in noise.items()}))
                    tests[-1]['leave_one_correction_training_family_out']=loo
        outputs[arm]=dict(training=training,target_component=t['key'],times=t['times'],baseline_residual_hz=baseline,
            baseline_rms_hz=float(np.sqrt(np.mean(baseline**2))),tests=tests)
    write(OUT/'CH7_independent_receiver_transfer.json',dict(arms=outputs,
        target_data_never_used_to_fit_receiver_correction=True,position_and_orbits_frozen=True,
        no_formal_full_posterior_confidence_claim=True))


def kernel_job(include_target,alternate=False):
    from algo02_scan import pair_passes
    from probe_ds23_frequency_events import refit
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    name='fine_kernel'+('_CH7' if include_target else '_baseline')+('_alt69468' if alternate else '');output=OUT/'reentry'/(name+'.json')
    if output.exists():return dict(name=name,cached=True)
    scan,base,saved,coverage,problems=load();node=copy.deepcopy(context(CASE)[1]);old=context(CASE)[4]
    changed=copy.copy(scan);grid=np.linspace(0,300,301)
    original=projected_receiver_basis(grid);fine=projected_receiver_basis(grid,spacing_s=10,width_s=15)
    scale=float(np.linalg.norm(original)/np.linalg.norm(fine))
    changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    node['seed']['state']['smooth']=np.zeros((2,fine.shape[1]))
    keep=np.asarray(saved['mask'],bool).copy()
    if include_target:
        sl=next(sl for row,sl in zip(base.rows,base.slices,strict=True) if 'RX1-CH7-T000-' in row['component']);keep[sl]=True
    powers,means,hyper=parameters(scan,base,old)
    if alternate:
        from investigate_ds23_adaptive_failures import phase_widths
        from probe_ds23_causal_phase_mean import forecast_phase_mean
        proposal=next(r for r in read(OUT/'causal_refined.json')['arms']['c0'] if 'RX1-CH7-T000-' in r['component'])
        candidate=next(r['best'] for r in proposal['refined'] if r['best']['norad']==69468)
        for k,row in enumerate(node['seed']['rows']):
            if 'RX1-CH7-T000-' in row['component']:
                row['candidate_norad']=69468;row['candidate_index']=int(np.flatnonzero(scan.norads==69468)[0]);node['aliases'][k]=candidate['alias']
        _,receipts=phase_widths(scan,sorted({r['candidate_index'] for r in node['seed']['rows']}))
        means=forecast_phase_mean(receipts,hyper['shrinkage'])
    pair={arm:refit(changed,node,keep,arm,powers,means,hyper,saved['events'],old['linear_entries']) for arm in ARMS}
    result=dict(name=name,mask=keep,node=node,arms=pair,paired_valid=pair_passes(pair,include_linear=True),
        grid_spacing_s=10,kernel_width_s=15,basis_scale=scale,
        average_pointwise_prior_variance_matched_on_fixed_0_300s_grid=True,
        original_curved_and_predictive_points_preserved=True,added_curved_points=60 if include_target else 0,
        other_priors_weights_and_cold_search_budgets_unchanged=True,GPS_used=False,future_TLE_used=False,
        one_scan_development_diagnostic_not_validated_new_algorithm=True)
    write(output,result);print(name,'valid',result['paired_valid'],flush=True)
    return dict(name=name,paired_valid=result['paired_valid'])


def kernel():
    with ProcessPoolExecutor(max_workers=2) as executor:
        receipts=[f.result() for f in as_completed([executor.submit(kernel_job,flag,alternate) for flag,alternate in ((False,False),(True,False),(True,True))])]
    write(OUT/'kernel_execution.json',dict(receipts=receipts))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('inventory','banks','screen','refine','reentry','alternate','transfer','kernel'),required=True)
    stage=parser.parse_args().stage
    globals()[stage]()
