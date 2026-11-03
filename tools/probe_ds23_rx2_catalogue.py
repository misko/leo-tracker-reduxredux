"""Recheck the most measurement-affected family against the full causal bank."""

import argparse
import time
from pathlib import Path
import numpy as np
from ds23_correlated_family_screen import screen
from ds23_heteroscedastic_gates import metrics
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_timestamps import apply_effective_times
from probe_ds23_rx2_measurement_position import record
from prototype_dsx01_continuous_position import latlon
from remeasure_ds23_rx2_cohort import OUT
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha, final_scan
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency


def affected_family(p, keep, updates):
    scores={}
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        track=p.scan.tracks[i]
        if track['receiver']!=2:continue
        delta=np.array([updates.get(oid,0.) for oid in track['observation_ids']])
        scores.setdefault(row['candidate_index'],0.)
        scores[row['candidate_index']]+=float(np.sum((delta[keep[sl]]/p.point_noise[sl][keep[sl]])**2))
    if not scores:raise ValueError('active RX2 evidence required')
    return min(scores,key=lambda j:(-scores[j],j)),scores


def run(case):
    started=time.monotonic();directory=OUT/'catalogue';directory.mkdir(exist_ok=True)
    if (directory/(case+'.json')).exists():raise FileExistsError('preserve scientific result')
    scan=final_scan(case);node=read(SOURCE/case/'result.json')['final_node']
    raw=read(OUT/(case+'_refined.json'));saved=read(OUT/(case+'_refined_local_noise_five_orbit_position.json'))
    noise=saved['proposed_noise_by_id'];keep=np.array(saved['original_mask'],bool)
    model=read(LEARNED/(case+'.json'))['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    updates=update_values(scan,raw['rows'],'joint_CFO_epoch_rate');apply_effective_times(scan,raw['rows'])
    p=problem(scan,node,'c0',keep);source,scores=affected_family(p,keep,updates['changed_observation_ids_and_delta_hz'])
    all_members=[k for k,row in enumerate(p.rows) if row['candidate_index']==source]
    members=[k for k in all_members if keep[p.slices[k]].any()]
    incumbent=saved['trial_arms'];state=incumbent['c0']['state'];endpoint=np.array(incumbent['c0']['endpoint_east_north_km'])
    anchors=[np.zeros(2),endpoint]+[np.clip(endpoint+d,-12.5,12.5) for d in ([2,0],[-2,0],[0,2],[0,-2])]
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
    means=forecast_phase_mean(receipts,model['shrinkage']);widths=np.array(widths)*model['multiplier']
    occupied={row['candidate_index'] for row in p.rows if row['candidate_index']!=source}
    proposals={};screens=[]
    for ai,anchor in enumerate(anchors):
        f,e,d=phase_linear_frequency(scan.geometry,*latlon(anchor));curves=[]
        for k in members:
            i,sl=p.members[k],p.slices[k];track=scan.tracks[i];active=keep[sl]
            index,q=scan.index[i][active],track['rf_hz']/11.5e9
            y=track['values']-scan.hardware(track,np.array(state['beta']))-q*scan.rx_basis[i]@np.array(state['smooth'])[track['receiver']-1]
            sigma=np.array([noise.get(oid,v) for oid,v in zip(track['observation_ids'],p.point_noise[sl],strict=True)])[active]
            curves.append(dict(observed=y[active],predicted=q*(f[:,index]+d[:,index]*means[:,None]),
                derivative=q*d[:,index],sigma=sigma,power=powers[k],visible=np.min(e[:,index],axis=1)>=0))
        scored=screen(curves,widths,np.eye(len(curves))*300**2)
        order=[int(j) for j in np.argsort(scored['cost']) if np.isfinite(scored['cost'][j]) and j not in occupied]
        screens.append(dict(anchor=anchor,incumbent_rank=order.index(source)+1 if source in order else None,
            best=[dict(index=j,norad=int(scan.norads[j]),cost=float(scored['cost'][j])) for j in order[:8]]))
        for j in order[:4]:
            if j==source:continue
            aliases={k:int(a[j]) for k,a in zip(members,scored['aliases'],strict=True)}
            changes=[dict(row_index=k,candidate_index=j,alias=aliases.get(k,int(node['aliases'][k]))) for k in all_members]
            proposal=dict(index=j,norad=int(scan.norads[j]),cost=float(scored['cost'][j]),anchor_index=ai,changes=changes)
            if j not in proposals or proposal['cost']<proposals[j]['cost']:proposals[j]=proposal
    shortlist=sorted(proposals.values(),key=lambda r:r['cost'])[:4]
    plan=dict(case=case,source_index=int(source),source_norad=int(scan.norads[source]),
        RF_measurement_change_by_family=scores,catalogue_size=len(scan.norads),screens=screens,proposals=shortlist,
        baseline_sha256=sha(OUT/(case+'_refined_local_noise_five_orbit_position.json')),
        source_sha256=sha(Path(__file__)),mergers_excluded=True,source_selected_by_normalized_CFO_change_not_GPS=True,
        cheap_screen_uses_Gaussian_phase_and_omits_physical_orbit_modes=True)
    write(directory/(case+'_plan.json'),plan)
    trials=[dict(proposal=dict(index=int(source),norad=int(scan.norads[source]),changes=[]),
        arms=incumbent,paired_valid=saved['paired_valid'],reused_exact_baseline=True)]
    for proposal in shortlist:
        candidate=changed_node(scan,node,proposal['changes']);base=problem(scan,candidate,'c0',keep)
        _,prior_receipts=phase_widths(scan,base.labels);mu=forecast_phase_mean(prior_receipts,model['shrinkage']);arms={}
        for arm in ('c0','fitted_c'):
            reference=np.zeros(len(mu));x=np.zeros(2);history=[]
            for _ in range(5):
                trial=eccentric_problem(scan,candidate,keep,arm,reference,powers,mu,model,noise)
                fitted=fit(trial,x,iterations=48);x=np.array(fitted['parameters']);history.append(fitted)
                reference=np.clip(trial.state(x)['phases'][trial.labels],-15,15)
            arms[arm]=record(trial,x,history)
        valid=all(t['compatible'] for a in arms.values() for t in a['gates']['tracks'])
        trials.append(dict(proposal=proposal,arms=arms,paired_valid=valid))
        write(directory/(case+'_partial.json'),dict(case=case,trials=trials))
        print(case,'catalogue',proposal['norad'],'valid',valid,flush=True)
    eligible=[t for t in trials if t['paired_valid']]
    chosen=min(eligible,key=lambda t:t['arms']['c0']['negative_twice_elbo']) if eligible else None
    write(directory/(case+'.json'),dict(case=case,trials=trials,chosen=chosen,plan_sha256=sha(directory/(case+'_plan.json')),
        source_sha256=sha(Path(__file__)),seconds=time.monotonic()-started,no_GPS_used=True,
        all_original_points_preserved=True,selection_by_normalized_c0_RF_and_paired_gates=True,
        candidate_phase_means_recomputed_in_label_order=True,one_family_search_not_global_reassociation=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
