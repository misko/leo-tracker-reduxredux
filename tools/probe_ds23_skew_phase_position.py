"""Paired cold position fits: asymmetric prior and matched scalar-optimizer null."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
import numpy as np
from scipy.optimize import minimize

from algo02_scan import pair_passes
from ds23_skew_phase_problem import make_skew_problem,attach_skew_predictive
from probe_ds23_skew_phase_prior import OUT as QUALIFICATION
from probe_ds23_frequency_events import parameters,cached,summary
from probe_algo03_frame_peak_recovery import context,SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_skew_phase_position'
ARMS=('c0','fitted_c')


def refit(scan,node,mask,arm,powers,means,model,entries,kappa):
    x=np.zeros(2);reference=np.zeros(len(means));history=[]
    for _ in range(5):
        p=make_skew_problem(scan,node,mask,arm,reference,powers,means,model,kappa)
        attach_skew_predictive(p,entries,powers);cached(p)
        start_score=p.calculate(x)['negative_twice_elbo']
        fitted=minimize(lambda z:p.calculate(z)['negative_twice_elbo']-start_score,x,
            method='L-BFGS-B',bounds=list(zip(p.lower,p.upper,strict=True)),
            options=dict(maxiter=48,ftol=1e-10,gtol=1e-5,eps=1e-3,maxls=20))
        x=np.asarray(fitted.x);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(parameters=x,phase_change_s=float(np.max(abs(phase-reference))),
            iterations=int(fitted.nit),evaluations=int(fitted.nfev),optimizer_success=bool(fitted.success),
            optimizer_message=str(fitted.message)))
        reference=phase
    c=p.calculate(x);r=summary(p,x,entries)
    r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],kappa=kappa,
        skew_solver_change=c['final_log_precision_change'],skew_solver_iterations=c['precision_iterations'],
        skew_solver_qualified=bool(c['final_log_precision_change']<1e-4))
    return r


def initialize():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    OUT.mkdir(parents=True,exist_ok=True)
    cohort=read(QUALIFICATION/'protocol.json')
    original=read(ROOT/'reports/2026_10_20_ds23_channel_calibration/protocol.json')
    p=dict(cases=cohort['cases'],cohort=original['cohort'],diagnostic_cases=original['diagnostic_cases'],
        qualification_sha256=sha(QUALIFICATION/'protocol.json'),
        raw_GLRT_graph_labels_aliases_masks_noise_and_weights_frozen=True,
        no_new_receiver_or_orbit_coordinates=True,phase_mode_variance_and_nu_preserved=True,
        kappa_learned_only_from_pre_scan_all_catalogue_TLEs=True,
        two_controls=['published original ALGO02','same scalar optimizer and symmetric prior'],
        scalar_optimizer='L-BFGS-B on normalized negative2ELBO; eps1e-3 km; max48; maxls20',
        reason_for_scalar_control='a different residual-vector decomposition must not be mistaken for a prior improvement',
        independent_phase_refresh_rounds=5,cold_start_km=[0,0],box_width_km=25,
        variance_updates=256,skew_solver_gate=1e-4,original_other_gates_unchanged=True,
        invalid_trials_fall_back_to_original_ALGO02=True,unqualified_prior_is_exact_original_policy=True,
        no_point_trimming_or_gate_driven_position_rescue=True,GPS_used=False,future_TLE_used=False,
        workers=20,source_sha256=sha(Path(__file__)),
        bound_sha256=sha(ROOT/'tools/ds23_skew_bound.py'),
        problem_sha256=sha(ROOT/'tools/ds23_skew_phase_problem.py'))
    write(path,p);return p


def run_case(case):
    path=OUT/(case+'.json')
    if path.exists():return dict(case=case,cached=True)
    selected=read(QUALIFICATION/(case+'.json'));start=time.monotonic()
    old=read(SOURCE/case/'algo02_result.json');baseline=old['policy_arms']
    if not selected['selection']['qualified']:
        write(path,dict(case=case,qualified=False,baseline_arms=baseline,
            scalar_policy_arms=baseline,skew_policy_arms=baseline,GPS_used=False,future_TLE_used=False))
        return dict(case=case,qualified=False)
    scan,node,mask,base,old=context(case);powers,means,model=parameters(scan,base,old)
    assert selected['base_model']==model
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    differences=[]
    for arm in ARMS:
        r=baseline[arm]
        p=make_skew_problem(scan,node,mask,arm,np.asarray(r['phase_reference']),powers,means,model,0.)
        attach_skew_predictive(p,entries,powers)
        difference=p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']
        if abs(difference)>1e-3:raise ValueError('symmetric null replay mismatch')
        differences.append(float(difference))
    results={};policies={};valid={}
    for name,kappa in [('scalar',0.),('skew',selected['selection']['kappa'])]:
        arms={a:refit(scan,node,mask,a,powers,means,model,entries,kappa) for a in ARMS}
        qualifies=pair_passes(arms,include_linear=True) and all(r['skew_solver_qualified'] for r in arms.values())
        results[name]=arms;policies[name]=arms if qualifies else baseline;valid[name]=qualifies
    write(path,dict(case=case,qualified=True,selection=selected['selection'],results=results,
        paired_valid=valid,baseline_arms=baseline,scalar_policy_arms=policies['scalar'],skew_policy_arms=policies['skew'],
        original_mask=mask,null_RF_differences=differences,GPS_used=False,future_TLE_used=False,
        seconds=time.monotonic()-start))
    receipt=dict(case=case,paired_valid=valid,seconds=time.monotonic()-start)
    print(receipt,flush=True);return receipt


def main():
    p=initialize();results=[]
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures={executor.submit(run_case,case):case for case in p['cases']}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(completed=len(results),total=len(futures),results=results))
    write(OUT/'execution.json',dict(results=results,all_terminal=True))


if __name__=='__main__':main()
