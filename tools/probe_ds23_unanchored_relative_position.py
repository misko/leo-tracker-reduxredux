"""Bounded three-scan relative-only position experiment, without graph anchors."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_unanchored_relative_position import RelativeCurveProblem
from build_dsx01_orbit_modes import build_modes
from ds23_causal_phase_location import adjust_means
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import cached
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

INPUT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase/unanchored_relative_inputs'
OUT=ROOT/'reports/2026_10_22_ds23_unanchored_relative_position'
CASES=['DS23-0202','DS23-0274','DS23-0154']
VARIANTS=[('nominal_bias1000',False,1000.),('physical_bias1000',True,1000.),
    ('nominal_bias424',False,float(np.sqrt(2)*300)),('physical_bias424',True,float(np.sqrt(2)*300))]


def context(case,physical):
    scan,node,mask,powers,ordinary,hyper,entries,signed,signed_path=context_signed(case)
    inputs=read(INPUT/(case+'.json'));assert inputs['eligible']
    groups=inputs['groups'];labels=inputs['nominated_candidate_indices']
    widths,receipts=phase_widths(scan,labels);means=forecast_phase_mean(receipts,hyper['shrinkage'])
    if signed['accepted']:means=adjust_means(means,receipts,hyper,signed['selection'])
    owners={j:set() for j in labels}
    for group in groups:
        for role in ['first','second']:owners[group['nomination'][role+'_index']].add(tuple(group['lane'][:2]))
    supported=[j for j in labels if len(owners[j])>=2] if physical else []
    modes=None;metadata={}
    if supported:
        if not hasattr(scan,'previous_tle_path'):raise ValueError('explicit scan-local causal prior path required')
        modes,metadata=build_modes(scan,labels,supported,'physical')
    return scan,groups,labels,np.asarray(means),np.asarray(widths)*hyper['multiplier'],hyper,modes,supported,metadata,signed


def make(data,reference,bias_sigma):
    scan,groups,labels,means,widths,hyper,modes,supported,*_=data
    return RelativeCurveProblem(scan.sky,labels,groups,means,widths,reference,latlon,
        mode_bank=modes,supported=supported,nu=hyper['nu'],bias_sigma=bias_sigma)


def one(case,variant,physical,bias_sigma,output_dir=None):
    path=(OUT if output_dir is None else Path(output_dir))/(case+'_'+variant+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s unanchored relative-only fit cap')));signal.alarm(180)
    try:
        data=context(case,physical);scan,groups,labels,means,widths,hyper,modes,supported,metadata,signed=data
        x=np.zeros(2);reference=np.zeros(len(labels));history=[]
        for _ in range(5):
            p=make(data,reference,bias_sigma);cached(p);fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
            phase=np.clip(p.phases(x),-15,15);history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
        c=p.calculate(x);phases=p.phases(x);phase_valid=bool(np.max(abs(phases))<=15)
        raw,elevation,_=p.exact_residual(x) if phase_valid else (np.full(len(p.values),np.nan),np.full(len(p.values),-90.),phases)
        gates=[];begin=len(labels)+3*len(supported)
        for k,(group,sl) in enumerate(zip(groups,p.slices,strict=True)):
            noise={key:value[0] for key,value in batch_noise_screen(raw[sl][None],p.times[sl]).items()} if phase_valid else dict(noise_screen_pass=False)
            rms=float(np.sqrt(np.mean(raw[sl]**2))) if phase_valid else None;bias=float(bias_sigma*c['coefficient'][begin+k])
            passed=bool(phase_valid and rms<=450 and abs(bias)<=3000 and elevation[sl].min()>=0 and noise['noise_screen_pass'])
            gates.append(dict(group=group['group'],compatible=passed,RMS_hz=rms,bias_hz=bias,diagnostics=noise,
                first_norad=group['nomination']['first_norad'],second_norad=group['nomination']['second_norad'],points=sl.stop-sl.start))
        accepted=all(g['compatible'] for g in gates) and history[-1]['phase_change_s']<=.01
        result=dict(case=case,variant=variant,status='complete',accepted=accepted,
            endpoint_east_north_km=x,endpoint_latlon=latlon(x),negative_twice_elbo=c['negative_twice_elbo'],
            normalization_constant=c['normalization_constant'],RMS_hz=float(np.sqrt(np.mean(raw**2))) if phase_valid else None,
            phase_reference=p.reference,posterior_phases_s=phases,history=history,final_phase_change_s=history[-1]['phase_change_s'],
            gates=gates,coefficient=c['coefficient'],noise_precision=c['noise_precision'],
            labels=labels,means_s=means,phase_sigma_s=widths,physical_supported=supported,physical_mode_metadata=metadata,
            relative_groups=len(groups),relative_observations=len(p.values),bias_sigma_hz=bias_sigma,
            original_signed_incumbent=signed['policy_arms'],input_sha256=sha(INPUT/(case+'.json')),
            c0_and_fitted_c_identical_by_analytic_same_RX_same_RF_cancellation=True,
            standalone_relative_observation_model_not_combined_with_reused_GLRT=True,
            fixed_hypotheses_are_not_verified_satellite_identities=True,no_GPS_future_TLE_new_RF_or_new_IQ=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,variant=variant,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(case,variant,result['status'],result.get('accepted'),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,variants=VARIANTS,inputs_protocol_sha256=sha(INPUT/'protocol.json'),
        input_sha256={c:sha(INPUT/(c+'.json')) for c in CASES},
        no_original_active_graph_anchor_required=True,original_causal_signed_phase_priors=True,
        physical_modes='original three modes for families with two RF receiver/channel owners',
        bias_controls_hz=[1000.,float(np.sqrt(2)*300)],
        same_saved_RF_data_and_noise_for_all_variants=True,noise_Gamma_nu=4.,likelihood_power=1.,
        c0_and_fitted_c_exactly_equal_shared_radio_terms_cancel=True,
        original_mean_slope_curvature_step_ACF_and_horizon_gates=True,
        cold_start=[0,0],regional_width_km=25,phase_rounds=5,steps_per_round=48,
        per_fit_seconds=180,workers=6,no_GPS_future_TLE_new_RF_or_IQ=True,
        engineering_pilot_not_generalization_or_full_DS23=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_unanchored_relative_position.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('relative-only position protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c,*v) for c in CASES for v in VARIANTS])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,new_method_not_promoted=True))


if __name__=='__main__':main()
