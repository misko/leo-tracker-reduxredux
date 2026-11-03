"""Matched nonlinear-channel offsets, with an independent signed-prior factor."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_channel_calibration import make_channel_problem, attach_channel_predictive
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_ds23_frequency_events import parameters, cached, summary
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_channel_calibration'
PRIOR = ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'
COHORT = ROOT/'reports/2026_10_20_ds23_gate_retention_cohort'
ARMS = ('c0','fitted_c')


def prior_case(case):
    metadata = read(PRIOR/'evaluation_audit.json')['evidence'][case]
    path = ROOT/metadata['path']
    if sha(path) != metadata['sha256']:
        raise ValueError('signed-prior evidence changed')
    return read(path)


def fit_channel(scan,node,mask,arm,powers,means,hyper,entries,sigma):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_channel_problem(scan,node,mask,arm,reference,powers,means,hyper,sigma)
        attach_channel_predictive(p,entries,powers);cached(p)
        fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    r=summary(p,x,entries)
    r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
             channel_receipt=p.channel_receipt,channel_sigma_hz=sigma,
             channel_offsets_hz=(np.einsum('rck,k->rc',p.channel_lookup,p.state(x)['channel_amplitudes_hz']) if sigma else np.zeros((2,8))))
    return r


def select_policy(baseline, variants):
    eligible=[v for v in variants if v['paired_valid'] and
              baseline['c0']['negative_twice_elbo']-v['arms']['c0']['negative_twice_elbo']>2*np.log(2)]
    return min(eligible,key=lambda v:v['arms']['c0']['negative_twice_elbo']) if eligible else None


def initialize():
    destination=OUT/'protocol.json'
    if destination.exists():return read(destination)
    OUT.mkdir(parents=True,exist_ok=True)
    cohort=read(COHORT/'protocol.json')
    diagnostics=['DS23-0189','DS23-0344','DS23-0185','DS23-0157']
    cases=list(dict.fromkeys(cohort['cases']+diagnostics))
    protocol=dict(cases=cases,cohort=cohort['cases'],diagnostic_cases=diagnostics,
        matched_fixed_original_observations_masks_aliases_labels_and_weights=True,
        phase_mean_factors=['original','causally_qualified_signed'],channel_coefficient_prior_sigma_hz=[0,100,300],
        offset_modes_orthogonal_to_band_constant_and_linear_RF_on_active_curved_channels=True,
        at_least_three_curved_satellite_families_and_three_channels_per_enabled_RX_band=True,
        linear_tracks_never_calibrate=True,predictive_covariance_includes_new_modes=True,
        physical_orbit_phase_scales_tails_receiver_drifts_and_fragment_priors_unchanged=True,
        same_c_pair_observations_priors_and_5x48_search=True,cold_start_km=[0,0],box_width_km=25,
        no_gate_changes_no_constrained_rescue_no_point_trimming=True,
        RF_policy='paired gates; full normalized c0 bound gain > 2 log2 vs corresponding incumbent',
        GPS_used=False,future_TLE_used=False,workers=20,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_channel_calibration.py'))
    write(destination,protocol);return protocol


def run_case(case):
    destination=OUT/(case+'.json')
    if destination.exists():return dict(case=case,cached=True)
    started=time.monotonic();scan,node,mask,base,old=context(case)
    powers,ordinary,hyper=parameters(scan,base,old)
    signed=prior_case(case);entries=old['linear_entries'] if old['linear_paired_valid'] else []
    # Exact zero-mode replay precedes every new fit.
    null_differences=[]
    for arm in ARMS:
        r=old['policy_arms'][arm]
        p=make_channel_problem(scan,node,mask,arm,np.asarray(r['phase_reference']),powers,ordinary,hyper,0.)
        attach_channel_predictive(p,entries,powers)
        difference=p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']
        if abs(difference)>1e-3:raise ValueError('original RF objective replay mismatch')
        null_differences.append(float(difference))
    results={};policies={};chosen={}
    same=np.array_equal(ordinary,np.asarray(signed['means_s']))
    for factor,means,baseline in [('original',ordinary,old['policy_arms']),
                                  ('signed',np.asarray(signed['means_s']),signed['policy_arms'])]:
        variants=[]
        for sigma in (100.,300.):
            label=factor+'_'+str(int(sigma))
            if factor=='signed' and same:
                result=results['original_'+str(int(sigma))]
            else:
                arms={arm:fit_channel(scan,node,mask,arm,powers,means,hyper,entries,sigma) for arm in ARMS}
                result=dict(arms=arms,paired_valid=pair_passes(arms,include_linear=True),sigma_hz=sigma)
            results[label]=result;variants.append(result)
        selected=select_policy(baseline,variants)
        policies[factor]=baseline if selected is None else selected['arms']
        chosen[factor]=0 if selected is None else selected['sigma_hz']
    write(destination,dict(case=case,results=results,policies=policies,chosen_sigma_hz=chosen,
        baselines=dict(original=old['policy_arms'],signed=signed['policy_arms']),
        original_mask=mask,ordinary_means_s=ordinary,signed_means_s=signed['means_s'],
        original_RF_objective_replay_difference=null_differences,
        source_ALGO02_sha256=sha(SOURCE/case/'algo02_result.json'),GPS_used=False,future_TLE_used=False,
        seconds=time.monotonic()-started))
    receipt=dict(case=case,chosen=chosen,seconds=time.monotonic()-started)
    print(receipt,flush=True);return receipt


def main():
    protocol=initialize();results=[]
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures={executor.submit(run_case,c):c for c in protocol['cases']}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(completed=len(results),total=len(futures),results=results))
    write(OUT/'execution.json',dict(results=results,all_terminal=True))


if __name__=='__main__':main()
