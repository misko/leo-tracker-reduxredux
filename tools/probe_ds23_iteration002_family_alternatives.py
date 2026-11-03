"""Test common top-three family identities on an identical recovered point set."""

import copy
from pathlib import Path

import numpy as np

from probe_ds23_family_cavity_position import fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
import run_ds23_dbg01_iteration_002 as iteration
from run_algo01_ds23_sample import read, write, sha

OUT = iteration.RAW/'family_alternatives'


def common_family_candidates(additions, nominations, maximum=3):
    by_component = {r['target']['component']:r for r in nominations}
    candidates = [{r['candidate_index']:r for r in by_component[a['component']]['candidates'][:maximum]
                   if r['qualified']} for a in additions]
    common = set.intersection(*(set(c) for c in candidates))
    return [(j, [c[j] for c in candidates]) for j in sorted(common)]


def one(case):
    d = iteration.current_setup(case)
    growth = read(iteration.RAW/'family_seeded_growth'/(case+'.json'))
    original = growth['selected']
    trials, checks, decisions = [], [], []
    if original is not None:
        nominations = [r for folder in ['single_curve_reentry','remaining_curves'] for r in
                       read(iteration.RAW/folder/(case+'_nominations.json'))['targets']]
        groups = {}
        for addition in original['additions']:
            groups.setdefault(addition['norad'], []).append(addition)
        for family, additions in groups.items():
            if len(additions) < 2:
                continue
            pool = common_family_candidates(additions, nominations)
            for j, offers in pool:
                if int(d['scan'].norads[j]) == family:
                    continue
                node = copy.deepcopy(original['node'])
                updated = copy.deepcopy(original['additions'])
                for addition, offer in zip(additions, offers, strict=True):
                    slot = next(k for k,r in enumerate(node['seed']['rows']) if r['component']==addition['component'])
                    node['seed']['rows'][slot].update(candidate_index=j,candidate_norad=int(d['scan'].norads[j]))
                    node['aliases'][slot]=int(offer['aliases'][0])
                    row = next(r for r in updated if r['component']==addition['component'])
                    row.update(candidate_index=j,norad=int(d['scan'].norads[j]),alias=int(offer['aliases'][0]))
                labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
                trial=fit_configuration(dict(d,keep=np.asarray(original['mask'],bool)),node,original['entries'],d['all_means'][labels])
                trial.update(mask=original['mask'],additions=updated,added_curved_points=original['added_curved_points'],
                             replaced_growth_family=family)
                trials.append(trial)
                print(case,'matched-mask family alternative',family,'to',int(d['scan'].norads[j]),trial['paired_valid'],flush=True)
            choices=[original]+[t for t in trials if t['paired_valid']]
            best=min(choices,key=lambda r:r['arms']['c0']['corrected_selection_loss'])
            gain=original['arms']['c0']['corrected_selection_loss']-best['arms']['c0']['corrected_selection_loss']
            penalty=float(2*np.log(max(1,len(pool))))
            decisions.append(dict(original_family=family,pool=[int(d['scan'].norads[j]) for j,_ in pool],
                                  gain=gain,penalty=penalty,adopted=bool(gain>penalty)))
            selected=best if gain>penalty else original
            break
        else:
            selected=original
    else:
        selected=None
    extension=None
    if selected is not None and selected is not original:
        nomination_by_key={r['target']['component']:r for r in nominations}
        failed_union=growth['extension']
        new=[a for a in failed_union['additions'] if a['component'] not in {r['component'] for r in selected['additions']}] if failed_union else []
        if new:
            node,keep=copy.deepcopy(selected['node']),np.asarray(selected['mask'],bool).copy()
            additions=copy.deepcopy(selected['additions'])
            for addition in new:
                slot=next(k for k,r in enumerate(node['seed']['rows']) if r['component']==addition['component'])
                node['seed']['rows'][slot].update(candidate_index=addition['candidate_index'],candidate_norad=addition['norad'])
                node['aliases'][slot]=addition['alias'];keep[d['base'].slices[slot]]=True;additions.append(addition)
            labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
            extension=fit_configuration(dict(d,keep=keep),node,d['entries'],d['all_means'][labels])
            extension.update(mask=keep,additions=additions,added_curved_points=int(keep.sum()-d['keep'].sum()))
            trials.append(extension)
            print(case,'separate-family long-curve extension',extension['added_curved_points'],extension['paired_valid'],flush=True)
            if extension['paired_valid']:
                selected=extension
    for trial in trials+([original] if original else []):
        dd=dict(d,node=trial['node'],keep=np.asarray(trial['mask'],bool),entries=trial['entries'],means=np.asarray(trial['means']))
        for arm,saved in trial['arms'].items():checks.append(audit_baseline(dd,arm,saved))
    coverage=growth['coverage']
    if selected is not None and selected is not original:
        dd=dict(d,node=selected['node'],keep=np.asarray(selected['mask'],bool),entries=selected['entries'],means=np.asarray(selected['means']),arms=selected['arms'])
        coverage={a:iteration.baseline.inventory(dd,a) for a in ['c0','fitted_c']}
    result=dict(case=case,selected=selected,coverage=coverage,trials=trials,decisions=decisions,checks=checks,
                extension=extension,all_passed=True,RF_selection_sealed_before_new_geographic_evaluation=True,
                original_growth_position_sha256=sha(iteration.RAW/'family_seeded_growth'/(case+'.json')))
    write(OUT/(case+'.json'),result)
    return dict(case=case,all_passed=True,trial_arms_audited=len(checks),new_trials=len(trials),decisions=decisions)


def main():
    iteration.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve family alternative evidence')
    write(OUT/'protocol.json',dict(cases=read(iteration.RAW/'protocol.json')['cases'],
        hypothesis='joint original family alternatives were absent when only leading per-curve offers were combined',
        candidates='intersection of qualified top-three causal candidates for already recovered multi-owner family',
        matched_mask_selection='minimum corrected c0 evidence; original candidate preference2log(pool size)',
        at_most_two_additional_family_candidates=True,one_separate_family_extension_only_after_RF_identity_change=True,
        original_points_priors_gates_and_paired_c_budgets_unchanged=True,no_GPS_or_following_TLE=True,
        source_sha256=sha(Path(__file__))))
    rows=[one(c) for c in read(iteration.RAW/'protocol.json')['cases']]
    write(OUT/'execution.json',dict(rows=rows,all_passed=True,all_terminal=True,
                                  no_new_geographic_evaluation_before_selection=True))


if __name__=='__main__':main()
