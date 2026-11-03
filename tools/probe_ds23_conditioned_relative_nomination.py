"""GLRT-conditioned, IQ-disjoint reranking of frozen relative-pair proposals."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import copy
import signal
import time
import numpy as np

from ds23_conditioned_relative_nomination import refine_prediction,unresolved_curve_score
from ds23_causal_phase_location import adjust_means
from ds23_unanchored_relative_position import RelativeCurveProblem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_joint_relative_position import OUT as JOINT,INPUT,CASES,context,make
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=ROOT/'reports/2026_10_22_ds23_conditioned_relative_nomination'
POOL=INPUT.parent/'refined'


def baseline(case):
    path=JOINT if case in CASES else JOINT/'confirmation20'
    saved=read(path/(case+'_quarantined_GLRT.json'))
    if saved['status']!='complete':return None,saved
    d=context(case);return d,saved


def candidate_prior(d,p,cov,coefficient,group,candidate,means,widths):
    labels=[candidate['first_index'],candidate['second_index']]
    supported=[j for j in labels if j in p.supported]
    slots=[];mean=[];scales=widths[labels];begin=p.hardware.shape[1]+p.smooth.shape[1]
    for j in labels:
        index=begin+p.labels.index(j) if j in p.labels else None
        slots.append(index);mean.append(coefficient[index] if index is not None else means[j]/widths[j])
    for j in supported:
        first=begin+len(p.labels)+3*p.supported.index(j)
        slots.extend(range(first,first+3));mean.extend(coefficient[first:first+3])
    slots.append(None);mean.append(0.);matrix=np.eye(len(slots));used=[k for k,s in enumerate(slots) if s is not None]
    old=[slots[k] for k in used];matrix[np.ix_(used,used)]=cov[np.ix_(old,old)]
    mode_bank=dict(time_s=p.mode_bank['time_s'],position_km=np.zeros((6,*p.mode_bank['position_km'].shape[1:])),
        velocity_km_s=np.zeros((6,*p.mode_bank['velocity_km_s'].shape[1:])))
    for k,j in enumerate(labels):
        if j in p.supported:
            a=3*p.labels.index(j)
            for field in ['position_km','velocity_km_s']:mode_bank[field][3*k:3*k+3]=p.mode_bank[field][a:a+3]
    changed=copy.deepcopy(group);changed['nomination']=candidate
    rf=RelativeCurveProblem(d['scan'].sky,labels,[changed],means[labels],scales,np.asarray(mean[:2])*scales,d['coordinate'],
        mode_bank=mode_bank,supported=supported,nu=None,bias_sigma=np.sqrt(2)*300)
    return rf,np.asarray(mean),matrix,slots


def one(case):
    path=OUT/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s conditioned pair nomination cap')));signal.alarm(180)
    try:
        d,saved=baseline(case)
        if d is None:result=dict(case=case,status='no_offer',baseline_status=saved['status'],groups=[])
        else:
            scan=d['scan'];labels=list(range(len(scan.norads)));widths,receipts=phase_widths(scan,labels)
            means=forecast_phase_mean(receipts,d['model']['shrinkage'])
            if d['signed']['accepted']:means=adjust_means(means,receipts,d['model'],d['signed']['selection'])
            means=np.asarray(means);widths*=d['model']['multiplier'];arms={};proposals={}
            for arm,record in saved['arms'].items():
                p=make(d,arm,np.asarray(record['joint_phase_reference']),False,float(np.sqrt(2)*300))
                x=np.asarray(record['endpoint_east_north_km']);c=p.calculate(x);cov=np.linalg.inv(c['joint_calibration_precision'])
                groups=[]
                for group in d['groups']:
                    refined=read(POOL/(group['group']+'.json'));pool=refined['results']['regional_centre']['candidates']
                    values=np.array([r['second_value_hz']-r['first_value_hz'] for r in group['points']]);times=np.array([r['time_s'] for r in group['points']])
                    sigma=group['noise_sigma_hz']*np.sqrt(2)
                    null=unresolved_curve_score(times,values,sigma);rows=[]
                    for candidate in pool:
                        rf,mu,matrix,slots=candidate_prior(d,p,cov,c['coefficient'],group,candidate,means,widths)
                        fitted=refine_prediction(rf.values,lambda phase:rf.geometry(x,phase),mu,matrix,rf.phase_sigma,sigma)
                        noise={k:v[0] for k,v in batch_noise_screen(fitted['residual_hz'][None],times).items()}
                        bias=float(rf.bias_sigma*fitted['coefficient'][-1])
                        qualified=bool(fitted['phase_valid'] and fitted['phase_change_s']<=.01 and fitted['RMS_hz']<=450 and
                            abs(bias)<=3000 and fitted['minimum_elevation_deg']>=0 and noise['noise_screen_pass'])
                        rows.append(dict(first_index=candidate['first_index'],second_index=candidate['second_index'],
                            first_norad=candidate['first_norad'],second_norad=candidate['second_norad'],difference_alias=candidate['difference_alias'],
                            score=fitted['score'],model_prior_adjusted_score=fitted['score']+2*np.log(len(pool)),
                            qualified=qualified,bias_hz=bias,noise=noise,prediction=fitted,
                            prior_mean=mu,prior_covariance=matrix,old_calibration_slots=slots,
                            original_regional_score=candidate['score']))
                    rows.sort(key=lambda r:r['model_prior_adjusted_score'])
                    available=[r for r in rows if r['qualified']];best=available[0] if available else None
                    margin=null-best['model_prior_adjusted_score'] if best else None
                    gap=(available[1]['score']-best['score']) if len(available)>1 else None
                    groups.append(dict(group=group['group'],lane=group['lane'],null_score=null,candidates=rows,
                        best=best,margin_against_unresolved=margin,qualified_runner_up_gap=gap,
                        selected=bool(best is not None and margin>=2*np.log(20)),
                        original_pair=[group['nomination']['first_norad'],group['nomination']['second_norad']]))
                arms[arm]=dict(endpoint_east_north_km=x,groups=groups)
            result=dict(case=case,status='complete',arms=arms,quarantine_receipt=d['quarantine_receipt'],
                all_candidates_from_same_frozen_regional_pool=True,uncertain_GLRT_calibration_not_updated_by_RF=True,
                unseen_phase_Gaussian_moment_approximation_proposal_only=True,new_orbit_modes_not_added_to_proposals=True,
                original_hierarchical_priors_required_in_final_position_fit=True,reference_position_used=False,
                no_GPS_future_TLE_new_RF_or_IQ=True,input_sha256=sha(INPUT/(case+'.json')))
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);print(case,result['status'],result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);cases=CASES+read(JOINT/'confirmation20/protocol.json')['cases']
    protocol=dict(cases=cases,development_cases=CASES,workers=8,per_case_seconds=180,
        GLRT_only_quarantined_endpoints_and_shared_covariance=True,maximum_phase_rounds=5,
        same_frozen_regional_exact_candidate_pool=True,unseen_phase_priors_Gaussian_moment_approximation_only=True,
        new_candidate_orbit_modes_omitted_until_joint_support_qualified=True,
        relative_noise_unseen_Gamma_variance_factor=2,relative_constant_sigma_hz=float(np.sqrt(2)*300),
        unresolved_degree4_Legendre_coefficient_sigma_hz=float(PERIOD/np.sqrt(6)),
        null_prior_mass=.5,pair_total_prior_mass=.5,pair_prior_uniform_in_saved_pool=True,
        required_log_odds_against_null=float(np.log(20)),strict_variant_also_requires_arm_agreement_and_runner_up_gap=float(2*np.log(20)),
        original_inference_Gamma_Student_and_physical_priors_not_changed=True,
        no_GPS_future_TLE_new_RF_or_IQ=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_conditioned_relative_nomination.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('conditioned nomination protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in cases])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,no_position_gain_claim=True))


if __name__=='__main__':main()
