"""Apply the incumbent's unchanged constrained refinement to the soft model."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import copy
import signal
import time
import numpy as np

import probe_ds23_soft_predictive_identity as study
from ds23_feasible_position import feasible_fit
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha


def one(case):
    path=study.OUT/'qualified_positions'/(case+'.json')
    if path.exists():return read(path)
    start=time.monotonic();original=read(study.OUT/'positions'/(case+'.json'));assert original['status']=='complete'
    result=copy.deepcopy(original);result['initial_position_sha256']=sha(study.OUT/'positions'/(case+'.json'));d=study.setup(case)
    result['constrained_refinement_attempted']=False;minima=[]
    if not original['paired_valid']:
        for arm,r in original['arms'].items():
            p=study.problem(d,arm,r['phase_reference'],'soft');x=np.asarray(r['endpoint_east_north_km'])
            minima.append(min(gate_slacks(p,x,d['entries']).values()))
        if min(minima)>=-.25:
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('remaining original600s soft identity budget exhausted')))
            signal.alarm(max(1,int(600-original['seconds'])))
            pair={};result['constrained_refinement_attempted']=True
            try:
                for arm,r in original['arms'].items():
                    x=np.asarray(r['endpoint_east_north_km']);reference=np.asarray(r['phase_reference']);history=[]
                    for _ in range(5):
                        p=study.problem(d,arm,reference,'soft')
                        fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                            lambda z:np.asarray(list(gate_slacks(p,z,d['entries']).values()))-.01,x,p.lower,p.upper,iterations=40)
                        x=np.asarray(fitted['parameters']);next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(next_phase-reference)))));reference=next_phase
                    c=p.calculate(x);entries=c.get('MAP_linear_entries',d['entries']);record=summary(p,x,entries)
                    record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],MAP_entries=entries,
                        minimum_gate_slack=min(gate_slacks(p,x,d['entries']).values()))
                    if d['entries']:
                        s=c['soft_identity'];record.update(identity_weights=s['weights'],identity_candidates=c['identity_candidates'],
                            EM_iterations=s['iterations'],EM_weight_change=s['final_weight_change'],EM_converged=s['converged'],
                            EM_objective_history=s['history'],identity_entropies=[float(-np.sum(w[w>0]*np.log(w[w>0]))) for w in s['weights']])
                    else:record['EM_converged']=True
                    pair[arm]=record
                result['arms']=pair
            except Exception as exc:
                result['constrained_error']=repr(exc)
            finally:signal.alarm(0)
    result['initial_gate_slacks']=minima
    result['paired_valid']=bool(valid(result['arms']) and all(r['EM_converged'] and r['final_phase_change_s']<=.01 for r in result['arms'].values()))
    result['policy_arms']=result['arms'] if result['paired_valid'] else result['incumbent_arms']
    result['c0_normalized_RF_gain']=result['incumbent_arms']['c0']['negative_twice_elbo']-result['arms']['c0']['negative_twice_elbo']
    result['lower_bound_policy_accepted']=result['paired_valid'] and result['c0_normalized_RF_gain']>0
    result['refinement_seconds']=time.monotonic()-start;write(path,result)
    print(case,'refinement',result['constrained_refinement_attempted'],'paired_valid',result['paired_valid'],flush=True);return result


def main():
    protocol=read(study.OUT/'protocol.json');cases=protocol['engineering']+protocol['random20']
    for cohort in ['engineering','random20']:assert read(study.OUT/(cohort+'_positions_execution.json'))['all_passed']
    (study.OUT/'qualified_positions').mkdir(exist_ok=True)
    write(study.OUT/'refinement_protocol.json',dict(cases=cases,
        reason='Match the previously published conditional-family fitter, which includes near-feasible constrained refinement',
        before_any_new_geographic_evaluation=True,original_unconstrained_outputs_preserved=True,
        original_minimum_slack_trigger=-.25,rounds=5,iterations=40,slack_margin=.01,
        remaining_original_per_case_600s_budget_only=True,priors_gates_points_and_both_c_arms_unchanged=True,
        source_sha256=sha(Path(__file__))))
    rows=[]
    with ProcessPoolExecutor(max_workers=24) as pool:
        for f in as_completed([pool.submit(one,c) for c in cases]):rows.append(f.result())
    write(study.OUT/'qualified_execution.json',dict(rows=[dict(case=r['case'],source_sha256=sha(study.OUT/'qualified_positions'/(r['case']+'.json'))) for r in rows],all_terminal=True,all_passed=True,no_geographic_evaluation_yet=True))


if __name__=='__main__':main()
