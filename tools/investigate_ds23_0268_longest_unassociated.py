"""Causal full-catalogue diagnosis of the longest unassociated ALGO02 curve.

Frozen endpoint diagnostics do not fit position or establish transmitter truth.
"""

import argparse
from functools import lru_cache
import numpy as np

from algo02_scan import bind_run_directory, load_scan
from audit_ds23_algo01_coverage import retained_metrics
from compare_dsx01_frame_joint import conditional_gate
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD, profile, projected_receiver_basis, whitening
from leo.analysis.research.robust_polynomial_order import polynomial_orders

SOURCE = ROOT / 'reports/2026_10_19_algo02_ds23_full'
OUT = ROOT / 'reports/2026_10_20_ds23_0268_longest_unassociated'
CASE = 'DS23-0268'
ARMS = ('c0', 'fitted_c')


@lru_cache(maxsize=1)
def context():
    bind_run_directory(SOURCE)
    scan = load_scan(SOURCE, CASE)
    old = read(SOURCE / CASE / 'algo02_result.json')
    node = read(SOURCE / CASE / 'result.json')['final_node']
    membership = read(ROOT / 'reports/2026_10_20_algo02_ds23_association_error/memberships' / (CASE + '.json'))
    return scan, old, node, membership


def inventory():
    scan, old, node, membership = context()
    observations = read(SOURCE / CASE / 'observations.json')
    owned = set(membership['arms']['c0']['associated_observation_ids'])
    ranking = []
    for i, t in enumerate(scan.tracks):
        keep = np.array([o not in owned for o in t['observation_ids']])
        if not keep.any():
            continue
        times = t['times'][keep]
        ranking.append(dict(component=t['key'], track_index=i, points=int(keep.sum()),
                            span_s=float(np.ptp(times)), start_s=float(times.min()), end_s=float(times.max()),
                            largest_gap_s=float(np.diff(times).max()) if len(times)>1 else 0,
                            wholly_unassociated=bool(keep.all()), pieces=len(t['pieces'])))
    ranking.sort(key=lambda r: (r['span_s'], r['points']), reverse=True)
    raw_runs = []
    # This permissive raw continuity inventory is a diagnostic, not a graph
    # join or an emitter association. Curvature/fit checks are still required.
    for rx in (1, 2):
        for ch in range(1, 9):
            points = sorted([o for o in observations if o['receiver']==rx and o['channel']==ch
                             and o['observation_id'] not in owned], key=lambda o:o['time_s'])
            runs = []
            for o in points:
                if runs:
                    last = runs[-1][-1]
                    dt = o['time_s']-last['time_s']
                    delta = (o['measured_cfo_hz']-last['measured_cfo_hz']+PERIOD/2)%PERIOD-PERIOD/2
                    continuous = 0 < dt <= 3 and abs(delta) <= 6000*dt+600
                else:
                    continuous = False
                if continuous:
                    runs[-1].append(o)
                else:
                    runs.append([o])
            for run in runs:
                if len(run)<6:
                    continue
                times = np.array([o['time_s'] for o in run])
                values = np.unwrap(np.array([o['measured_cfo_hz'] for o in run])*2*np.pi/PERIOD)*PERIOD/(2*np.pi)
                raw_runs.append(dict(receiver=rx, channel=ch, points=len(run), span_s=float(np.ptp(times)),
                    start_s=float(times[0]),end_s=float(times[-1]), observation_ids=[o['observation_id'] for o in run],
                    degree4_rms_hz=float(np.sqrt(np.mean((values-np.polynomial.Polynomial.fit(times,values,4)(times))**2)))))
    raw_runs.sort(key=lambda r:(r['span_s'],r['points']), reverse=True)
    target = scan.tracks[ranking[0]['track_index']]
    write(OUT/'inventory.json',dict(case=CASE, graph_tracks=ranking, raw_contiguous_runs=raw_runs,
        raw_continuity_gap_s=3, raw_continuity_maximum_rate_hz_s=6000,
        raw_runs_are_not_verified_single_emitters=True, target=ranking[0],
        original_result_sha256=sha(SOURCE/CASE/'algo02_result.json')))
    write(OUT/'target.json',target)
    write(OUT/'polynomial_orders.json',polynomial_orders(target['times'],target['values']))
    print('Longest graph curves:',ranking[:3],flush=True)
    print('Longest raw continuity runs:',[{k:v for k,v in r.items() if k!='observation_ids'} for r in raw_runs[:5]],flush=True)


def build(arm):
    scan, old, node, _ = context()
    labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
    model = old['hyperparameters_from_pre_RF_TLE_only']
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, model['shrinkage'])
    saved = old['policy_arms'][arm]
    p = make_problem(scan,node,np.array(old['mask'],bool),arm,np.array(saved['phase_reference']),
                     np.array(old['weights']),means,model['multiplier'],model['nu'])
    calculate = p.calculate
    @lru_cache(maxsize=4)
    def cached(x):
        return calculate(np.asarray(x))
    p.calculate = lambda x:cached(tuple(x))
    return p, np.array(saved['endpoint_east_north_km'])


def noise_row(residual,times):
    return {k:v[0] for k,v in batch_noise_screen(np.atleast_2d(residual),times).items()}


def screen():
    scan, old, node, membership = context()
    target = read(OUT/'inventory.json')['target'];i = target['track_index'];t = scan.tracks[i]
    times, q = t['times'], t['rf_hz']/11.5e9
    phases = np.linspace(-15,15,121)
    widths, receipts = phase_widths(scan,list(range(len(scan.norads))))
    model = old['hyperparameters_from_pre_RF_TLE_only']
    means = forecast_phase_mean(receipts,model['shrinkage']);widths *= model['multiplier']
    frozen, results = {}, {}
    observed = {}
    for arm in ARMS:
        p,x = build(arm);state = p.state(x);c = p.calculate(x)
        k = next(k for k,r in enumerate(p.rows) if r['component']==t['key']);sl=p.slices[k]
        y = t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        observed[arm] = y
        f,e = p.conditional_frequency(x)
        terms = profile(y,q*f[sl],*scan.white[i])
        conditional = c['conditional_residual_hz'][sl]
        frozen[arm]=dict(assigned_norad=p.rows[k]['candidate_norad'],
            family_phase_s=state['phases'][p.rows[k]['candidate_index']],
            retained_points=int(p.keep[sl].sum()),
            profile_rms_hz=terms['rms'][0],bias_hz=terms['bias'][0],alias=terms['alias'][0],
            profile_noise=noise_row(terms['innovations'],times),
            conditional_gate=conditional_gate(conditional,times),
            conditional_residual_hz=conditional,profile_residual_hz=terms['residual'][0],
            native_prediction_hz=t['values']-terms['residual'][0],
            elevation_min_deg=float(e[sl].min()), mask_history=old['curved_gate_history'])
        shape = (len(phases),len(scan.norads))
        results[arm]={k:np.empty(shape) for k in ('cost','rms','bias','alias','minimum_elevation')}
        results[arm]['passing']=np.empty(shape,bool)
    for k,phase in enumerate(phases):
        geometry = prepare_phase_geometry(scan.sky,times,np.full(len(scan.norads),phase))
        for arm in ARMS:
            x=np.array(old['policy_arms'][arm]['endpoint_east_north_km'])
            frequency,elevation,_=phase_linear_frequency(geometry,*latlon(x))
            terms=profile(observed[arm],q*frequency,*scan.white[i])
            diagnostics=batch_noise_screen(terms['innovations'],times)
            valid=(terms['rms']<=450)&(abs(terms['bias'])<=3000)&diagnostics['noise_screen_pass']&(elevation.min(axis=1)>=0)
            for name,value in dict(cost=terms['cost']+((phase-means)/widths)**2,
                rms=terms['rms'],bias=terms['bias'],alias=terms['alias'],minimum_elevation=elevation.min(axis=1),passing=valid).items():
                results[arm][name][k]=value
        if (k+1)%20==0:
            print('Exact causal phase sweep',k+1,'/',len(phases),flush=True)
    active_norads={r['norad'] for r in old['policy_arms']['c0']['gates']['tracks'] if r['compatible']}
    summaries={}
    for arm,r in results.items():
        rows=[]
        for j,norad in enumerate(scan.norads):
            visible=r['minimum_elevation'][:,j]>=0
            if not visible.any():continue
            best=int(np.argmin(np.where(visible,r['cost'][:,j],np.inf)))
            shape=int(np.argmin(np.where(visible,r['rms'][:,j],np.inf)))
            def detail(k):
                return dict(phase_s=phases[k],rms_hz=r['rms'][k,j],bias_hz=r['bias'][k,j],
                    alias=int(r['alias'][k,j]),cost=r['cost'][k,j],passing=bool(r['passing'][k,j]))
            passing=np.flatnonzero(r['passing'][:,j])
            rows.append(dict(norad=int(norad),candidate_index=j,currently_active_family=int(norad) in active_norads,
                phase_prior_mean_s=means[j],phase_prior_sigma_s=widths[j],best_cost=detail(best),best_shape=detail(shape),
                best_passing=detail(int(passing[np.argmin(r['cost'][passing,j])])) if len(passing) else None))
        rows.sort(key=lambda r:r['best_cost']['cost'])
        write(OUT/(arm+'_candidates.json'),rows)
        np.savez_compressed(OUT/(arm+'_phase_grid.npz'),phases_s=phases,norads=scan.norads,**r)
        summaries[arm]=dict(top_cost=rows[:12],top_shape=sorted(rows,key=lambda r:r['best_shape']['rms_hz'])[:12],
            passing=[r for r in rows if r['best_passing']], frozen=frozen[arm],visible_candidates=len(rows))
    write(OUT/'screen.json',dict(case=CASE,target=target,arms=summaries,catalogue_candidates=len(scan.norads),
        phase_range_s=[-15,15],phase_step_s=.25,position_fixed_at_RF_endpoint=True,
        active_family_phase_is_only_freed_for_diagnosis=True,
        screen_excludes_orbit_modes_for_new_candidates=True,original_family_frozen_includes_existing_orbit_modes=True,
        GPS_used=False,future_TLE_used=False))
    print({arm:dict(passing=[r['norad'] for r in summaries[arm]['passing']],top=summaries[arm]['top_cost'][:2],
        frozen=summaries[arm]['frozen']['profile_noise']) for arm in ARMS},flush=True)


def golden(function,left,right,steps=40):
    ratio=(np.sqrt(5)-1)/2
    a,b=right-ratio*(right-left),left+ratio*(right-left)
    fa,fb=function(a),function(b)
    for _ in range(steps):
        if fa<fb:
            right,b,fb=b,a,fa;a=right-ratio*(right-left);fa=function(a)
        else:
            left,a,fa=a,b,fb;b=left+ratio*(right-left);fb=function(b)
    return a if fa<fb else b


def diagnose():
    scan,old,node,membership=context();target=read(OUT/'target.json')
    i=read(OUT/'inventory.json')['target']['track_index'];t=scan.tracks[i];times=t['times'];q=t['rf_hz']/11.5e9
    screen=read(OUT/'screen.json');arms={}
    for arm in ARMS:
        p,x=build(arm);state=p.state(x);c=p.calculate(x);f,e=p.conditional_frequency(x)
        observed=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        candidates=[]
        for row in screen['arms'][arm]['top_cost'][:5]:
            j=row['candidate_index'];bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],
                                              velocity_km_s=scan.sky['velocity_km_s'][[j]])
            def calculate(phase):
                geometry=prepare_phase_geometry(bank,times,np.array([phase]))
                frequency,elevation,_=phase_linear_frequency(geometry,*latlon(x))
                terms=profile(observed,q*frequency,*scan.white[i])
                score=float(terms['cost'][0]+((phase-row['phase_prior_mean_s'])/row['phase_prior_sigma_s'])**2)
                return score,terms,float(elevation.min())
            seed=row['best_cost']['phase_s']
            phase=golden(lambda v:calculate(v)[0],max(-15,seed-.5),min(15,seed+.5))
            score,terms,elevation=calculate(phase);residual=terms['residual'][0]
            xnorm=(times-times.mean())/(np.ptp(times)/2);models=[]
            for degree in range(4):
                correction=np.polynomial.Polynomial.fit(times,residual,degree)
                remaining=residual-correction(times)
                models.append(dict(degree=degree,remaining_rms_hz=float(np.sqrt(np.mean(remaining**2))),
                    correction_hz=correction(times),remaining_residual_hz=remaining,
                    maximum_centered_correction_hz=float(max(abs(correction(times)-np.mean(correction(times))))),
                    noise=noise_row(remaining,times),
                    slope_at_midpoint_hz_s=float(correction.deriv()(times.mean()))))
            candidates.append(dict(norad=row['norad'],phase_s=phase,cost=score,alias=int(terms['alias'][0]),
                bias_hz=terms['bias'][0],rms_hz=terms['rms'][0],minimum_elevation_deg=elevation,
                residual_hz=residual,noise=noise_row(terms['innovations'],times),
                free_polynomial_diagnostics_only=models,native_prediction_hz=t['values']-residual))
        family=[];cross_channel=[]
        for k,(row,member,sl,alias) in enumerate(zip(p.rows,p.members,p.slices,p.alias,strict=True)):
            if row['candidate_norad']!=64923:continue
            tr=scan.tracks[member];qt=tr['rf_hz']/11.5e9
            y=tr['values']-scan.hardware(tr,state['beta'])-qt*scan.rx_basis[member]@state['smooth'][tr['receiver']-1]
            terms=profile(y,qt*f[sl],*scan.white[member])
            family.append(dict(component=tr['key'],receiver=tr['receiver'],channel=tr['channel'],
                points=len(y),retained_points=int(p.keep[sl].sum()),times=tr['times'],
                residual_hz=terms['residual'][0],normalized_residual_hz=terms['residual'][0]/qt,
                noise=noise_row(terms['innovations'],tr['times']),rms_hz=terms['rms'][0]))
            if not p.keep[sl].any() or tr['key']==t['key']:continue
            pieces=tr['pieces']
            overlap=(times>=tr['times'].min())&(times<=tr['times'].max())
            if overlap.sum()<6:continue
            tx=times[overlap];prediction=np.full(len(tx),np.nan)
            for piece in pieces:
                valid=(tx>=piece['start_s'])&(tx<=piece['end_s'])
                z=(tx[valid]-piece['reference_time_s'])/piece['time_scale_s']
                prediction[valid]=np.polynomial.legendre.legval(z,piece['coefficients_hz'])
            valid=np.isfinite(prediction);tx=tx[valid];prediction=prediction[valid]
            other=dict(tr,times=tx)
            corrected=prediction-scan.hardware(other,state['beta'])-qt*projected_receiver_basis(tx)@state['smooth'][tr['receiver']-1]
            delta=observed[overlap][valid]/q-corrected/qt
            delta-=delta.mean()
            cross_channel.append(dict(other_component=tr['key'],other_channel=tr['channel'],times=tx,
                differential_reference_hz=delta,rms_hz=float(np.sqrt(np.mean(delta**2))),
                slope_hz_s=float(np.polyfit(tx-tx.mean(),delta,1)[0]),
                description='Orbit cancels if same emitter. Target raw CFO minus independent other-channel graph polynomial; '
                            'RF-normalized and hardware-corrected; constant removed.'))
        arms[arm]=dict(refined_candidates=candidates,family=family,cross_channel=cross_channel)
    write(OUT/'diagnostics.json',dict(case=CASE,arms=arms,unpenalized_polynomials_are_not_accepted_model_terms=True,
        paired_cross_channel_comparisons_do_not_use_TLE_prediction=True))
    print({a:[(r['norad'],r['phase_s'],r['rms_hz'],r['noise']) for r in d['refined_candidates'][:1]] for a,d in arms.items()},flush=True)


def reenter():
    from ds23_predictive_linear import attach_predictive_linear
    from investigate_dsx01_localization_failures import fit
    from probe_algo03_frame_peak_recovery import refit
    from report_algo02_ds23 import position_error
    scan,old,node,membership=context();base,_=build('c0');target=read(OUT/'target.json')
    index=next(k for k,r in enumerate(base.rows) if r['component']==target['key'])
    keep=np.array(old['mask'],bool);keep[base.slices[index]]=True
    model=old['hyperparameters_from_pre_RF_TLE_only'];_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);powers=np.array(old['weights'])
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    pair={}
    for arm in ARMS:
        result=refit(scan,node,keep,powers,means,model,arm,entries)
        result['error_km']=position_error(result['endpoint_latlon']);pair[arm]=result
        write(OUT/'reentry_partial.json',dict(arms=pair))
    write(OUT/'reentry.json',dict(case=CASE,arms=pair,added_points=int(keep.sum()-np.sum(old['mask'])),
        all_original_position_evidence_preserved=True, original_curve_weight=float(powers[index]),
        accepted=all(r['compatible'] for d in pair.values() for r in d['gates']['tracks']+d['linear_gates']),
        GPS_used_for_error_reporting_only=True, all_position_fits_start_at_regional_box_center=True))


def independent_correction():
    scan,old,node,_=context();target=read(OUT/'target.json');arms={}
    for arm in ARMS:
        p,x=build(arm);state=p.state(x);f,e=p.conditional_frequency(x)
        target_k=next(k for k,r in enumerate(p.rows) if r['component']==target['key'])
        target_i=p.members[target_k];target_sl=p.slices[target_k];tr=scan.tracks[target_i]
        reference=float(np.mean(tr['times']));scale=float(np.ptp(tr['times'])/2)
        def basis(times):
            z=(times-reference)/scale
            return np.column_stack((z,z*z-1/3))*150
        arms[arm]={}
        for control in ('same_family_other_channels','other_families_same_RX_lowband'):
            normal=np.eye(2);rhs=np.zeros(2);training=[]
            for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
                t=scan.tracks[i];active=p.keep[sl].copy()
                active &= (t['times']>=tr['times'].min())&(t['times']<=tr['times'].max())
                eligible=(row['candidate_norad']==64923 and i!=target_i) if control=='same_family_other_channels' else (
                    row['candidate_norad']!=64923 and t['receiver']==1 and t['channel']<=4)
                if not eligible or active.sum()<4:continue
                q=t['rf_hz']/11.5e9;times=t['times'][active]
                y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
                residual=y[active]+alias*PERIOD-q*f[sl][active]
                design=q*basis(times);w=1/p.point_noise[sl][active]**2
                one=w.sum()+1/300**2;cross=design.T@w
                normal+=design.T@(w[:,None]*design)-np.outer(cross,cross)/one
                rhs+=design.T@(w*residual)-cross*(w@residual)/one
                training.append(dict(component=t['key'],points=int(active.sum())))
            coefficient=np.linalg.solve(normal,rhs);q=tr['rf_hz']/11.5e9
            y=tr['values']-scan.hardware(tr,state['beta'])-q*scan.rx_basis[target_i]@state['smooth'][0]
            correction=q*basis(tr['times'])@coefficient
            terms=profile(y,q*f[target_sl]+correction,*scan.white[target_i])
            arms[arm][control]=dict(training=training,coefficient=coefficient,target_correction_hz=correction,
                posterior_covariance=np.linalg.inv(normal),target_rms_hz=terms['rms'][0],bias_hz=terms['bias'][0],
                target_residual_hz=terms['residual'][0],noise=noise_row(terms['innovations'],tr['times']))
    write(OUT/'independent_correction.json',dict(arms=arms,target_never_used_in_correction_fit=True,
        diagnostic_only=True,common_two_coefficient_linear_quadratic_prior_sigma_hz=150,
        no_position_updated=True))


def raw_refine():
    from concurrent.futures import ThreadPoolExecutor,as_completed
    import json
    import time
    from decoupled_pilot_clocks import ContinuousCoupledWorkspace
    from fast_local_pilot_refinement import FastPilotWorkspace
    panel=OUT/'raw_panel.npz';z=np.load(panel,allow_pickle=False)
    metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz']
    arrays={p['window_key']:z[p['window_key']] for p in metadata['points']};z.close()
    def one(point):
        values=arrays[point['window_key']][:,point['receiver_offset']]
        samples=values[:,0].astype(float)+1j*values[:,1]
        peak=point['peak'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
        center=peak['fractional_tracking_cfo_hz']
        work=ContinuousCoupledWorkspace(samples,fs,point['edge'],epoch)
        fit=work.fast_joint_fit(center)
        odd=work.frequency_fit(fit['CFO_hz'],fit['offset_samples'],fit['modulation_ppm'],subset='odd')
        even=work.frequency_fit(fit['CFO_hz'],fit['offset_samples'],fit['modulation_ppm'],subset='even')
        return dict(point=point,archived_CFO_hz=center,refined=fit,
            original_score=float(work.evaluate([center])[0]),
            odd=odd,even=even,delta_hz=fit['CFO_hz']-center,
            qualified=bool(fit['margin']>0 and not any(fit[k] for k in
                ('frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary'))))
    started=time.monotonic();rows=[]
    with ThreadPoolExecutor(max_workers=8) as executor:
        for future in as_completed([executor.submit(one,p) for p in metadata['points']]):
            rows.append(future.result())
            if len(rows)%15==0:
                write(OUT/'raw_refinement_partial.json',dict(rows=rows))
                print('Existing-IQ pilot refinement',len(rows),'/',len(metadata['points']),flush=True)
    write(OUT/'raw_refinement.json',dict(rows=rows,seconds=time.monotonic()-started,panel_sha256=sha(panel),
        no_GPS_TLE_or_satellite_prediction_in_RF_estimator=True,
        helpers_sha256={name:sha(ROOT/'tools'/name) for name in (
            'decoupled_pilot_clocks.py','fast_local_pilot_refinement.py','local_pilot_refinement.py')},
        original_contracts_unchanged=True))


def raw_evaluate():
    scan,old,node,_=context();target=read(OUT/'target.json');data=read(OUT/'raw_refinement.json')
    by_id={r['point']['observation_id']:r for r in data['rows']};arms={}
    for arm in ARMS:
        p,x=build(arm);state=p.state(x);f,e=p.conditional_frequency(x)
        k=next(k for k,r in enumerate(p.rows) if r['component']==target['key']);i=p.members[k];sl=p.slices[k];t=scan.tracks[i]
        q=t['rf_hz']/11.5e9
        delta=np.array([by_id[oid]['delta_hz'] if by_id[oid]['qualified'] else 0 for oid in t['observation_ids']])
        y=t['values']+delta-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][0]
        terms=profile(y,q*f[sl],*scan.white[i])
        arms[arm]=dict(delta_hz=delta,qualified_points=sum(by_id[oid]['qualified'] for oid in t['observation_ids']),
            frozen_rms_hz=terms['rms'][0],frozen_noise=noise_row(terms['innovations'],t['times']),
            frozen_residual_hz=terms['residual'][0],bias_hz=terms['bias'][0])
        if (OUT/'shared_step.json').exists():
            correction=np.asarray(read(OUT/'shared_step.json')['arms'][arm]['target_correction_hz'])
            corrected=profile(y,q*f[sl]+correction,*scan.white[i])
            arms[arm].update(shared_step_rms_hz=corrected['rms'][0],
                shared_step_residual_hz=corrected['residual'][0],
                shared_step_noise=noise_row(corrected['innovations'],t['times']))
    write(OUT/'raw_evaluation.json',dict(arms=arms,calibration_and_position_unchanged=True,
        unqualified_refinements_fall_back_to_original_CFO=True,
        in_sample_RF_score_gain_does_not_establish_CFO_truth=True))


def shared_step():
    """Predict the held-out target using a change point learned on other channels."""
    scan,old,node,_=context();target=read(OUT/'target.json');arms={}
    # Exact same discovery times and prior scales in the paired c arms.
    grid=np.arange(70.,115.0001,.25);chosen_tau=None
    for arm in ARMS:
        p,x=build(arm);state=p.state(x);frequency,elevation=p.conditional_frequency(x)
        training=[];ys=[];qs=[];ts=[];sigmas=[];groups=[]
        for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
            if row['candidate_norad']!=64923 or row['component']==target['key']:continue
            t=scan.tracks[i];q=t['rf_hz']/11.5e9
            y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][0]
            raw=y+alias*PERIOD-q*frequency[sl]
            groups.extend([len(training)]*len(raw));ys.extend(raw);qs.extend([q]*len(raw))
            ts.extend(t['times']);sigmas.extend(p.point_noise[sl])
            training.append(dict(component=t['key'],points=len(raw),retained_points=int(p.keep[sl].sum())))
        y,q,times,sigma,g=map(np.asarray,(ys,qs,ts,sigmas,groups))
        constants=np.eye(len(training))[g.astype(int)]*300
        def model(tau=None,law='RF_scaled'):
            step=(times>=tau)*300*(q if law=='RF_scaled' else 1) if tau is not None else None
            design=constants if step is None else np.column_stack((step,constants))
            u=design/sigma[:,None];z=y/sigma
            normal=np.eye(u.shape[1])+u.T@u;rhs=u.T@z;coefficient=np.linalg.solve(normal,rhs)
            cost=float(z@z-rhs@coefficient+np.linalg.slogdet(normal)[1])
            return dict(cost=cost,coefficient=coefficient,covariance=np.linalg.inv(normal))
        baseline=model();curves=[]
        for tau in grid:
            r=model(tau)
            curves.append(dict(time_s=tau,cost=r['cost'],amplitude_hz=float(300*r['coefficient'][0])))
        best=min(curves,key=lambda r:r['cost'])
        if chosen_tau is None:chosen_tau=best['time_s']
        result=model(chosen_tau);additive=model(chosen_tau,'additive_Hz')
        k=next(k for k,r in enumerate(p.rows) if r['component']==target['key']);i=p.members[k];sl=p.slices[k];tr=scan.tracks[i]
        qt=tr['rf_hz']/11.5e9
        observed=tr['values']-scan.hardware(tr,state['beta'])-qt*scan.rx_basis[i]@state['smooth'][0]
        amplitude=float(300*result['coefficient'][0]);correction=qt*(tr['times']>=chosen_tau)*amplitude
        terms=profile(observed,qt*frequency[sl]+correction,*scan.white[i])
        noise=noise_row(terms['innovations'],tr['times'])
        arms[arm]=dict(training=training,training_points=len(y),null_cost=baseline['cost'],
            selected_time_s=chosen_tau,amplitude_at_11_5GHz_hz=amplitude,
            amplitude_conditional_sigma_hz=float(300*np.sqrt(result['covariance'][0,0])),
            training_fit_improvement=baseline['cost']-result['cost'],search_penalty=2*np.log(len(grid)),
            penalized_training_gain=baseline['cost']-result['cost']-2*np.log(len(grid)),
            additive_Hz_cost=additive['cost'],RF_scaled_cost=result['cost'],
            additive_amplitude_hz=float(300*additive['coefficient'][0]),
            target_correction_hz=correction,target_residual_hz=terms['residual'][0],
            target_rms_hz=float(terms['rms'][0]),target_bias_hz=float(terms['bias'][0]),
            target_alias=int(terms['alias'][0]),target_noise=noise,
            target_profile_compatible=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000
                and int(terms['alias'][0])==p.alias[k] and noise['noise_screen_pass']),curve=curves)
    write(OUT/'shared_step.json',dict(arms=arms,target_never_used_to_fit_time_or_amplitude=True,
        all_other_original_64923_nominations_included_even_if_currently_rejected=True,
        single_conditional_step_amplitude_prior_sigma_hz=300,selection_times_s=grid,
        family_is_single_RX_only_and_cannot_identify_receiver_vs_satellite=True,
        fitted_c_uses_c0_selected_time=True,diagnostic_not_promoted_to_algorithm=True,
        calibration_covariance_not_propagated_in_this_conditional_change_point_fit=True))


def transfer_step(arm='c0'):
    """Probe a receiver-wide step on other families, with all-catalogue proposals."""
    scan,old,node,_=context();step=read(OUT/'shared_step.json')['arms'][arm]
    tau=step['selected_time_s'];p,x=build(arm);state=p.state(x)
    selected=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        t=scan.tracks[i]
        if row['candidate_norad']==64923 or t['receiver']!=1 or len(t['times'])<12:continue
        if t['times'].min()<=tau-4 and t['times'].max()>=tau+4:
            selected.append((len(t['times']),row,i))
    selected=sorted(selected,key=lambda v:-v[0])[:4]
    rows=[]
    for _,row,i in selected:
        t=scan.tracks[i];q=t['rf_hz']/11.5e9
        y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][0]
        outputs={name:dict(cost=np.full(len(scan.norads),np.inf),phase=np.zeros(len(scan.norads)))
                 for name in ('original','RX1_step_from_other_family')}
        for phase in np.linspace(-15,15,61):
            geometry=prepare_phase_geometry(scan.sky,t['times'],np.full(len(scan.norads),phase))
            f,e,_=phase_linear_frequency(geometry,*latlon(x));visible=e.min(axis=1)>=0
            for name,output in outputs.items():
                corrected=y-(0 if name=='original' else step['additive_amplitude_hz']*(t['times']>=tau))
                terms=profile(corrected,q*f,*scan.white[i]);cost=np.where(visible,terms['cost'],np.inf)
                improved=cost<output['cost'];output['cost'][improved]=cost[improved];output['phase'][improved]=phase
        for name,output in outputs.items():
            corrected=y-(0 if name=='original' else step['additive_amplitude_hz']*(t['times']>=tau))
            candidates=[]
            for j in np.argsort(output['cost'])[:3]:
                bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],
                          velocity_km_s=scan.sky['velocity_km_s'][[j]])
                def calculate(phase):
                    geo=prepare_phase_geometry(bank,t['times'],np.array([phase]))
                    f,e,_=phase_linear_frequency(geo,*latlon(x))
                    terms=profile(corrected,q*f,*scan.white[i])
                    return terms,e
                seed=output['phase'][j]
                phase=golden(lambda v:float(calculate(v)[0]['cost'][0]),max(-15,seed-.5),min(15,seed+.5))
                terms,e=calculate(phase)
                candidates.append(dict(norad=int(scan.norads[j]),phase_s=phase,rms_hz=float(terms['rms'][0]),
                    bias_hz=float(terms['bias'][0]),cost=float(terms['cost'][0]),
                    residual_hz=terms['residual'][0],noise=noise_row(terms['innovations'],t['times']),
                    minimum_elevation_deg=float(e.min())))
            output.clear();output.update(candidates=candidates)
        rows.append(dict(component=t['key'],points=len(t['times']),times=t['times'],
                         original_nomination_norad=row['candidate_norad'],results=outputs))
        print('Other-family transfer',t['key'],[(k,v['candidates'][0]['rms_hz'],v['candidates'][0]['noise']) for k,v in outputs.items()],flush=True)
        write(OUT/('step_transfer'+('_fitted_c' if arm=='fitted_c' else '')+'_partial.json'),dict(rows=rows))
    write(OUT/('step_transfer'+('_fitted_c' if arm=='fitted_c' else '')+'.json'),dict(rows=rows,step_time_s=tau,arm=arm,
        amplitude_hz=step['additive_amplitude_hz'],target_family_never_used_to_choose_other_family_candidate=True,
        catalogue_candidates=len(scan.norads),GPS_used=False,future_TLE_used=False,
        independent_prediction_of_other_families=True,no_position_update=True))


def receiver_control():
    scan,old,node,_=context();steps=read(OUT/'shared_step.json');arms={}
    for arm in ARMS:
        p,x=build(arm);state=p.state(x);f,e=p.conditional_frequency(x);step=steps['arms'][arm]
        tau=step['selected_time_s'];rows=[]
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            t=scan.tracks[i];active=p.keep[sl]
            if t['receiver']!=2 or not active.any():continue
            times=t['times'][active]
            before=(times>=tau-12)&(times<tau);after=(times>=tau)&(times<=tau+12)
            if before.sum()<3 or after.sum()<3:continue
            q=t['rf_hz']/11.5e9
            y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][1]
            terms=profile(y[active],q*f[sl][active],*whitening(times))
            r=terms['residual'][0];corrected=r-step['additive_amplitude_hz']*(times>=tau)
            corrected-=corrected.mean()
            rows.append(dict(component=t['key'],norad=row['candidate_norad'],times=times,residual_hz=r,
                mean_jump_hz=float(r[after].mean()-r[before].mean()),
                pre_points=int(before.sum()),post_points=int(after.sum()),
                original_rms_hz=float(np.sqrt(np.mean(r*r))),
                imposed_RX1_step_rms_hz=float(np.sqrt(np.mean(corrected*corrected))),
                original_noise=noise_row(r,times),imposed_step_noise=noise_row(corrected,times)))
        arms[arm]=rows
    write(OUT/'RX2_controls.json',dict(arms=arms,step_time_and_amplitude_fixed_from_RX1_other_channels=True,
                                     independent_RX2_negative_control=True))


def summarize():
    import json
    scan,old,node,_=context();target=read(OUT/'target.json');step=read(OUT/'shared_step.json')
    training_keys={r['component'] for r in step['arms']['c0']['training']}
    training_ids={oid for t in scan.tracks if t['key'] in training_keys for oid in t['observation_ids']}
    assert len(training_ids)==170 and not training_ids.intersection(target['observation_ids'])
    assert len(target['times'])==82
    for arm in ARMS:
        assert step['arms'][arm]['target_profile_compatible']
        assert len(step['arms'][arm]['target_residual_hz'])==82
    for value in (-4.,0.,2.):
        assert abs(golden(lambda x:(x-value)**2,-10,10)-value)<1e-6
    screen=read(OUT/'screen.json');raw=read(OUT/'raw_evaluation.json');support=read(OUT/'event_support.json')
    after=sum(r['after'] for r in support['family_64923'].values())
    retained_after=sum(r['accepted_after'] for r in support['family_64923'].values())
    panel=np.load(OUT/'raw_panel.npz',allow_pickle=False)
    panel_metadata=json.loads(str(panel['metadata_json']));panel.close()
    summary=dict(case=CASE,target=read(OUT/'inventory.json')['target'],
        strongest_causal_candidate=dict(norad=64923,name='STARLINK-34643'),
        catalogue_candidates=screen['catalogue_candidates'],future_TLE_used=False,GPS_used_for_matching=False,
        known_cause_of_rejection='Initial ALGO01 post-salvage whole-track residual gates dropped the already nominated '
            '64923 curve. ALGO02 inherited that empty mask. The final frozen extension also fails structured-residual gates.',
        leading_model_explanation='An approximately 350–365 Hz shared frequency change near 108.5 s is absent from the '
            'constant/linear/smooth receiver model. An independent different-family RX1 track also improves when given this step.',
        family_points_after_event=after,family_points_after_event_retained=retained_after,
        original_native_GLRT_points_in_target=82,independent_training_points=170,
        independent_training_components=len(training_keys),training_and_target_ID_sets_disjoint=True,
        original_shared_frequency_RMS_hz={a:screen['arms'][a]['frozen']['profile_rms_hz'] for a in ARMS},
        step_predicted_target_RMS_hz={a:step['arms'][a]['target_rms_hz'] for a in ARMS},
        pilot_refined_plus_same_step_RMS_hz={a:raw['arms'][a]['shared_step_rms_hz'] for a in ARMS},
        one_amplitude_plus_searched_change_time=True,step_prior_sigma_hz=300,
        missing_negative_control='Only one original RX2 GLRT winner between 100 and 120 s; no retained RX2 track spans the event.',
        physical_source_not_identified='RX1 LNB/LO change versus common timing/reference disturbance is not resolved.',
        all_82_target_points_pass_existing_profile_association_screens_under_step_in_both_arms=True,
        full_pipeline_or_position_not_updated=True,no_claim_of_improved_position_accuracy=True,
        native_IQ=dict(points=panel_metadata['planned_points'],raw_windows_read=panel_metadata['raw_windows_read'],
                      export_seconds=panel_metadata['seconds'],new_RF_collection=False),
        input_sha256={name:sha(SOURCE/CASE/name) for name in (
            'algo02_result.json','result.json','tracks.json','observations.json','radio_noise.json','tracking.json')},
        tool_sha256={name:sha(ROOT/'tools'/name) for name in (
            'investigate_ds23_0268_longest_unassociated.py','plot_ds23_0268_longest_unassociated.py',
            'export_ds23_0268_longest_panel.py')})
    write(OUT/'summary.json',summary)
    print('All 82 target points retained; 170 independent training IDs; frozen ALGO02 unchanged.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=(
        'inventory','screen','diagnose','reenter','independent_correction','raw_refine','raw_evaluate','shared_step',
        'transfer_step','receiver_control','summarize'),required=True)
    parser.add_argument('--arm',choices=ARMS,default='c0')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.stage=='transfer_step':transfer_step(args.arm)
    else:globals()[args.stage]()
