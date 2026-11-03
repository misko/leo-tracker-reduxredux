"""Re-screen the newly active precise family against the complete causal bank."""

import argparse
import copy
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_family_screen import screen_family
from ds23_refined_noise import learn_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_precision import OUT as PRECISE
from probe_ds23_refined_timestamps import apply_effective_times
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

OUT=ROOT/'reports/2026_10_19_ds23_refined_catalogue'


def context(case,companion=False):
    scan=final_scan(case);node=read(SOURCE/case/'result.json')['final_node']
    data=read(RAW/(case+'_tracks.json'))
    if companion:
        other=read(RAW/(case+'_companion.json'));data=copy.deepcopy(data)
        data['rows']+=other['rows'];data['panel_metadata']['tracks']+=other['panel_metadata']['tracks']
    learned=read(LEARNED/(case+'.json'));model=learned['hyperparameters_from_pre_RF_TLE_only']
    incumbent=read(PRECISE/(case+'_family.json'));keep=np.array(incumbent['mask'],bool)
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    noise,radio=learn_noise(data);update_values(scan,data['rows'],'joint_CFO_epoch_rate');offsets=apply_effective_times(scan,data['rows'])
    return scan,node,keep,powers,noise,radio,model,incumbent,offsets


def refit(scan,node,keep,powers,noise,model,arm,rounds=5,steps=48):
    base=problem(scan,node,arm,keep);_,receipt=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage']);reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(rounds):
        p=eccentric_problem(scan,node,keep,arm,reference,powers,means,model,noise)
        r=fit(p,x,iterations=steps);x=np.array(r['parameters']);history.append(r)
        reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    c=p.calculate(x);tracks=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=keep[sl]
        if not active.any():continue
        tracks.append(dict(track=scan.tracks[i]['key'],norad=row['candidate_norad'],time_s=scan.tracks[i]['times'][active],
            sigma_hz=p.point_noise[sl][active],conditional_residual_hz=c['conditional_residual_hz'][sl][active],
            noise_precision=float(c['noise_precision'][p.members.index(i)])))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
        negative_twice_elbo=c['negative_twice_elbo'],active_points=int(keep.sum()),phase_reference=reference,
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),gates=retained_metrics(p,x),tracks=tracks)


def run(case,companion=False):
    OUT.mkdir(parents=True,exist_ok=True);name=case+('_companion' if companion else '')
    scan,node,keep,powers,noise,radio,model,old,offsets=context(case,companion)
    incumbent=old['results']['eccentric']['trial_arms']['c0'];p=problem(scan,node,'c0',keep)
    sources=sorted({r['norad'] for r in old['restored']})
    if len(sources)!=1:raise ValueError('one newly reentered whole family required for this bounded diagnostic')
    source=int(np.flatnonzero(scan.norads==sources[0])[0]);members=[k for k,r in enumerate(p.rows) if r['candidate_index']==source]
    endpoint=np.array(incumbent['endpoint_east_north_km']);state=incumbent['state']
    anchors=[np.zeros(2),endpoint]+[np.clip(endpoint+d,-12.5,12.5) for d in ([2,0],[-2,0],[0,2],[0,-2])]
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
    means=forecast_phase_mean(receipts,model['shrinkage']);widths=np.array(widths)*model['multiplier']
    proposals={};screens=[]
    for ai,anchor in enumerate(anchors):
        frequency,elevation,derivative=phase_linear_frequency(scan.geometry,*latlon(anchor));curves=[]
        for k in members:
            i,sl=p.members[k],p.slices[k];tr=scan.tracks[i];active=keep[sl];index=scan.index[i][active];q=tr['rf_hz']/11.5e9
            y=tr['values']-scan.hardware(tr,np.array(state['beta']))-q*scan.rx_basis[i]@np.array(state['smooth'])[tr['receiver']-1]
            sigma=np.array([noise.get(o,s) for o,s in zip(tr['observation_ids'],p.point_noise[sl],strict=True)])[active]
            curves.append(dict(observed=y[active],predicted=q*(frequency[:,index]+derivative[:,index]*means[:,None]),
                derivative=q*derivative[:,index],sigma=sigma,power=powers[k],visible=np.min(elevation[:,index],axis=1)>=0))
        screen=screen_family(curves,widths);order=[int(j) for j in np.argsort(screen['cost']) if np.isfinite(screen['cost'][j])]
        screens.append(dict(anchor=anchor,top=[dict(index=j,norad=int(scan.norads[j]),cost=float(screen['cost'][j]),phase_s=float(screen['phase_correction_s'][j]+means[j])) for j in order[:20]],
            finite_candidates=len(order),incumbent_rank=order.index(source)+1 if source in order else None))
        for j in order[:6]+[source]:
            changes=[dict(row_index=k,candidate_index=j,alias=int(a[j])) for k,a in zip(members,screen['aliases'],strict=True)]
            candidate=dict(index=j,norad=int(scan.norads[j]),cost=float(screen['cost'][j]),anchor=ai,changes=changes)
            if j not in proposals or candidate['cost']<proposals[j]['cost']:proposals[j]=candidate
    selected=sorted(proposals.values(),key=lambda r:r['cost'])[:6]
    if not any(r['index']==source for r in selected):selected.append(proposals[source])
    # Do not merge into another active family: that changes unrelated family support.
    occupied={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if keep[sl].any() and r['candidate_index']!=source}
    trials=[]
    for proposal in selected:
        if proposal['index'] in occupied:
            trials.append(dict(proposal=proposal,skipped='already-active family; merge requires separate diagnostic'));continue
        candidate=changed_node(scan,node,proposal['changes'])
        arms={a:refit(scan,candidate,keep,powers,noise,model,a) for a in ('c0','fitted_c')}
        valid=all(t['compatible'] for a in arms.values() for t in a['gates']['tracks'])
        trials.append(dict(proposal=proposal,arms=arms,paired_valid=valid))
        write(OUT/(name+'_partial.json'),dict(case=case,trials=trials,screens=screens))
        print(name,'NORAD',proposal['norad'],'paired valid',valid,flush=True)
    valid=[r for r in trials if r.get('paired_valid')]
    chosen=min(valid,key=lambda r:r['arms']['c0']['negative_twice_elbo']) if valid else None
    write(OUT/(name+'.json'),dict(case=case,companion_refined=companion,source_norad=sources[0],
        catalogue_size=len(scan.norads),screens=screens,trials=trials,chosen=chosen,radio_noise_receipts=radio,
        mask=keep,powers=powers,offsets_s=offsets,GPS_used=False,paired_c=True,
        same_observations_other_priors_and_budgets_for_all_identity_trials=True,
        final_fits_cold_start_at_regional_center=True,screening_is_approximate_not_exhaustive_fitting=True,
        source_sha256=sha(Path(__file__)),screen_source_sha256=sha(ROOT/'tools/ds23_family_screen.py'),
        input_refinement_sha256=sha(RAW/(case+'_tracks.json')),
        companion_sha256=sha(RAW/(case+'_companion.json')) if companion else None))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--companion',action='store_true');args=parser.parse_args();run(args.case,args.companion)
