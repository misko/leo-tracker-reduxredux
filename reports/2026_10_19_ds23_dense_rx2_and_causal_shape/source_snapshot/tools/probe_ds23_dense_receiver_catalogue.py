"""Repeat causal identity competition after dense RX2 remeasurement."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_causal_shape_distribution import OUT as DISTRIBUTION
from ds23_heteroscedastic_gates import metrics
from ds23_measurement_noise import learn_local_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_history_shape_prior import distribution_problem
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_receiver_positions import merge_measurements
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE
from probe_ds23_refined_precision import OUT as PRECISE
from probe_ds23_refined_timestamps import apply_effective_times
from refine_ds23_receiver_panel import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha
from prototype_dsx01_continuous_position import latlon


def run(case,mode):
    old=copy.deepcopy(read(RAW/(case+'_tracks.json')));extra=read(RAW/(case+'_companion.json'))
    old['rows']+=extra['rows'];old['panel_metadata']['tracks']+=extra['panel_metadata']['tracks']
    data=merge_measurements(old,read(OUT/(case+'_broad_refined.json')));noise,_=learn_local_noise(data)
    scan=final_scan(case);original_node=read(SOURCE/case/'result.json')['final_node']
    catalogue=read(CATALOGUE/(case+'_companion.json'));baseline=catalogue['chosen'];keep=np.array(read(PRECISE/(case+'_family.json'))['mask'],bool)
    model=read(LEARNED/(case+'.json'))['hyperparameters_from_pre_RF_TLE_only'];powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    distribution=read(DISTRIBUTION/(case+'.json'))['selection'];update_values(scan,data['rows'],'joint_CFO_epoch_rate');apply_effective_times(scan,data['rows'])
    audited=read(OUT/(case+'_heteroscedastic_gates.json'))['results'][mode];trials=[]
    for proposal in sorted([r for r in catalogue['trials'] if 'arms' in r],key=lambda r:r['arms']['c0']['negative_twice_elbo']):
        arms={};candidate=changed_node(scan,original_node,proposal['proposal']['changes'])
        if proposal['proposal']['norad']==baseline['proposal']['norad']:
            for arm,r in audited['arms'].items():
                arms[arm]=dict(r['fit'],heteroscedastic_gates=r['heteroscedastic_gates'],validated_reused_fit=True)
        else:
            for arm in ('c0','fitted_c'):
                base=problem(scan,candidate,arm,keep);_,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
                reference=np.zeros(len(means));x=np.zeros(2);history=[]
                for _ in range(5):
                    p=(eccentric_problem(scan,candidate,keep,arm,reference,powers,means,model,noise) if mode=='local_noise'
                       else distribution_problem(scan,candidate,keep,arm,reference,powers,means,model,noise,distribution,'trained'))
                    r=fit(p,x,iterations=48);x=np.array(r['parameters']);history.append(r)
                    reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
                c=p.calculate(x);tracks=[]
                for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                    active=keep[sl]
                    if active.any():tracks.append(dict(track=scan.tracks[i]['key'],norad=row['candidate_norad'],time_s=scan.tracks[i]['times'][active],
                        sigma_hz=p.point_noise[sl][active],conditional_residual_hz=c['conditional_residual_hz'][sl][active]))
                arms[arm]=dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
                    phase_reference=reference,negative_twice_elbo=c['negative_twice_elbo'],active_points=int(keep.sum()),
                    heteroscedastic_gates=metrics(p,x),tracks=tracks,RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))))
        valid=all(t['compatible'] for a in arms.values() for t in a['heteroscedastic_gates']['tracks'])
        trials.append(dict(proposal=proposal['proposal'],arms=arms,paired_valid=valid))
        write(OUT/(case+'_'+mode+'_catalogue_partial.json'),dict(case=case,trials=trials))
        print(case,mode,'dense NORAD',proposal['proposal']['norad'],'valid',valid,flush=True)
    valid=[r for r in trials if r['paired_valid']];chosen=min(valid,key=lambda r:r['arms']['c0']['negative_twice_elbo']) if valid else None
    write(OUT/(case+'_'+mode+'_catalogue.json'),dict(case=case,mode=mode,trials=trials,chosen=chosen,
        source_sha256=sha(Path(__file__)),full_refined_sha256=sha(OUT/(case+'_broad_refined.json')),
        prior_catalogue_sha256=sha(CATALOGUE/(case+'_companion.json')),audited_fit_sha256=sha(OUT/(case+'_heteroscedastic_gates.json')),
        all_six_old_RF_shortlist_identities_retested=True,new_prior_full_catalogue_rescreen_not_claimed=True,
        GPS_used=False,paired_c=True,original_masks_points_and_aliases_preserved_except_declared_candidate_changes=True,
        final_fits_five_phase_rounds_48_steps_regional_center=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--mode',choices=['local_noise','local_noise_causal_shape'],required=True);args=parser.parse_args();run(args.case,args.mode)
