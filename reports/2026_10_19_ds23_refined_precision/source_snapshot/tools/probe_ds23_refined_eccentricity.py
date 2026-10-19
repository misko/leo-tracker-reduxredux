"""Test the two missing physical eccentricity directions with precise CFOs."""

import argparse
import copy
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_refined_noise import learn_noise
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from dsx01_structured_joint import eccentricity_bank
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_receiver_smooth_prior import scale_posterior
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_precision import OUT,precision_problem
from probe_ds23_refined_restoration import restoration_mask
from probe_ds23_refined_timestamps import apply_effective_times
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def extra_columns(labels,q,modes,supported):
    labels,q,modes=np.asarray(labels),np.asarray(q),np.asarray(modes)
    if q.shape!=labels.shape or modes.shape!=(len(q),2):raise ValueError('two physical modes per matching observation required')
    extra=np.zeros((len(q),2*len(supported)))
    for k,j in enumerate(supported):
        use=labels==j;extra[use,2*k:2*k+2]=q[use,None]*modes[use]
    return extra


def eccentric_problem(scan,node,keep,arm,reference,powers,means,model,noise):
    p=precision_problem(scan,node,keep,arm,reference,powers,means,model,noise)
    bank,metadata=eccentricity_bank(scan,p.labels,p.supported)
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    def calculate(x):
        c=JointMarginal.calculate(p,x)
        modes=paired_frequency_modes(p.sky,bank,p.flat_times,p.flat_labels,p.reference,*latlon(x[:2]))
        extra=extra_columns(p.flat_labels,p.q,modes,p.supported_local)
        stop=c['features'].shape[1]-len(p.members)
        f=np.column_stack((c['features'][:,:stop],extra,c['features'][:,stop:]));width=f.shape[1]
        mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
        prior=np.full(width,-1,int)
        if model['nu'] is not None:prior[begin:begin+len(p.labels)]=np.arange(len(p.labels))
        scales=np.ones(width);scales[-len(p.members):]=.3;present=np.unique(p.noise_groups[keep])
        raw=p.values-p.q*c['intercept']-f@mean
        b=hierarchical_bound(raw[keep],(f*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=None if model['nu'] is None else prior,
            prior_nu=4 if model['nu'] is None else model['nu'])
        b=scale_posterior(b,scales);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-f@b['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep])))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)];c.update(b,features=f)
        return c
    p.calculate=calculate;p.eccentricity_receipts=metadata
    return p


def run(case):
    raw=read(RAW/(case+'_tracks.json'));scan=final_scan(case);learned=read(LEARNED/(case+'.json'))
    primary=learned['results']['mean_and_distribution'];original=np.array(primary['mask'],bool)
    node=read(SOURCE/case/'result.json')['final_node'];model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    base=problem(scan,node,'c0',original);_,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    keep,restored=restoration_mask(scan,base,original,{r['point']['observation_id'] for r in raw['rows']})
    noise,radio=learn_noise(raw);modified=copy.deepcopy(scan);update_values(modified,raw['rows'],'joint_CFO_epoch_rate')
    offsets=apply_effective_times(modified,raw['rows']);arms={}
    for arm in ('c0','fitted_c'):
        reference=np.zeros(len(means));x=np.zeros(2);history=[]
        for _ in range(5):
            p=eccentric_problem(modified,node,keep,arm,reference,powers,means,model,noise)
            result=fit(p,x,iterations=48);x=np.array(result['parameters']);history.append(result)
            reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
        c=p.calculate(x);tracks=[]
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            active=keep[sl]
            if not active.any():continue
            tracks.append(dict(track=scan.tracks[i]['key'],norad=row['candidate_norad'],
                time_s=modified.tracks[i]['times'][active],conditional_residual_hz=c['conditional_residual_hz'][sl][active]))
        arms[arm]=dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),state=p.state(x),history=history,
            negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
            gates=retained_metrics(p,x),phase_reference=reference,active_points=int(keep.sum()),tracks=tracks,
            eccentricity_receipts=p.eccentricity_receipts)
        print(case,'eccentric',arm,'fit finished',flush=True)
    failed={r['component'] for a in arms.values() for r in a['gates']['tracks'] if not r['compatible']}
    write(OUT/(case+'_eccentric.json'),dict(case=case,trial_arms=arms,paired_valid=not failed,failed_tracks=sorted(failed),
        reported_arms=arms if not failed else primary['arms'],restored=restored,mask=keep,
        offsets_s=offsets,radio_noise_receipts=radio,source_sha256=sha(Path(__file__)),
        raw_sha256=sha(RAW/(case+'_tracks.json')),causal_eccentricity_source_sha256=sha(ROOT/'tools/dsx01_structured_joint.py'),
        GPS_used=False,paired_c=True,no_original_point_removed=True,
        two_additional_shared_physical_modes_per_supported_family=True,
        eccentricity_scales_from_latest_and_previous_causal_TLE_only=True))
    print(case,'eccentric paired valid',not failed,'failed',len(failed),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
