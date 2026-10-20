"""Bounded RF-only discovery and paired position trials of shared frequency events."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
import time
import numpy as np

from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import coverage,retained_metrics
from ds23_frequency_events import make_event_problem,attach_event_predictive,event_profile,event_design
from ds23_predictive_linear import attach_predictive_linear
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD,profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

OUT=ROOT/'reports/2026_10_20_ds23_frequency_events_v3'
ARMS=('c0','fitted_c')
METHODS=('null','receiver','receiver_RF','band','family')


def parameters(scan,base,old):
    model=old['hyperparameters_from_pre_RF_TLE_only']
    _,receipts=phase_widths(scan,base.labels)
    return np.asarray(old['weights']),forecast_phase_mean(receipts,model['shrinkage']),model


def cached(p):
    original=p.calculate
    @lru_cache(maxsize=8)
    def calculate(x):return original(np.asarray(x))
    p.calculate=lambda x:calculate(tuple(x))
    return p


def prepare(case):
    directory=OUT/case;directory.mkdir(parents=True,exist_ok=True)
    output=directory/'selection.json'
    if output.exists():return read(output)
    scan,node,keep,base,old=context(case);powers,means,model=parameters(scan,base,old)
    memberships=read(ROOT/'reports/2026_10_20_algo02_ds23_association_error/memberships'/(case+'.json'))
    owned=set(memberships['arms']['c0']['associated_observation_ids'])
    unassociated=[t for t in scan.tracks if not owned.intersection(t['observation_ids'])]
    focus=max(unassociated,key=lambda t:np.ptp(t['times']))
    saved=old['policy_arms']['c0'];x=np.array(saved['endpoint_east_north_km'])
    p=cached(make_problem(scan,node,keep,'c0',np.array(saved['phase_reference']),powers,means,model['multiplier'],model['nu']))
    state=p.state(x);f,e=p.conditional_frequency(x);eligible=[]
    for k,(row,i,sl,alias) in enumerate(zip(p.rows,p.members,p.slices,p.alias,strict=True)):
        t=scan.tracks[i]
        if len(t['times'])<12 or np.ptp(t['times'])<10:continue
        q=t['rf_hz']/11.5e9
        y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y,q*f[sl],*scan.white[i])
        if terms['rms'][0]>750 or abs(terms['bias'][0])>3000 or e[sl].min()<0:continue
        eligible.append(dict(component=t['key'],index=i,row=k,candidate_index=row['candidate_index'],
            norad=row['candidate_norad'],receiver=t['receiver'],channel=t['channel'],times=t['times'],
            raw=y+alias*PERIOD-q*f[sl],sigma=p.point_noise[sl]/np.sqrt(powers[k]),
            points=len(y),original_points=int(keep[sl].sum()),profile_rms_hz=terms['rms'][0]))
    trials=[];grid=np.arange(10.,290.01,2.)
    for rx in (1,2):
        curves=[r for r in eligible if r['receiver']==rx]
        if len(curves)<2:continue
        def evaluate(tau):
            spanning=[r for r in curves if sum(r['times']<tau)>=3 and sum(r['times']>=tau)>=3]
            if len({r['channel'] for r in spanning})<2:return None
            information=1.;rhs=0.;pieces=[]
            for r in spanning:
                w=1/r['sigma'];t=r['times'];affine=np.column_stack((np.ones(len(t)),t-t.mean()))*w[:,None]
                raw=r['raw']*w;u=(t>=tau)*300*w
                # Proposal-only affine elimination prevents separated tracks or
                # an existing smooth phase/rate error from voting for a jump.
                raw-=affine@np.linalg.lstsq(affine,raw,rcond=None)[0]
                u-=affine@np.linalg.lstsq(affine,u,rcond=None)[0]
                info=float(u@u);cross=float(u@raw);information+=info;rhs+=cross
                pieces.append(dict(component=r['component'],norad=r['norad'],
                    amplitude_hz=300*cross/(1+info),information=info))
            gain=rhs*rhs/information-np.log(information)
            return dict(receiver=rx,time_s=float(tau),gain=gain,amplitude_hz=float(300*rhs/information),
                per_curve=pieces,
                spanning_components=[r['component'] for r in spanning],
                spanning_families=sorted({r['norad'] for r in spanning}))
        coarse=[r for tau in grid if (r:=evaluate(tau)) is not None]
        if not coarse:continue
        local=[r for r in coarse if focus['times'].min()<r['time_s']<focus['times'].max()]
        if not local:continue
        center=max(local,key=lambda r:r['gain'])['time_s']
        fine=[r for tau in np.arange(max(10,center-2),min(290,center+2)+.01,.25)
              if (r:=evaluate(tau)) is not None]
        trials.extend(coarse+fine)
    penalty=2*np.log(max(len(grid)*2,len(trials))*4)
    # The task is the longest unassociated curve: select its receiver from the
    # saved membership IDs, without hard-coding a receiver or satellite ID.
    focus_trials=[r for r in trials if r['receiver']==focus['receiver'] and
                  focus['times'].min()<r['time_s']<focus['times'].max()]
    best=max(focus_trials,key=lambda r:r['gain']) if focus_trials else None
    offered=keep.copy();added=[]
    if best and best['gain']>penalty:
        for row in eligible:
            if row['receiver']!=best['receiver']:continue
            times=row['times'];tau=best['time_s']
            if sum(times<tau)<3 or sum(times>=tau)<3:continue
            sl=p.slices[row['row']];n=int((~offered[sl]).sum())
            if n:
                offered[sl]=True;added.append({k:v for k,v in row.items() if k not in ('raw','sigma','times')})
    else:best=None
    result=dict(case=case,best=best,search_penalty=penalty,coarse_time_grid_s=grid,
        trials=trials,eligible_components=[{k:v for k,v in r.items() if k not in ('raw','sigma','times')} for r in eligible],
        original_mask=keep,offered_mask=offered,added_curves=added,focus_component=focus['key'],
        offered_additional_points=int(offered.sum()-keep.sum()),source_sha256=sha(ROOT/'tools/probe_ds23_frequency_events.py'),
        original_result_sha256=sha(SOURCE/case/'algo02_result.json'),GPS_used=False,
        no_fixed_satellite_ID_receiver_event_time_or_evaluation_coordinate_in_discovery=True,
        frozen_original_nominations_are_candidate_proposals_not_confirmed_identities=True)
    write(output,result)
    print(case,'event',best,'additional',result['offered_additional_points'],flush=True)
    return result


def events_for(method,selection,base):
    if method=='null' or not selection['best']:return []
    best=selection['best'];tau=best['time_s'];rx=best['receiver']
    common=dict(time_s=tau,sigma_hz=300.)
    if method in ('receiver','receiver_RF'):return [dict(common,kind=method,receiver=rx)]
    if method=='band':return [dict(common,kind='band',receiver=rx,band=b) for b in (0,1)]
    indices=sorted({r['candidate_index'] for r in selection['eligible_components']
                    if r['component'] in best['spanning_components']})
    return [dict(common,kind='family',candidate_index=j) for j in indices]


def summary(p,x,entries):
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;linear=[]
    for entry,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=p.scan.tracks[entry['track_index']];r=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(r,np.zeros(len(r)),*p.scan.white[entry['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        linear.append(dict(component=entry['component'],norad=entry['norad'],candidate_index=entry['candidate_index'],
            observation_ids=entry['observation_ids'],points=len(r),compatible=bool(terms['rms'][0]<=450 and
                abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0 and noise['noise_screen_pass'][0]
                and c['linear_elevation'][sl].min()>=0)))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),state=p.state(x),phase_reference=p.reference,
        gates=retained_metrics(p,x),linear_gates=linear,negative_twice_elbo=c['negative_twice_elbo'],
        curved_negative_twice_elbo=curved['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        active_points=int(p.keep.sum()),predictive_points=sum(e['points'] for e in entries),
        linear_calibration_max_difference=float(np.max(abs(c['coefficient']-curved['coefficient']))),
        events=p.events,event_amplitudes_hz=c.get('event_amplitudes_hz',np.array([])))


def refit(scan,node,keep,arm,powers,means,model,events,entries):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for epoch in range(5):
        p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,events)
        attach_event_predictive(p,entries,powers);cached(p)
        result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    record=summary(p,x,entries);record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'])
    return record


def recover_independent_family(case):
    """Targeted follow-up: use the already audited all-catalogue transfer screen."""
    if case!='DS23-0268':raise ValueError('the independent transfer audit exists only for the debug case')
    output=OUT/case/'receiver_reentry.json'
    if output.exists():return read(output)
    audit=ROOT/'reports/2026_10_20_ds23_0268_longest_unassociated'
    left,right=read(audit/'step_transfer.json'),read(audit/'step_transfer_fitted_c.json')
    candidates=[]
    for a,b in zip(left['rows'],right['rows'],strict=True):
        original=a['results']['original']['candidates'][0]['norad']
        new=[r['results']['RX1_step_from_other_family']['candidates'][0] for r in (a,b)]
        if all(r['norad']==original and r['noise']['noise_screen_pass'] and r['rms_hz']<=450
               and abs(r['bias_hz'])<=3000 for r in new):candidates.append(a['component'])
    scan,node,keep,base,old=context(case);powers,means,model=parameters(scan,base,old)
    selection=read(OUT/case/'selection.json');offered=np.asarray(selection['offered_mask'],bool)
    for row,sl in zip(base.rows,base.slices,strict=True):
        if row['component'] in candidates:offered[sl]=True
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    events=events_for('receiver',selection,base)
    pair={a:refit(scan,node,offered,a,powers,means,model,events,entries) for a in ARMS}
    result=dict(case=case,method='receiver_reentry',arms=pair,paired_valid=pair_passes(pair,include_linear=True),
        mask=offered,events=events,powers=powers,additional_components=candidates,
        targeted_independent_family_screen_not_a_full_new_catalogue_search=True,
        GPS_used=False,future_TLE_used=False,original_points_never_removed=True)
    write(output,result)
    return result


def cohort_case(case):
    selection=prepare(case);directory=OUT/case
    if not selection['best'] or not selection['offered_additional_points']:
        write(directory/'policy.json',dict(case=case,accepted=False,reason='no_penalized_event_or_new_points'))
        return dict(case=case,accepted=False)
    run(case,'null');run(case,'receiver')
    left,right=read(directory/'null.json'),read(directory/'receiver.json')
    gain=left['arms']['c0']['negative_twice_elbo']-right['arms']['c0']['negative_twice_elbo']
    accepted=bool(right['paired_valid'] and gain>selection['search_penalty'])
    write(directory/'policy.json',dict(case=case,accepted=accepted,same_mask_null_gain=gain,
        penalty=selection['search_penalty'],paired_valid=right['paired_valid'],
        selection='minimum full c0 bound after time/model-search penalty, all original paired gates must pass',
        no_GPS_selection=True))
    return dict(case=case,accepted=accepted,gain=gain,paired_valid=right['paired_valid'])


def cohort():
    cases=[r['case'] for r in read(ROOT/'reports/2026_10_20_algo03_reassociation_cohort/execution.json')['receipts']
           if r['case']!='DS23-0268']
    write(OUT/'cohort_protocol.json',dict(cases=cases,development_case='DS23-0268',workers=20,
        fixed_receiver_event_prior_sigma_hz=300,one_event_within_longest_unassociated_curve=True,
        regional_start_km=[0,0],box_width_km=25,RF_only_event_discovery=True,
        cohort_is_previous_development_set_not_external_location_validation=True))
    results=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures={executor.submit(cohort_case,c):c for c in cases}
        for future in as_completed(futures):
            try:row=future.result()
            except Exception as exc:row=dict(case=futures[future],failed=repr(exc))
            results.append(row);print(row,flush=True)
    write(OUT/'cohort_execution.json',dict(results=results,seconds=time.monotonic()-started))


def run(case,method):
    selection=read(OUT/case/'selection.json');output=OUT/case/(method+'.json')
    if output.exists():return dict(case=case,method=method,cached=True)
    scan,node,keep,base,old=context(case);powers,means,model=parameters(scan,base,old)
    offered=np.asarray(selection['offered_mask'],bool);events=events_for(method,selection,base)
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    started=time.monotonic();pair={a:refit(scan,node,offered,a,powers,means,model,events,entries) for a in ARMS}
    write(output,dict(case=case,method=method,arms=pair,paired_valid=pair_passes(pair,include_linear=True),
        mask=offered,events=events,powers=powers,original_points_never_removed=True,
        same_offered_points_aliases_labels_noise_other_priors_search_budgets_in_all_methods=True,
        event_time_discovered_by_RF_only=True,amplitude_Gaussian_SD_hz=300,
        time_and_method_search_penalty=selection['search_penalty'],seconds=time.monotonic()-started,
        GPS_used=False,future_TLE_used=False))
    print(case,method,'valid',pair_passes(pair,include_linear=True),'seconds',time.monotonic()-started,flush=True)
    return dict(case=case,method=method,seconds=time.monotonic()-started)


def verify(case):
    scan,node,keep,base,old=context(case);powers,means,model=parameters(scan,base,old)
    rows=[];entries=old['linear_entries'] if old['linear_paired_valid'] else []
    for arm in ARMS:
        saved=old['policy_arms'][arm];x=np.asarray(saved['endpoint_east_north_km']);ref=np.asarray(saved['phase_reference'])
        p=make_event_problem(scan,node,keep,arm,ref,powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        c=p.calculate(x);difference=c['negative_twice_elbo']-saved['negative_twice_elbo']
        assert abs(difference)<1e-3
        # A zero-scale extra column must leave the entire original posterior intact.
        z=make_event_problem(scan,node,keep,arm,ref,powers,means,model,[dict(kind='receiver',receiver=1,time_s=100,sigma_hz=0)])
        attach_event_predictive(z,entries,powers);cz=z.calculate(x)
        assert abs(cz['negative_twice_elbo']-c['negative_twice_elbo'])<1e-7
        assert np.max(abs(cz['conditional_residual_hz']-c['conditional_residual_hz']))<1e-6
        assert np.max(abs(z.state(x)['beta'][:-1]-p.state(x)['beta']))<1e-6
        rows.append(dict(arm=arm,original_objective_replay_difference=difference,
                         zero_scale_event_objective_difference=cz['negative_twice_elbo']-c['negative_twice_elbo']))
    write(OUT/case/'replay.json',dict(rows=rows))
    print('Original and zero-event replays passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',default='DS23-0268')
    parser.add_argument('--stage',choices=('prepare','verify','run','all','cohort','recover'),default='all')
    parser.add_argument('--method',choices=METHODS);args=parser.parse_args()
    if args.stage in ('prepare','all'):prepare(args.case)
    if args.stage in ('verify','all'):verify(args.case)
    if args.stage=='run':run(args.case,args.method)
    if args.stage=='recover':recover_independent_family(args.case)
    if args.stage=='cohort':cohort()
    if args.stage=='all':
        with ProcessPoolExecutor(max_workers=5) as executor:
            for future in as_completed([executor.submit(run,args.case,m) for m in METHODS]):print(future.result(),flush=True)
