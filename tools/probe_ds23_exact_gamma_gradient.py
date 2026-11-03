"""Measure position-dependent Gaussian/Gamma approximation error, without GPS.

The older fixed-position importance audit did not test position gradients or
the shared linear predictive block. This diagnostic holds the original phase
reference fixed on a small local grid and integrates the same generalized
model. No new position is adopted from its local Newton prediction.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from ds23_exact_gamma_position import gaussian_blocks, linear_schur, integrate
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_21_ds23_exact_gamma_gradient'
BULK=Path('/srv/bulk/leo/research/ds23-exact-gamma-gradient-20261021')
CASES=['DS23-0202','DS23-0274','DS23-0293','DS23-0240','DS23-0112','DS23-0114','DS23-0289']
RULES=[dict(samples=512,seed=2026102108),dict(samples=2048,seed=2026102108),dict(samples=2048,seed=2026102109)]
STEP=.25


def prepare_point(context,arm,position):
    scan,node,mask,powers,means,hyper,entries,signed,_=context
    reference=np.array(signed['policy_arms'][arm]['phase_reference'])
    p=make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
    attach_event_predictive(p,entries,powers);c=p.calculate(position)
    features=c['features'];width=features.shape[1];begin=p.hardware.shape[1]+p.smooth.shape[1]
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    scale=np.ones(width);scale[-len(p.members):]=.3
    raw=p.values-p.q*c['intercept']-features@mean
    present,groups=np.unique(p.noise_groups[mask],return_inverse=True)
    blocks=gaussian_blocks(raw[mask],(features*scale)[mask],p.point_noise[mask],groups,powers[present])
    phase=np.arange(begin,begin+len(p.labels)) if hyper['nu'] is not None else np.array([],int)
    linear=None
    if entries:
        view,values,sigma,lg,_=linear_geometry(p,entries);geometry=geometry_features(view,position,0.)
        ly=values-view.q*geometry['intercept']-geometry['features']@mean
        linear=linear_schur(ly,geometry['features']*scale,sigma*np.sqrt(2),lg)
    return dict(blocks=blocks,noise_mean=c['noise_precision'][present],phase_indices=phase,
        phase_mean=c['coefficient_prior_precision'][phase],nu=hyper['nu'],linear=linear),dict(
        variational_joint_score=c['negative_twice_elbo'],
        variational_curved_score=c.get('curved_negative_twice_elbo',c['negative_twice_elbo']),
        coefficient=c['coefficient'],mean=mean,scale=scale,phase_sigma=p.phase_sigma,begin=begin,
        phase_count=len(p.labels),curved_points=int(mask.sum()),linear_points=sum(e['points'] for e in entries))


def derivatives(values):
    center=values[0,0];gradient=np.array([(values[1,0]-values[-1,0])/(2*STEP),(values[0,1]-values[0,-1])/(2*STEP)])
    hessian=np.diag([(values[1,0]+values[-1,0]-2*center)/STEP**2,(values[0,1]+values[0,-1]-2*center)/STEP**2])
    hessian[0,1]=hessian[1,0]=(values[1,1]-values[1,-1]-values[-1,1]+values[-1,-1])/(4*STEP**2)
    return gradient,hessian


def one(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('600-second exact-Gamma local-grid budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(600);result=dict(case=case)
    try:
        context=context_signed(case);arms={}
        for arm in ['c0','fitted_c']:
            anchor=np.array(context[-2]['policy_arms'][arm]['endpoint_east_north_km']);records=[]
            for ix in [-1,0,1]:
                for iy in [-1,0,1]:
                    position=anchor+STEP*np.array([ix,iy]);prepared,base=prepare_point(context,arm,position)
                    estimates=[]
                    for rule in RULES:
                        exact=integrate(**prepared,**rule);coefficient=base['mean']+base['scale']*exact.pop('curved_coefficient_mean')
                        phase_slice=slice(base['begin'],base['begin']+base['phase_count'])
                        phase_change=float(np.max(abs(coefficient[phase_slice]-base['coefficient'][phase_slice])*base['phase_sigma']))
                        estimates.append(dict(rule=rule,curved=exact['curved'],joint=exact['joint'],
                            maximum_exact_vs_VB_phase_change_s=phase_change,
                            joint_variational_gap=base['variational_joint_score']-exact['joint']['negative_twice_log_evidence'],
                            curved_variational_gap=base['variational_curved_score']-exact['curved']['negative_twice_log_evidence']))
                    records.append(dict(offset=[ix,iy],position=position,variational_joint_score=base['variational_joint_score'],
                        variational_curved_score=base['variational_curved_score'],estimates=estimates))
            vb={(r['offset'][0],r['offset'][1]):r['variational_joint_score'] for r in records};vg,vh=derivatives(vb)
            if np.linalg.eigvalsh(vh).min()<=0:raise ValueError('incumbent local variational Hessian is not positive definite')
            diagnostics=[]
            for k,rule in enumerate(RULES):
                scores={(r['offset'][0],r['offset'][1]):r['estimates'][k]['joint']['negative_twice_log_evidence'] for r in records}
                exact_gradient,exact_hessian=derivatives(scores);delta=-np.linalg.solve(vh,exact_gradient-vg)
                checks=[r['estimates'][k][kind] for r in records for kind in ['curved','joint']]
                diagnostics.append(dict(rule=rule,exact_joint_gradient=exact_gradient,exact_joint_hessian=exact_hessian,
                    predicted_position_change_from_gap_km=delta,predicted_change_norm_km=float(np.linalg.norm(delta)),
                    minimum_effective_sample_fraction=min(r['effective_samples']/rule['samples'] for r in checks),
                    maximum_single_importance_weight=max(r['maximum_normalized_weight'] for r in checks)))
            reliable=all(r['minimum_effective_sample_fraction']>=.1 and r['maximum_single_importance_weight']<.05 for r in diagnostics[1:])
            seed_change=float(np.linalg.norm(diagnostics[1]['predicted_position_change_from_gap_km']-diagnostics[2]['predicted_position_change_from_gap_km']))
            arms[arm]=dict(anchor_east_north_km=anchor,records=records,variational_gradient=vg,variational_hessian=vh,
                diagnostics=diagnostics,importance_reliable=reliable,independent_seed_predicted_change_disagreement_km=seed_change,
                no_position_refit_or_adoption=True,phase_reference_held_at_incumbent=True,
                curved_points=base['curved_points'],linear_points=base['linear_points'])
            print(case,arm,'predicted change',[round(r['predicted_change_norm_km'],4) for r in diagnostics],
                'reliable',reliable,'seed agreement',round(seed_change,4),flush=True)
        result.update(status='complete',arms=arms,incumbent_sha256=sha(context[-1]))
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,step_km=STEP,grid='3x3 around each incumbent RF mode',integration_rules=RULES,
        phase_reference_fixed_for_gradient_diagnosis=True,workers=7,per_case_seconds=600,
        identical_observations_labels_aliases_physical_priors_and_curved_powers=True,
        same_independent_Gaussian_linear_noise_and300Hz_bias_priors=True,
        linear_data_never_update_returned_curved_calibration_moments=True,
        exact_means_Gaussian_modes_integrated_analytically_Gamma_integrals_estimated=True,
        generalized_evidence_not_calibrated_probability=True,
        no_GPS_new_RF_future_TLE_or_position_adoption=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_exact_gamma_position.py',
            ROOT/'tools/probe_ds23_marginal_evidence.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('exact-Gamma gradient protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=7) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,c) for c in CASES])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],protocol_sha256=sha(path),
        no_position_error_or_truth_used=True,no_new_position_accuracy_claim=True))


if __name__=='__main__':main()
