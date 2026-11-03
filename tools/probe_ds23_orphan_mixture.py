"""Bounded all-orphan predictive evidence; inference never reads evaluation GPS."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

import numpy as np

import run_ds23_dbg01_iteration_004 as context
from ds23_height_problem import geometry_features
from ds23_orphan_predictive_mixture import OrphanPrediction,orphan_rows,geometry_view,PERIOD
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha,ROOT

OUT=context.RAW/'orphan_mixture'
SEEDS=(2026102204,2026102217)


def curve_geometry_null(d,p,x):
    c=p.calculate(x);observations={o['observation_id']:o for o in d['observations']};examples=[]
    for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        use=np.flatnonzero(p.keep[sl])
        if len(use):
            q=int(use[len(use)//2]);oid=p.scan.tracks[i]['observation_ids'][q]
            examples.append((observations[oid],r['candidate_index'],sl.start+q))
    view,active,*_=geometry_view(p,[o for o,_,_ in examples]);g=geometry_features(view,x,0.)
    stop=p.event_start-len(p.members);differences=[]
    for k,(_,candidate,index) in enumerate(examples):
        row=active.index(candidate)*len(examples)+k
        differences.append(np.max(abs(g['features'][row,:stop]-c['features'][index,:stop])))
        differences.append(abs(g['intercept'][row]-c['intercept'][index]))
    maximum=float(max(differences))
    if maximum>1e-7:raise ValueError('orphan virtual geometry differs from original curved geometry')
    return dict(maximum_geometry_difference=maximum,original_curved_rows_tested=len(examples))


def qualify(case):
    began=time.monotonic();d=context.engine.current_setup(case);observations=orphan_rows(d);records=[]
    for arm in ['c0','fitted_c']:
        saved=d['arms'][arm];p=context.engine.baseline.build(d,arm,saved['phase_reference'])
        x=np.asarray(saved['endpoint_east_north_km']);null=curve_geometry_null(d,p,x)
        coefficient=p.calculate(x)['coefficient'].copy()
        for bias in [0.,300.]:
            trials=[]
            for seed in SEEDS:
                prediction=OrphanPrediction(p,observations,d['powers'],seed=seed,draw_power=10,nodes=64,bias_sigma_hz=bias)
                ratios=prediction.ratios(x);result=prediction.calculate(x,details=True)
                from ds23_orphan_predictive_mixture import integrated_clutter
                finer=integrated_clutter(ratios,nodes=128)
                result.update(seed=seed,quadrature64_to128_difference=abs(result['relative_negative_twice_log_likelihood']-finer['relative_negative_twice_log_likelihood']))
                trials.append(result)
            delta=abs(trials[0]['relative_negative_twice_log_likelihood']-trials[1]['relative_negative_twice_log_likelihood'])
            stable=bool(delta<=.5 and all(r['effective_nuisance_draws']>=32 and r['quadrature64_to128_difference']<=.05 for r in trials))
            records.append(dict(arm=arm,bias_sigma_hz=bias,trials=trials,seed_loss_difference=delta,
                                qualified_for_position_fit=stable,geometry_null=null))
            print(case,arm,bias,'orphan evidence',[r['relative_negative_twice_log_likelihood'] for r in trials],
                  'ESS',[r['effective_nuisance_draws'] for r in trials],'qualified',stable,flush=True)
        np.testing.assert_array_equal(coefficient,p.calculate(x)['coefficient'])
    record=dict(case=case,status='complete',orphan_observation_ids=[o['observation_id'] for o in observations],
        points=len(observations),rows=records,seconds=time.monotonic()-began,
        all_orphan_points_used_no_residual_based_selection=True,
        active_family_candidates_inferred_by_existing_pipeline_not_verified_identities=True,
        original_curved_calibration_coefficients_unchanged=True,no_GPS_or_following_TLE=True)
    write(OUT/(case+'_qualification.json'),record);return dict(case=case,status='complete')


def fit_one(job):
    case,bias,seed=job;began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180second orphan paired-fit cap')));signal.alarm(180)
    path=OUT/(case+f'_bias{int(bias)}_seed{seed}_fit.json')
    if path.exists():raise FileExistsError('preserve frozen orphan fit')
    try:
        d=context.engine.current_setup(case);observations=orphan_rows(d);pair={}
        for arm in ['c0','fitted_c']:
            reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
            for _ in range(5):
                p=context.engine.baseline.build(d,arm,reference)
                prediction=OrphanPrediction(p,observations,d['powers'],seed=seed,draw_power=8,nodes=32,bias_sigma_hz=bias)
                original_residual=p.residual
                # Wrapped signal/clutter ratio is bounded by this positive
                # density ceiling; padding makes least-squares residual real.
                maximum=1+3*PERIOD/(np.sqrt(2*np.pi)*prediction.noise.min())
                padding=2*len(observations)*np.log(maximum)+1
                def residual(z):
                    cost=prediction.calculate(z)['relative_negative_twice_log_likelihood']
                    return np.r_[original_residual(z),np.sqrt(padding+cost)]
                p.residual=residual
                fitted=fit(p,x,iterations=24);x=np.asarray(fitted['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                history.append(dict(fit=fitted,phase_change_s=float(max(abs(phase-reference)))))
                reference=phase
            r=summary(p,x,d['entries']);r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
                orphan_evidence=prediction.calculate(x,details=True))
            r['combined_negative_twice_objective']=r['negative_twice_elbo']+r['orphan_evidence']['relative_negative_twice_log_likelihood']
            pair[arm]=r
        result=dict(case=case,bias_sigma_hz=bias,seed=seed,status='complete',arms=pair,
            paired_valid=bool(valid(pair) and all(r['final_phase_change_s']<=.01 for r in pair.values())),
            no_orphan_point_updates_curved_calibration_normal_equations=True,
            all_original_curved_and_predictive_points_retained=True,seconds=time.monotonic()-began)
    except Exception as exc:
        import traceback
        result=dict(case=case,bias_sigma_hz=bias,seed=seed,status='failed',error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0)
    write(path,result);return {k:result[k] for k in ['case','bias_sigma_hz','seed','status']}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    record=dict(cases=read(context.RAW/'protocol.json')['cases'],
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_orphan_predictive_mixture.py'),
        all_and_only_original_winning_points_outside_every_graph_track=True,
        conditional_candidates='all original active curved families; no manually supplied IDs or GPS-dependent catalogue',
        signal='equal mixture of visible inferred-family wrapped Gaussian CFO densities',
        clutter='uniform on one227272.727Hz CFO alias period',
        signal_fraction='one scan-wide Uniform(0,1), marginalized by Gauss-Legendre quadrature',
        calibration='joint conditional Gaussian from curved Gamma precisions, shared across all points; no feedback into curved equations',
        extra_constants='one per family/RX/channel/RF; zero control or existing300Hz Gaussian scale, shared across scan',
        qualification=dict(seeds=list(SEEDS),draws=1024,quadrature_nodes=64,control_nodes=128,
            maximum_loss_difference=.5,minimum_effective_nuisance_draws=32,maximum_quadrature_difference=.05),
        fit_only_qualified_both_c_arms=True,
        fit_budget=dict(draws=256,nodes=32,phase_rounds=5,steps=24,regional_start=[0,0],paired_seconds=180),
        after_fit='no adoption without independent higher-draw seed and quadrature stability checks and original both-arm gates',
        no_geographic_scoring_until_RF_results_frozen=True,no_new_RF_IQ_or_stationary_pooling=True)
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen orphan protocol')
    else:write(path,record)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['qualify','fit'],required=True)
    args=parser.parse_args();context.configure();record=prepare()
    if args.stage=='qualify':jobs=record['cases'];function=qualify
    else:
        jobs=[];function=fit_one
        for case in record['cases']:
            rows=read(OUT/(case+'_qualification.json'))['rows']
            for bias in [0.,300.]:
                if all(r['qualified_for_position_fit'] for r in rows if r['bias_sigma_hz']==bias):
                    jobs.extend((case,bias,seed) for seed in SEEDS)
    rows=[]
    with ProcessPoolExecutor(max_workers=min(4,max(1,len(jobs)))) as pool:
        for future in as_completed([pool.submit(function,j) for j in jobs]):rows.append(future.result())
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
