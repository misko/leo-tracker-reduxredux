"""Bounded causal re-entry trials and report-side antenna visibility audit."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np

from investigate_ds23_0268_remaining_tracks import OUT as PREVIOUS,CASE,ARMS,load,fine_receiver_basis
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_ds23_frequency_events import parameters,refit,cached
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from ds23_frequency_events import make_event_problem,attach_event_predictive,extend_event_associations
from audit_ds23_algo01_coverage import coverage
from algo02_scan import pair_passes
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_0268_visibility_reentry'


def apply_nominations(scan,node,base,mask,additions,replacements):
    """Preserve old observations and update one satellite label per whole curve."""
    changed=copy.deepcopy(node);keep=np.asarray(mask,bool).copy();changes=[]
    for component,norad,alias in replacements:
        for k,row in enumerate(changed['seed']['rows']):
            if row['component']==component:
                changes.append(dict(component=component,previous_norad=row['candidate_norad'],norad=norad))
                row['candidate_norad']=norad;row['candidate_index']=int(np.flatnonzero(scan.norads==norad)[0])
                if alias is not None:changed['aliases'][k]=alias
    for key in additions:
        sl=next(sl for row,sl in zip(base.rows,base.slices,strict=True) if key in row['component']);keep[sl]=True
    return changed,keep,changes


def definitions():
    return dict(add_66797=(['RX1-CH4-T006','RX1-CH5-T005'],False,False),
        add_59342=(['RX2-CH5-T001'],False,False),add_63963=(['RX1-CH7-T003'],False,False),
        add_67953=(['RX1-CH2-T005'],False,False),add_64908=(['RX1-CH6-T004'],False,False),
        add_all=(['RX1-CH4-T006','RX1-CH5-T005','RX2-CH5-T001','RX1-CH7-T003','RX2-CH4-T001'],False,False),
        split_with_CH2=(['RX1-CH2-T005'],True,False),split_with_CH2_conservative=(['RX1-CH2-T005'],True,True),
        split_only=([],True,False))


def trial(name):
    output=OUT/'trials'/(name+'.json');output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():return dict(name=name,cached=True)
    scan,base,saved,cover,problems=load();old=context(CASE)[4]
    initial=read(PREVIOUS/'reentry/fine_kernel_CH7.json');additions,split,conservative=definitions()[name]
    proposals=read(PREVIOUS/'causal_refined.json')['arms']['c0'];replacements=[]
    for key in additions:
        row=next(r for r in proposals if key in r['component']);best=row['refined'][0]['best']
        replacements.append((row['component'],best['norad'],best['alias']))
    if split:
        for row in base.rows:
            if any(key in row['component'] for key in ('RX1-CH1-T005','RX1-CH5-T003')):
                replacements.append((row['component'],67953,None))
    node,mask,changes=apply_nominations(scan,initial['node'],base,initial['mask'],additions,replacements)
    changed=copy.copy(scan);changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    powers=np.asarray(saved['powers']).copy()
    if conservative:
        for k,row in enumerate(base.rows):
            if any(key in row['component'] for key in ('RX1-CH1-T005','RX1-CH5-T003')):powers[k]=.2
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']});_,receipts=phase_widths(scan,labels)
    hyper=old['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,hyper['shrinkage'])
    pair={arm:refit(changed,node,mask,arm,powers,means,hyper,saved['events'],old['linear_entries']) for arm in ARMS}
    result=dict(name=name,arms=pair,mask=mask,node=node,powers=powers,changes=changes,
        paired_valid=pair_passes(pair,include_linear=True),added_curved_points=int(mask.sum()-np.asarray(initial['mask'],bool).sum()),
        original_curved_and_predictive_points_retained=True,GPS_used=False,future_TLE_used=False,
        basis_spacing_s=10,basis_width_s=15,conservative_changed_family_powers=conservative,
        cold_start_km=[0,0],phase_rounds=5,position_steps_per_round=48)
    write(output,result);print(name,'valid',result['paired_valid'],'added',result['added_curved_points'],flush=True)
    return dict(name=name,paired_valid=result['paired_valid'],added_curved_points=result['added_curved_points'])


def trials():
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/'protocol.json',dict(case=CASE,trials=definitions(),goal_original_GLRT_percent=70,
        minimum_unique_original_GLRT_points=2216,GLRT_total=3165,
        all_original_gates_and_observations_retained=True,causal_TLE_only=True,
        no_GPS_selection=True,matched_c_masks_labels_aliases_other_priors_and_budgets=True,
        raw_scores_not_compared_across_different_masks_or_powers=True,
        starting_model_sha256=sha(PREVIOUS/'reentry/fine_kernel_CH7.json')))
    receipts=[]
    with ProcessPoolExecutor(max_workers=9) as executor:
        for future in as_completed([executor.submit(trial,name) for name in definitions()]):
            receipts.append(future.result());write(OUT/'trial_progress.json',dict(receipts=receipts))
    write(OUT/'trial_execution.json',dict(receipts=receipts,all_terminal=True))


def replay(record,arm):
    scan,base,saved,cover,problems=load();old=context(CASE)[4];changed=copy.copy(scan)
    changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    labels=sorted({r['candidate_index'] for r in record['node']['seed']['rows']});_,receipts=phase_widths(scan,labels)
    hyper=old['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,hyper['shrinkage'])
    powers=np.asarray(record.get('powers',saved['powers']));r=record['arms'][arm];x=np.asarray(r['endpoint_east_north_km'])
    p=make_event_problem(changed,record['node'],np.asarray(record['mask'],bool),arm,np.asarray(r['phase_reference']),powers,means,hyper,saved['events'])
    attach_event_predictive(p,old['linear_entries'],powers);cached(p)
    if abs(p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:raise ValueError('endpoint changed')
    return p,x


def audit_coverage():
    ids={r['observation_id'] for r in read(SOURCE/CASE/'observations.json')};rows=[]
    for path in sorted((OUT/'trials').glob('*.json')):
        record=read(path);arms={}
        for arm,r in record['arms'].items():
            p,x=replay(record,arm);extension=extend_event_associations(p,x,r['gates']);accepted={t['component']:t for t in extension['tracks']}
            for t in r['linear_gates']+r['gates']['tracks']:
                if t['compatible']:accepted[t['component']]=t
            arms[arm]=dict(**coverage(list(accepted.values()),p.scan.tracks,ids),accepted_rows=list(accepted.values()))
        rows.append(dict(name=path.stem,paired_valid=record['paired_valid'],arms=arms))
    write(OUT/'trial_coverage.json',dict(rows=rows));return rows


def constrained_trial(name,margin=0.):
    """Refine a cold RF proposal subject to the unchanged full-scan gates."""
    from ds23_feasible_position import feasible_fit
    from probe_algo03_feasible_recovery import gate_slacks
    from probe_ds23_frequency_events import summary
    prefix='interior_' if margin else 'feasible_'
    source=OUT/'trials'/(name+'.json');output=OUT/'trials'/(prefix+name+'.json')
    if output.exists():return dict(name=prefix+name,cached=True)
    previous=read(source);scan,base,saved,cover,problems=load();old=context(CASE)[4]
    changed=copy.copy(scan);changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    labels=sorted({r['candidate_index'] for r in previous['node']['seed']['rows']});_,receipts=phase_widths(scan,labels)
    hyper=old['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,hyper['shrinkage'])
    powers=np.asarray(previous['powers']);mask=np.asarray(previous['mask'],bool);entries=old['linear_entries'];pair={}
    for arm in ARMS:
        r=previous['arms'][arm];x=np.asarray(r['endpoint_east_north_km']);reference=np.asarray(r['phase_reference']);history=[]
        for epoch in range(5):
            p=make_event_problem(changed,previous['node'],mask,arm,reference,powers,means,hyper,saved['events'])
            attach_event_predictive(p,entries,powers);cached(p)
            result=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.asarray(list(gate_slacks(p,z,entries).values()))-margin,x,p.lower,p.upper,iterations=40)
            x=np.asarray(result['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(epoch=epoch,fit=result,phase_change_s=float(np.max(abs(phase-reference)))))
            reference=phase
        pair[arm]=summary(p,x,entries);pair[arm].update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
            minimum_gate_slack=min(gate_slacks(p,x,entries).values()))
    record=dict(previous,name=prefix+name,arms=pair,paired_valid=pair_passes(pair,include_linear=True),
        constrained_refinement=True,original_cold_proposal_sha256=sha(source),
        constrained_phase_rounds=5,constrained_position_iterations=40,gate_thresholds_unchanged=True,
        stricter_optimization_interior_slack=margin)
    write(output,record);print(record['name'],'valid',record['paired_valid'],flush=True)
    return dict(name=record['name'],paired_valid=record['paired_valid'])


def constrained():
    names=['add_66797','add_59342','add_64908','split_only','split_with_CH2','split_with_CH2_conservative']
    write(OUT/'constrained_protocol.json',dict(proposals=names,RF_and_gate_diagnostic_selection_only=True,
        retain_all_original_evidence=True,phase_rounds=5,iterations=40,initial_conditions='saved cold RF trials',
        optimize_RF_bound_subject_to_original_gates=True,GPS_used=False,future_TLE_used=False,
        boundary_solutions_are_not_a_generalization_claim=True))
    receipts=[]
    with ProcessPoolExecutor(max_workers=6) as executor:
        for f in as_completed([executor.submit(constrained_trial,name) for name in names]):
            receipts.append(f.result());write(OUT/'constrained_progress.json',dict(receipts=receipts))
    write(OUT/'constrained_execution.json',dict(receipts=receipts,all_terminal=True))


def identity_screen():
    """Whole-catalogue shared-phase proposals for the disputed receiver groups."""
    from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry,phase_linear_frequency
    from leo.analysis.research.retained_track_likelihood import profile
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from prototype_dsx01_continuous_position import latlon
    output=OUT/'identity_catalogue_screen.json'
    if output.exists():return
    record=read(OUT/'trials/feasible_add_66797.json');scan,base,saved,cover,problems=load()
    members=[i for row,i in zip(base.rows,base.members,strict=True) if row['candidate_norad'] in (53923,63901)]
    members=list(dict.fromkeys(members));times=np.unique(np.concatenate([scan.tracks[i]['times'] for i in members]))
    groups=dict(all_53923=[k for k,i in enumerate(members) if any(r['component']==scan.tracks[i]['key'] and r['candidate_norad']==53923 for r in base.rows)],
        RX1_53923=[k for k,i in enumerate(members) if scan.tracks[i]['receiver']==1 and any(r['component']==scan.tracks[i]['key'] and r['candidate_norad']==53923 for r in base.rows)],
        RX2_53923=[k for k,i in enumerate(members) if scan.tracks[i]['receiver']==2 and any(r['component']==scan.tracks[i]['key'] and r['candidate_norad']==53923 for r in base.rows)],
        family_63901=[k for k,i in enumerate(members) if any(r['component']==scan.tracks[i]['key'] and r['candidate_norad']==63901 for r in base.rows)])
    phases=np.linspace(-15,15,121);arrays={};frozen={}
    for arm in ARMS:
        p,x=replay(record,arm);state=p.state(x);observed=[]
        for i in members:
            t=scan.tracks[i];q=t['rf_hz']/11.5e9
            observed.append(t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1])
        frozen[arm]=(p,x,observed)
        arrays[arm]={key:np.empty((len(phases),len(scan.norads),len(members)),dtype=bool if key=='passing' else float)
                     for key in ('cost','rms','bias','passing')}
    for k,phase in enumerate(phases):
        geometry=prepare_phase_geometry(scan.sky,times,np.full(len(scan.norads),phase))
        for arm,(p,x,observed) in frozen.items():
            f,e,_=phase_linear_frequency(geometry,*latlon(x))
            for m,i in enumerate(members):
                t=scan.tracks[i];ix=np.searchsorted(times,t['times']);terms=profile(observed[m],t['rf_hz']/11.5e9*f[:,ix],*scan.white[i])
                noise=batch_noise_screen(terms['innovations'],t['times']);visible=e[:,ix].min(axis=1)>=0
                for key in ('rms','bias'):arrays[arm][key][k,:,m]=terms[key]
                arrays[arm]['cost'][k,:,m]=np.where(visible,terms['cost'],np.inf)
                arrays[arm]['passing'][k,:,m]=visible&(terms['rms']<=450)&(abs(terms['bias'])<=3000)&noise['noise_screen_pass']
        if (k+1)%30==0:print('identity catalogue phase',k+1,'/',len(phases),flush=True)
    results={}
    for arm,r in arrays.items():
        results[arm]={}
        for name,which in groups.items():
            score=r['cost'][:,:,which].sum(axis=2);best_phase=np.argmin(score,axis=0);best_score=score[best_phase,np.arange(len(scan.norads))]
            candidates=[]
            for j in np.argsort(best_score)[:6]:
                k=best_phase[j];candidates.append(dict(norad=int(scan.norads[j]),phase_s=phases[k],curve_score=best_score[j],
                    all_local_tracks_pass=bool(r['passing'][k,j,which].all()),members=[dict(component=scan.tracks[members[m]]['key'],
                        rms_hz=r['rms'][k,j,m],bias_hz=r['bias'][k,j,m],local_pass=bool(r['passing'][k,j,m])) for m in which]))
            results[arm][name]=candidates
    write(output,dict(arms=results,catalogue_candidates=len(scan.norads),phase_grid_s=phases,
        fixed_RF_endpoint_and_calibration=True,one_shared_phase_per_tested_group=True,
        nomination_only_no_new_orbit_modes_or_phase_prior_in_proposal_score=True,
        not_an_identity_truth_test=True,GPS_used=False,future_TLE_used=False))


def interior():
    write(OUT/'interior_protocol.json',dict(source='add_66797',minimum_original_gate_slack=.01,
        purpose='test a stricter 1% optimization interior instead of a boundary-only acceptance',
        original_acceptance_thresholds_unchanged=True,GPS_used=False))
    constrained_trial('add_66797',.01)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('trials','coverage','constrained','identity','interior'),required=True)
    args=parser.parse_args();dict(trials=trials,coverage=audit_coverage,constrained=constrained,identity=identity_screen,interior=interior)[args.stage]()
