"""Same-budget support-control search ordered by added native points, not name."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import repair_ds23_iteration009_targets as repair
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'point_priority_support'


def rank_proposals(proposals):
    return sorted(proposals,key=lambda p:(len(p['additions']),-p['added_curved_points'],tuple(a['component'] for a in p['additions'])))[:2]


def one(case):
    repair.configure();d=repair.engine.current_setup(case)
    old=read(repair.OUT/(case+'_positions.json'));previous=read(repair.runner.RAW/'support_aware_reentry'/(case+'.json'))
    offered=[]
    for t in old['trials']:
        if t['paired_valid'] or len(t['additions'])>2:continue
        p=repair.engine.support.build(d,t['node'],np.asarray(t['mask'],bool),'c0',t['arms']['c0']['phase_reference'],np.asarray(t['means']))
        if p.disabled_new_one_owner_orbit_families:offered.append(t)
    selected=rank_proposals(offered);trials=[]
    for t in selected:
        reused=next((p for p in previous['trials'] if p['additions']==t['additions']),None)
        if reused:
            result=dict(reused,reused_original_control=True)
        else:
            arms={a:repair.engine.support.refit(d,t['node'],np.asarray(t['mask'],bool),a,np.asarray(t['means'])) for a in ['c0','fitted_c']}
            result=dict(t,arms=arms,paired_valid=bool(valid(arms)),reused_original_control=False)
        trials.append(result);print(case,result['added_curved_points'],'points valid',result['paired_valid'],'reused',result['reused_original_control'],flush=True)
    passing=[t for t in trials if t['paired_valid']]
    chosen=max(passing,key=lambda t:t['added_curved_points']) if passing else None
    write(OUT/(case+'.json'),dict(case=case,trials=trials,selected=chosen,
        exact_two_proposal_budget_unless_fewer_eligible=True,no_GPS_used=True,
        reused_original_candidate_points_priors_aliases_and_cold_fit_budget=True))
    return dict(case=case,status='complete',passing=len(passing))


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve priority experiment')
    write(OUT/'protocol.json',dict(cases=read(repair.runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        parent_support_source_sha256=sha(Path(repair.engine.support.__file__)),
        old_order='number of additions then lexical component key',
        new_order='number of additions, descending added native observations, lexical component tie break',
        maximum_proposals=2,all_other_fitting_priors_gates_and_5x48budget_unchanged=True,
        original_fitted_proposals_reused_exactly_when_in_both_policies=True,
        no_GPS_future_TLE_trimmed_points_or_new_RF=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
