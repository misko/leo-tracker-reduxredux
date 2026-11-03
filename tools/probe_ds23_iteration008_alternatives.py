"""Bounded same-mask whole-curve identity alternatives, using causal RF scores."""

import copy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_008 as runner
import probe_ds23_graph_seeded_paths as paths
from ds23_family_cavity import unused_student_gap
from probe_ds23_family_cavity_position import unused_count,fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'same_mask_alternatives'


def choices(target):
    return [c for c in target['candidates'] if c['qualified'] and c['conditional_RMS_hz']<=750][:3]


def one(case):
    runner.configure();original=runner.engine.current_setup(case);parent,_,kind,_=paths.parent(case)
    nominations=read(runner.RAW/'single_curve_reentry'/(case+'_nominations.json'));groups=[]
    for target in nominations['targets'][:2]:
        offered=choices(target)
        if len(offered)<2:continue
        trials=[]
        for candidate in offered:
            row=target['row_index'];node=copy.deepcopy(original['node']);keep=original['keep'].copy();keep[original['base'].slices[row]]=True
            node['seed']['rows'][row].update(candidate_index=candidate['candidate_index'],candidate_norad=candidate['norad'])
            node['aliases'][row]=int(candidate['aliases'][0]);labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
            means=original['all_means'][labels];dd=dict(original,node=node,keep=keep,means=means,original_protected=parent['original_protected'])
            if kind=='default':
                fit=fit_configuration(dict(original,keep=keep),node,original['entries'],means);arms=fit['arms'];passed=fit['paired_valid']
            else:
                arms={a:runner.engine.support.refit(original,node,keep,a,means) for a in ['c0','fitted_c']};passed=bool(valid(arms))
            corrected={}
            for a,saved in arms.items():
                p=paths.build(dd,kind,a,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
                if abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])>1e-5:raise ValueError('alternative endpoint does not replay')
                corrected[a]=saved['negative_twice_elbo']-unused_count(p,dd['entries'])*unused_student_gap(dd['model']['nu'])
            trials.append(dict(candidate_index=candidate['candidate_index'],norad=candidate['norad'],alias=int(candidate['aliases'][0]),
                arms=arms,paired_valid=passed,corrected_loss=corrected,node=node,mask=keep,means=means))
            print(case,target['target']['component'],candidate['norad'],'paired',passed,flush=True)
        passing=[t for t in trials if t['paired_valid']];winner=min(passing,key=lambda t:t['corrected_loss']['c0']) if passing else None
        incumbent=next((t for t in passing if t['candidate_index']==target['best']['candidate_index']),None)
        penalty=float(2*np.log(len(trials)));gain=None
        if winner and incumbent:
            gain=incumbent['corrected_loss']['c0']-winner['corrected_loss']['c0']
            if winner is not incumbent and (gain<=penalty or winner['corrected_loss']['fitted_c']>=incumbent['corrected_loss']['fitted_c']):winner=incumbent
        groups.append(dict(component=target['target']['component'],points=target['target']['points'],trials=trials,
            kind=kind,original_best_norad=target['best']['norad'],selected_norad=winner['norad'] if winner else None,
            search_penalty=penalty,c0_improvement_over_valid_original_identity=gain,selection_sealed_without_GPS=True))
    write(OUT/(case+'.json'),dict(case=case,groups=groups,no_geographic_selection=True))
    return dict(case=case,groups=len(groups))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve same-mask identity experiment')
    write(OUT/'protocol.json',dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        candidate_rule='first three qualified existing causal nominees with conditional RMS<=750Hz; at most two unused curved targets',
        candidate_aliases_frozen_from_existing_c0_nomination=True,matched_c0_fitted_c_points_priors_and_budgets=True,
        parent_graph_model_kind_retained_for_all_candidates=True,same_mask_normalized_RF_loss_only=True,
        unused_Student_coordinate_constant_removed_for_identity_ranking=True,
        replacement_requires_c0_gain_above2log_pool_and_positive_fitted_c_gain=True,
        no_GPS_following_TLE_point_trimming_or_new_RF=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,RF_selection_complete_before_geographic_scoring=True))


if __name__=='__main__':main()
