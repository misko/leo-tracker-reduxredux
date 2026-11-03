"""Restore original curved family companions together, retaining support gates."""

import argparse
import copy
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_refined_noise import learn_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_precision import OUT,precision_problem
from probe_ds23_refined_restoration import restoration_mask
from probe_ds23_refined_timestamps import apply_effective_times
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha


def family_mask(p,keep,selected_mask,original_mask):
    families={row['candidate_index'] for row,sl in zip(p.rows,p.slices,strict=True) if np.any(selected_mask[sl]&~keep[sl])}
    mask=keep.copy();restored=[]
    for row,sl in zip(p.rows,p.slices,strict=True):
        if row['candidate_index'] not in families:continue
        added=original_mask[sl]&~keep[sl]
        mask[sl]|=original_mask[sl]
        if added.any():restored.append(dict(track=row['component'],norad=row['candidate_norad'],added_points=int(added.sum())))
    return mask,restored


def run(case):
    scan=final_scan(case);raw=read(RAW/(case+'_tracks.json'));learned=read(LEARNED/(case+'.json'))
    primary=learned['results']['mean_and_distribution'];keep=np.array(primary['mask'],bool)
    original=read(SOURCE/case/'result.json');node=original['final_node'];model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    p=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,p.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    selected,_=restoration_mask(scan,p,keep,{r['point']['observation_id'] for r in raw['rows']})
    mask,restored=family_mask(p,keep,selected,np.array(original['final_mask'],bool))
    noise,radio=learn_noise(raw);modified=copy.deepcopy(scan);update_values(modified,raw['rows'],'joint_CFO_epoch_rate')
    offsets=apply_effective_times(modified,raw['rows']);results={}
    for name,factory in [('precise',precision_problem),('eccentric',eccentric_problem)]:
        arms={}
        for arm in ('c0','fitted_c'):
            reference=np.zeros(len(means));x=np.zeros(2);history=[]
            for _ in range(5):
                p=factory(modified,node,mask,arm,reference,powers,means,model,noise)
                r=fit(p,x,iterations=48);x=np.array(r['parameters']);history.append(r)
                reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
            c=p.calculate(x);tracks=[]
            for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                active=mask[sl]
                if active.any():tracks.append(dict(track=scan.tracks[i]['key'],norad=row['candidate_norad'],
                    time_s=modified.tracks[i]['times'][active],conditional_residual_hz=c['conditional_residual_hz'][sl][active]))
            arms[arm]=dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),state=p.state(x),history=history,
                negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][mask]**2))),
                gates=retained_metrics(p,x),phase_reference=reference,active_points=int(mask.sum()),tracks=tracks,
                eccentricity_receipts=getattr(p,'eccentricity_receipts',{}))
        failed={r['component'] for a in arms.values() for r in a['gates']['tracks'] if not r['compatible']}
        results[name]=dict(trial_arms=arms,paired_valid=not failed,failed_tracks=sorted(failed),reported_arms=arms if not failed else primary['arms'])
        write(OUT/(case+'_family_partial.json'),dict(case=case,results=results,restored=restored))
        print(case,'family',name,'new points',int(mask.sum()-keep.sum()),'failed',len(failed),flush=True)
    write(OUT/(case+'_family.json'),dict(case=case,results=results,restored=restored,mask=mask,
        original_mask=keep,radio_noise_receipts=radio,offsets_s=offsets,
        only_originally_accepted_curved_family_companions_restored=True,
        identities_aliases_support_gates_unchanged=True,no_original_point_removed=True,
        GPS_used=False,paired_c=True,source_sha256=sha(Path(__file__)),raw_sha256=sha(RAW/(case+'_tracks.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
