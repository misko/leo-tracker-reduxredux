"""Existing near-feasible gate-constrained solver on frozen primary HMM paths."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import numpy as np

import probe_ds23_iteration010_paths as binding
from ds23_feasible_position import feasible_fit
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import summary
from audit_ds23_algo01_coverage import retained_metrics
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=binding.runner.RAW/'temporal_feasibility'


def eligible(primary,minima):
    return bool('arms' in primary and not primary['accepted'] and not primary['paired_valid'] and min(minima)>=-.25)


def refine(d,kind,arm,saved):
    reference=np.asarray(saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);history=[]
    for _ in range(5):
        p=binding.paths.build(d,kind,arm,reference)
        fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
            lambda z:np.asarray(list(gate_slacks(p,z,d['entries']).values()))-.01,x,p.lower,p.upper,iterations=40)
        x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
    result=summary(p,x,d['entries']);result.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
        minimum_gate_slack=min(gate_slacks(p,x,d['entries']).values()))
    delta=p.calculate(x)['negative_twice_elbo']-result['negative_twice_elbo']
    assert_curved_gate_replay(result['gates'],retained_metrics(p,x))
    result['independent_gate_replay_objective_difference']=delta
    if abs(delta)>1e-5:raise ValueError('constrained path endpoint changed')
    return result


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s bounded temporal feasibility cap')));signal.alarm(360)
    binding.configure();source=read(binding.OUT/(case+'.json'));primary=source['methods']['persistent5s'];minima=[]
    if 'arms' not in primary:
        write(OUT/(case+'.json'),dict(case=case,eligible=False,accepted=False,reason='no primary cold fit'));return dict(case=case,status='complete')
    d,cov,kind,_=binding.paths.parent(case);selected=read(binding.OUT/(case+'_persistent5s_selection.json'))['selected']
    basis=binding.paths.native.receiver_basis(d['scan']);scan,entries=binding.paths.native.append_native_paths(d['scan'],d['entries'],selected,basis);changed=dict(d,scan=scan,entries=entries)
    for arm,saved in primary['arms'].items():
        p=binding.paths.build(changed,kind,arm,saved['phase_reference']);minima.append(min(gate_slacks(p,np.asarray(saved['endpoint_east_north_km']),entries).values()))
    if not eligible(primary,minima):
        write(OUT/(case+'.json'),dict(case=case,eligible=False,accepted=False,initial_minimum_slacks=minima,reason='primary already accepted or outside original bounded near-feasible trigger'))
        return dict(case=case,status='complete',eligible=False)
    arms={a:refine(changed,kind,a,s) for a,s in primary['arms'].items()};coverage={a:binding.paths.coverage(changed,kind,a,s) for a,s in arms.items()}
    kept={a:set(cov[a]['accepted_observation_ids'])<=set(coverage[a]['accepted_observation_ids']) for a in arms}
    accepted=bool(valid(arms) and all(s['final_phase_change_s']<=.01 for s in arms.values()) and all(kept.values()))
    write(OUT/(case+'.json'),dict(case=case,eligible=True,initial_minimum_slacks=minima,arms=arms,coverage=coverage,
        paired_valid=bool(valid(arms)),accepted=accepted,all_parent_accepted_IDs_preserved=kept,selected_paths=selected,
        original_unconstrained_result_sha256=sha(binding.OUT/(case+'.json')),new_points=primary['new_points'],
        original_nodes_aliases_observations_priors_and_all_gate_thresholds_unchanged=True))
    print(case,'constrained primary',accepted,flush=True);signal.alarm(0);return dict(case=case,status='complete',eligible=True,accepted=accepted)


def main():
    binding.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve constrained temporal experiment')
    assert read(binding.OUT/'execution.json')['all_terminal']
    write(OUT/'protocol.json',dict(cases=read(binding.runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        solver_sha256=sha(Path(feasible_fit.__code__.co_filename)),primary_only='persistent5s',
        original_cold_HMM_proposal_IDs_and_all_original_parent_observations_frozen=True,
        trigger='failed both-arm qualification with each normalized gate slack >= -0.25',
        near_feasible_trigger_reused_from_existing_curve_fit_configuration=True,
        refinement5phase_rounds40steps_each_both_c_arms_matched=True,numerical_margin=.01,
        acceptance='all original gates, phase convergence and every parent accepted ID retained',
        no_GPS_future_TLE_new_RF_threshold_relaxation_or_point_pruning=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
