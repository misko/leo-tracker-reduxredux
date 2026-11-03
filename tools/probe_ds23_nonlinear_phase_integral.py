"""Local phase-nonlinearity diagnosis on fixed causal DS23 observations."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_nonlinear_phase_integral import ConditionalPhaseIntegral,phase_frequency_samples,summarize_log_ratio
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_nonlinear_phase_integral'
BULK=Path('/srv/bulk/leo/research/ds23-nonlinear-phase-integral-20261021')
COHORT=ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json'
CASES=['DS23-0268','DS23-0405']+read(COHORT)['pilot_cases']
RULES=[dict(samples=512,seed=2026102191),dict(samples=2048,seed=2026102191),dict(samples=2048,seed=2026102192)]
STEP=.25


def prepare_point(context,arm,position):
    scan,node,keep,powers,means,hyper,entries,signed,_=context
    reference=np.asarray(signed['policy_arms'][arm]['phase_reference'])
    p=make_event_problem(scan,node,keep,arm,reference,powers,means,hyper,[])
    c=p.calculate(position);features=c['features'];begin=p.hardware.shape[1]+p.smooth.shape[1]
    indices=np.arange(begin,begin+len(p.labels));mean=np.zeros(features.shape[1]);mean[indices]=means/p.phase_sigma
    raw=p.values-p.q*c['intercept']-features@mean;groups=p.noise_groups[keep]
    weight=powers[groups]*c['noise_precision'][groups]/p.point_noise[keep]**2
    design=features[keep];precision=c['coefficient_prior_precision']
    curved=ConditionalPhaseIntegral(raw[keep],design,weight,precision,indices)
    difference=float(max(abs(curved.conditional_mean-(c['coefficient']-mean))))
    if difference>1e-6:raise ValueError('curved Gaussian posterior fails existing coefficient replay')
    models={'curved':curved};metadata={}
    times=p.flat_times[keep];labels=p.flat_labels[keep];q=p.q[keep];intercept=c['intercept'][keep]
    phase_feature=features[keep][:,indices]
    metadata['curved']=dict(times=times,labels=labels,q=q,intercept=intercept,phase_feature=phase_feature)
    if entries:
        view,values,sigma,lg,_=linear_geometry(p,entries);geometry=geometry_features(view,position,0.)
        ly=values-view.q*geometry['intercept']-geometry['features']@mean
        biases=np.eye(int(max(lg))+1)[lg]*300.;width=biases.shape[1]
        u=np.r_[np.column_stack((design,np.zeros((len(design),width)))),np.column_stack((geometry['features'],biases))]
        y=np.r_[raw[keep],ly];w=np.r_[weight,1/(2*sigma**2)]
        joint=ConditionalPhaseIntegral(y,u,w,np.r_[precision,np.ones(width)],indices)
        models['joint']=joint
        metadata['joint']=dict(times=np.r_[times,view.flat_times],labels=np.r_[labels,view.flat_labels],
            q=np.r_[q,view.q],intercept=np.r_[intercept,geometry['intercept']],phase_feature=u[:,indices])
        attach_event_predictive(p,entries,powers);full=p.calculate(position)
    else:
        models['joint']=curved;metadata['joint']=metadata['curved'];full=c
    return models,metadata,dict(p=p,phase_prior_mean=mean[indices],phase_sigma=p.phase_sigma,
        coefficient_replay_difference=difference,variational_joint_score=full['negative_twice_elbo'],
        variational_curved_score=c['negative_twice_elbo'],curved_points=int(keep.sum()),
        predictive_points=sum(e['points'] for e in entries))


def correct(problem,metadata,base,position,rule):
    draws=problem.draws(**rule);phase=(draws+base['phase_prior_mean'])*base['phase_sigma']
    records=[];rms=[];mean_delta=np.zeros(len(problem.raw));maximum=0.
    for start in range(0,len(draws),64):
        stop=min(start+64,len(draws));physical=phase_frequency_samples(base['p'].sky,metadata['times'],metadata['labels'],
            phase[start:stop],*latlon(position))
        exact=metadata['q'][None,:]*(physical-metadata['intercept'][None,:])
        linear=(draws[start:stop]+base['phase_prior_mean'])@metadata['phase_feature'].T
        delta=exact-linear;records.extend(problem.log_ratio(draws[start:stop],delta))
        rms.extend(np.sqrt(np.mean(delta**2,axis=1)));mean_delta+=delta.sum(axis=0)
        maximum=max(maximum,float(max(abs(delta).ravel())))
    result=summarize_log_ratio(records);result.update(rule=rule,
        RMS_of_sample_mean_nonlinear_remainder_hz=float(np.sqrt(np.mean((mean_delta/len(draws))**2))),
        median_sample_RMS_nonlinear_remainder_hz=float(np.median(rms)),maximum_sample_remainder_hz=maximum,
        posterior_phase_marginal_used_for_scoring_only=True)
    return result


def derivatives(scores):
    center=scores[0,0]
    gradient=np.array([(scores[1,0]-scores[-1,0])/(2*STEP),(scores[0,1]-scores[0,-1])/(2*STEP)])
    hessian=np.diag([(scores[1,0]+scores[-1,0]-2*center)/STEP**2,
        (scores[0,1]+scores[0,-1]-2*center)/STEP**2])
    hessian[0,1]=hessian[1,0]=(scores[1,1]-scores[1,-1]-scores[-1,1]+scores[-1,-1])/(4*STEP**2)
    return gradient,hessian


def one(case):
    path=BULK/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('240second bounded nonlinear phase diagnostic cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
    try:
        context=context_signed(case);arms={}
        for arm in ['c0','fitted_c']:
            anchor=np.asarray(context[-2]['policy_arms'][arm]['endpoint_east_north_km']);records=[]
            for ix in [-1,0,1]:
                for iy in [-1,0,1]:
                    position=anchor+STEP*np.array([ix,iy]);models,metadata,base=prepare_point(context,arm,position)
                    estimates=[]
                    for rule in RULES:
                        estimates.append({kind:correct(models[kind],metadata[kind],base,position,rule) for kind in ['curved','joint']})
                    records.append(dict(offset=[ix,iy],position=position,
                        variational_joint_score=base['variational_joint_score'],variational_curved_score=base['variational_curved_score'],
                        estimates=estimates,coefficient_replay_difference=base['coefficient_replay_difference']))
            values={(r['offset'][0],r['offset'][1]):r['variational_joint_score'] for r in records}
            gradient,hessian=derivatives(values);positive=bool(min(np.linalg.eigvalsh(hessian))>0);diagnostics=[]
            for k,rule in enumerate(RULES):
                values={(r['offset'][0],r['offset'][1]):r['estimates'][k]['joint']['negative_twice_log_evidence_correction'] for r in records}
                dg,dh=derivatives(values);change=-np.linalg.solve(hessian,dg) if positive else None
                diagnostics.append(dict(rule=rule,correction_gradient=dg,correction_hessian=dh,
                    predicted_local_shift_km=change,predicted_local_shift_norm_km=None if change is None else float(np.linalg.norm(change)),
                    minimum_effective_sample_fraction=min(r['estimates'][k][kind]['effective_sample_fraction'] for r in records for kind in ['curved','joint']),
                    maximum_single_weight=max(r['estimates'][k][kind]['maximum_normalized_weight'] for r in records for kind in ['curved','joint'])))
            arms[arm]=dict(anchor=anchor,records=records,diagnostics=diagnostics,original_joint_gradient=gradient,
                original_joint_hessian=hessian,original_hessian_positive=positive,
                independent_seed_shift_difference_km=None if not positive else float(np.linalg.norm(
                    diagnostics[1]['predicted_local_shift_km']-diagnostics[2]['predicted_local_shift_km'])),
                no_position_refit_or_adoption=True,curved_phase_reference_held_fixed=True,
                predictive_data_never_update_curved_calibration_moments=True)
            print(case,arm,[d['predicted_local_shift_norm_km'] for d in diagnostics],flush=True)
        result=dict(case=case,status='complete',arms=arms,incumbent_sha256=sha(context[-1]))
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,engineering_cases=CASES[:2],preexisting_random_pilots=CASES[2:],cohort_sha256=sha(COHORT),
        step_km=STEP,local_grid='3x3 around current RF-selected endpoint; no evaluation coordinate',rules=RULES,
        workers=5,per_case_seconds=240,
        exact_nonlinear_nominal_phase_Doppler_same_causal_bank=True,
        frozen_Gamma_precisions_at_each_original_VB_point=True,physical_shape_design_conditioned_at_existing_phase_reference=True,
        other_Gaussian_modes_integrated_analytically=True,curved_and_joint_predictive_evidence_compared=True,
        joint_phase_draws_only_score_evidence_and_never_update_curved_calibration=True,
        same_observations_labels_aliases_priors_and_c0_fitted_c=True,
        local_Newton_shift_is_diagnostic_not_a_new_regional_position_estimate=True,
        no_GPS_future_TLE_new_RF_or_position_adoption=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_nonlinear_phase_integral.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen nonlinear phase diagnostic changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,case) for case in CASES])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),
        no_position_error_or_truth_used=True,no_new_position_estimate_adopted=True))


if __name__=='__main__':main()
