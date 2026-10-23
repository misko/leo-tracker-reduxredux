"""Reuse the published paired-positive RF guard before native temporal recovery."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration015_recovery as binding
import probe_ds23_paired_replacement_evidence as guard
from run_algo01_ds23_sample import read,write,sha

runner=binding.runner;paths=binding.paths.paths
OUT=runner.RAW/'paired_guard_parent'
PATHS=OUT/'paths'
ORIGINAL_PARENT=paths.parent


def use_guard(choice):
    return bool(choice['accepted']['published_c0_positive'] and not choice['accepted']['paired_positive'])


def parent(case):
    original,cov,kind,t=ORIGINAL_PARENT(case);frozen=read(OUT/'RF_selection.json');choice=next(r for r in frozen['rows'] if r['case']==case)
    if not choice['use_guard']:return original,cov,kind,t
    current=runner.engine.current_setup(case);source=guard.SOURCE/(case+'.json')
    if sha(source)!=choice['source_sha256']:raise ValueError('published guard input changed')
    saved=read(source)
    if not np.array_equal(original['keep'],current['keep']):raise ValueError('do not discard a new graph calibration to restore the guard')
    changed=dict(current,node=saved['baseline_node'],entries=saved['baseline_entries'],means=np.asarray(saved['baseline_means']),arms=saved['baseline_arms'])
    changed['base']=runner.engine.baseline.build(changed,'c0',changed['arms']['c0']['phase_reference'])
    changed['original_protected']={r['candidate_index'] for r,sl in zip(changed['base'].rows,changed['base'].slices,strict=True) if changed['keep'][sl].any()}|{e['candidate_index'] for e in changed['entries']}
    coverage={a:runner.engine.baseline.inventory(changed,a) for a in changed['arms']}
    if any(set(coverage[a]['accepted_observation_ids'])!=set(cov[a]['accepted_observation_ids']) for a in coverage):raise ValueError('existing guard must preserve original accepted IDs exactly')
    return changed,coverage,'default',None


def main():
    binding.configure('paths');OUT.mkdir(exist_ok=True);PATHS.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve guard-parent composition')
    cases=read(runner.RAW/'protocol.json')['cases'];old=read(guard.OUT/'RF_selection.json');rows=[]
    for case in cases:
        c=next(r for r in old['rows'] if r['case']==case);rows.append(dict(case=case,source_sha256=c['source_sha256'],use_guard=use_guard(c),original_RF_gains=c['RF_gains']))
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),guard_RF_selection_sha256=sha(guard.OUT/'RF_selection.json'),
        old011guard_decision_reused_without_new_position_or_candidate_selection=True,
        original_guard_and_native19permutation_identity_alias_residual_rules_unchanged=True,
        only_changed_guard_cases_refit_others_use_existing_native_results=True,
        parent_mask_and_original_accepted_IDs_must_be_identical=True,
        same_c0_fitted_c_original5x48_cold_and_native_search_budgets=True,
        no_GPS_following_TLE_new_RF_IQ_or_unqualified_relabeling=True))
    write(OUT/'RF_selection.json',dict(rows=rows,RF_parent_choices_sealed_before_new_native_search_and_geographic_evaluation=True))
    paths.runner=runner;paths.OUT=PATHS;paths.parent=parent;receipts=[]
    import shutil
    for r in rows:
        if r['use_guard']:receipts.append(paths.one(r['case']))
        else:
            for p in (runner.RAW/'graph_seeded_paths').glob(r['case']+'*.json'):shutil.copyfile(p,PATHS/p.name)
            receipts.append(dict(case=r['case'],status='complete',unchanged_parent_native_results_reused=True))
    write(PATHS/'execution.json',dict(rows=receipts,all_terminal=True,all_passed=all(r['status']=='complete' for r in receipts)))


if __name__=='__main__':main()
