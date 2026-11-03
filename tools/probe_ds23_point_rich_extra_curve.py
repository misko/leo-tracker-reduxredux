"""One dense whole curve omitted by the original longest-span target budget."""

import copy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import repair_ds23_iteration009_targets as repair
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'point_rich_extra_curve'


def choose_extra(inventory,previous_components):
    eligible=[r for r in inventory['ranking'] if r['curved'] and r['points']==r['original_points'] and r['points']>=12 and r['component'] not in previous_components]
    return sorted(eligible,key=lambda r:(-r['points'],-r['span_s'],r['component']))[:1]


def one(case):
    repair.configure();d=repair.engine.current_setup(case);inventory=read(repair.runner.RAW/case/'inventory.json')['arms']['c0']
    previous=read(repair.OUT/(case+'_nominations.json'));used={r['target']['component'] for r in previous['targets']}
    active={r['component'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    targets=choose_extra(repair.whole_targets(inventory,active),used)
    if not targets:
        write(OUT/(case+'.json'),dict(case=case,targets=[],trials=[],selected=None));return dict(case=case,targets=0)
    nominations=repair.ORIGINAL_NOMINATE(d,dict(inventory,ranking=targets));write(OUT/(case+'_nominations.json'),nominations)
    target=nominations['targets'][0];best=target['best'];trials=[]
    if best:
        matching=[r for r in previous['targets'] if r['best'] is not None and r['best']['candidate_index']==best['candidate_index']]
        offers=[[(target,best)]]
        if matching:
            context=max(matching,key=lambda r:r['target']['points']);offers.append([(target,best),(context,context['best'])])
        for parts in offers:
            node=copy.deepcopy(d['node']);keep=d['keep'].copy()
            for row,candidate in parts:
                k=row['row_index'];keep[d['base'].slices[k]]=True
                node['seed']['rows'][k].update(candidate_index=candidate['candidate_index'],candidate_norad=candidate['norad']);node['aliases'][k]=int(candidate['aliases'][0])
            labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
            arms={a:repair.engine.support.refit(d,node,keep,a,means) for a in ['c0','fitted_c']}
            result=dict(arms=arms,node=node,mask=keep,entries=d['entries'],means=means,paired_valid=bool(valid(arms)),
                additions=[dict(component=r['target']['component'],candidate_index=c['candidate_index'],norad=c['norad'],alias=int(c['aliases'][0])) for r,c in parts],
                added_curved_points=int(keep.sum()-d['keep'].sum()))
            trials.append(result);print(case,result['added_curved_points'],'points',[a['norad'] for a in result['additions']],'valid',result['paired_valid'],flush=True)
    good=[t for t in trials if t['paired_valid']];selected=max(good,key=lambda t:t['added_curved_points']) if good else None
    write(OUT/(case+'.json'),dict(case=case,targets=targets,trials=trials,selected=selected,no_GPS_or_following_TLE_used=True))
    return dict(case=case,targets=len(targets),trials=len(trials))


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve extra-curve experiment')
    write(OUT/'protocol.json',dict(cases=read(repair.runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        hypothesis='a dense curve outside the three-longest-span nomination budget can independently support a missing family',
        maximum_additional_whole_curved_tracks=1,ranking='descending native point count, descending span, component key',
        at_most_one_single_and_one_union_with_largest_prior_same_family_nominee=True,
        same_frozen_covariance_nomination_and_original_support_aware5x48fitter=True,
        no_GPS_new_RF_following_TLE_prior_relaxation_or_point_trimming=True,
        matched_c0_fitted_c_points_aliases_and_budgets=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
