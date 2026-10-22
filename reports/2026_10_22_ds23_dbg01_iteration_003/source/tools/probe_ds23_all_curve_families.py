"""Bounded ALGO02/03 reentry using all unused curves and common family offers.

Nomination retains shared receiver uncertainty across curves. Final fitting
reuses the existing physical model, original gates, priors and paired c arms.
No evaluation coordinate is imported or used to rank hypotheses.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal

import numpy as np

import probe_ds23_family_cavity_nominations as nomination
import probe_ds23_single_curved_reentry as single
from ds23_family_cavity import predictive_density_reference
from probe_ds23_family_cavity_position import fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
from run_algo01_ds23_sample import ROOT,read,write,sha
import run_ds23_dbg01_iteration_002 as context

RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_003_raw'
LIMIT=8


def configure(raw):
    global RAW
    RAW=Path(raw)
    context.RAW=RAW
    context.configure()


def merged_prediction_data(parts):
    first=parts[0]
    if any(p['radio_width']!=first['radio_width'] or
           not np.array_equal(p['coefficient'],first['coefficient']) or
           not np.array_equal(p['covariance'],first['covariance']) for p in parts):
        raise ValueError('all proposed curves must share the same original calibration posterior')
    data={key:first[key] for key in ['p','coefficient','covariance','radio_width','target']}
    for key in ['times','values','q','noise','radio']:
        data[key]=np.concatenate([p[key] for p in parts])
    data['groups']=np.concatenate([np.full(len(p['times']),k,int) for k,p in enumerate(parts)])
    data['members']=[p['members'][0] for p in parts]
    data['held_owners']=len({(m['receiver'],m['channel']) for m in data['members']})
    nb=data['radio_width'];radio=data['radio'];groups=data['groups']
    data['base_covariance']=(np.diag(data['noise']**2)+radio@data['covariance'][:nb,:nb]@radio.T+
                             300.**2*(groups[:,None]==groups[None,:]))
    return data


def group_candidates(targets):
    groups={}
    for target in targets:
        for offer in target['candidates'][:3]:
            if offer['qualified']:
                groups.setdefault(offer['candidate_index'],[]).append((target,offer))
    return groups


def nominate(case):
    d=context.current_setup(case);inventory=read(RAW/case/'inventory.json')['arms']['c0']
    targets=[r for r in inventory['ranking'] if r['curved'] and r['points']>=12 and r['points']==r['original_points']]
    records=[]
    for offset in range(0,len(targets),3):
        records.extend(single.nominate(d,dict(inventory,ranking=targets[offset:offset+3]))['targets'])
    x=np.asarray(d['arms']['c0']['endpoint_east_north_km']);d=dict(d,x=x)
    p=context.baseline.build(d,'c0',d['arms']['c0']['phase_reference'])
    grouped=[]
    for j,offers in group_candidates(records).items():
        parts=[single.predictive_track_data(d,p,x,r['row_index']) for r,_ in offers]
        data=merged_prediction_data(parts)
        aliases=[int(offer['aliases'][0]) for _,offer in offers]
        result=nomination.candidate_prediction(d,data,j,aliases)
        grouped.append(dict(candidate_index=j,norad=int(d['scan'].norads[j]),prediction=result,
            points=len(data['times']),owners=data['held_owners'],
            additions=[dict(component=r['target']['component'],row_index=r['row_index'],
                            candidate_index=j,norad=int(d['scan'].norads[j]),alias=alias)
                       for (r,_),alias in zip(offers,aliases,strict=True)]))
    eligible=[r for r in grouped if r['prediction']['qualified']]
    eligible.sort(key=lambda r:(-r['points'],-r['owners'],r['prediction']['score']/r['points'],r['norad']))
    result=dict(case=case,targets=records,groups=grouped,shortlist=eligible[:LIMIT],
        scheduling='most proposed points, then independent RX/channel owners, then predictive score per point',
        scheduling_is_not_evidence_comparison_between_different_masks=True,
        all_nomination_curves_disjoint_from_calibration=True,
        no_GPS_or_following_TLE=True,source_sha256=sha(Path(__file__)))
    write(RAW/'all_curve_families'/(case+'_nominations.json'),result)
    print(case,'unused curved targets',len(records),'common candidate groups',len(grouped),'shortlist',len(result['shortlist']),flush=True)
    return dict(case=case,status='complete',targets=len(records),groups=len(grouped))


def fit_additions(d,additions):
    node,keep=copy.deepcopy(d['node']),d['keep'].copy()
    for addition in additions:
        k=next(k for k,r in enumerate(node['seed']['rows']) if r['component']==addition['component'])
        node['seed']['rows'][k].update(candidate_index=addition['candidate_index'],candidate_norad=addition['norad'])
        node['aliases'][k]=addition['alias'];keep[d['base'].slices[k]]=True
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    result=fit_configuration(dict(d,keep=keep),node,d['entries'],d['all_means'][labels])
    result.update(additions=additions,mask=keep,added_curved_points=int(keep.sum()-d['keep'].sum()))
    return result


def fit_one(job):
    case,index=job;folder=RAW/'all_curve_families'/case;folder.mkdir(exist_ok=True)
    path=folder/f'fit_{index:02d}.json'
    if path.exists():raise FileExistsError('preserve completed family-group fit')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 s family-group cap')))
    signal.alarm(180)
    try:
        d=context.current_setup(case);group=read(RAW/'all_curve_families'/(case+'_nominations.json'))['shortlist'][index]
        result=fit_additions(d,group['additions'])
        result.update(case=case,index=index,status='complete',group_norad=group['norad'])
        write(path,result)
        print(case,'group',index,group['norad'],result['added_curved_points'],result['paired_valid'],flush=True)
        return dict(case=case,index=index,status='complete',paired_valid=result['paired_valid'])
    except Exception as exc:
        import traceback
        result=dict(case=case,index=index,status='failed',error=repr(exc),traceback=traceback.format_exc())
        write(folder/f'fit_{index:02d}_failed.json',result)
        return result
    finally:signal.alarm(0)


def choose(trials):
    good=[r for r in trials if r['paired_valid']]
    if not good:return None
    good.sort(key=lambda r:(-r['added_curved_points'],tuple(a['component'] for a in r['additions']),
                            r['arms']['c0']['corrected_selection_loss']))
    return good[0]


def combine(case):
    d=context.current_setup(case);folder=RAW/'all_curve_families'/case
    trials=[read(p) for p in sorted(folder.glob('fit_[0-9][0-9].json'))]
    original=read(RAW/'single_curve_reentry'/(case+'_positions.json'))['selected']
    if original is not None:trials.append(original)
    good=sorted([r for r in trials if r['paired_valid']],key=lambda r:-r['added_curved_points'])
    selected=choose(trials);unions=[]
    for candidate in good[:4]:
        if selected is None:break
        old={r['component']:r for r in selected['additions']}
        if any(r['component'] in old and old[r['component']]['candidate_index']!=r['candidate_index'] for r in candidate['additions']):
            continue
        old.update({r['component']:r for r in candidate['additions']})
        if len(old)<=len(selected['additions']):continue
        trial=fit_additions(d,sorted(old.values(),key=lambda r:r['component']))
        unions.append(trial);trials.append(trial)
        print(case,'union',trial['added_curved_points'],trial['paired_valid'],flush=True)
        if trial['paired_valid']:selected=choose(trials)
        if len(unions)>=3:break
    write(RAW/'all_curve_families'/(case+'_positions.json'),dict(case=case,trials=trials,unions=unions,
        selected=selected,RF_selection_frozen_before_geographic_evaluation=True,
        original_curved_and_predictive_observations_preserved=True))
    return dict(case=case,status='complete',selected_added_points=selected['added_curved_points'] if selected else 0)


def audit(case):
    d=context.current_setup(case);x=np.asarray(d['arms']['c0']['endpoint_east_north_km']);d=dict(d,x=x)
    p=context.baseline.build(d,'c0',d['arms']['c0']['phase_reference'])
    nominees=read(RAW/'all_curve_families'/(case+'_nominations.json'));checks=[]
    for group in nominees['groups']:
        parts=[single.predictive_track_data(d,p,x,r['row_index']) for r in group['additions']]
        data=merged_prediction_data(parts);capture=[];original=nomination.gaussian_prediction
        def record(raw,design,covariance,sigma):
            capture.append((raw.copy(),design.copy(),covariance.copy(),sigma.copy()))
            return original(raw,design,covariance,sigma)
        nomination.gaussian_prediction=record
        try:replay=nomination.candidate_prediction(d,data,group['candidate_index'],[r['alias'] for r in group['additions']])
        finally:nomination.gaussian_prediction=original
        direct,method=predictive_density_reference(*capture[-1]);saved=group['prediction']['score']
        if abs(replay['score']-saved)>1e-5 or abs(direct-saved)>2e-3:
            raise ValueError('joint family prediction density does not independently replay')
        checks.append(dict(norad=group['norad'],score_difference=abs(direct-saved),method=method))
    positions=read(RAW/'all_curve_families'/(case+'_positions.json'));endpoint=[]
    for trial in positions['trials']:
        dd=dict(d,node=trial['node'],keep=np.asarray(trial['mask'],bool),entries=trial['entries'],means=np.asarray(trial['means']))
        for arm,saved in trial['arms'].items():endpoint.append(audit_baseline(dd,arm,saved))
    selected=positions['selected'];coverage=read(RAW/case/'inventory.json')['arms']
    if selected is not None:
        dd=dict(d,node=selected['node'],keep=np.asarray(selected['mask'],bool),entries=selected['entries'],means=np.asarray(selected['means']),arms=selected['arms'])
        coverage={a:context.baseline.inventory(dd,a) for a in ['c0','fitted_c']}
    write(RAW/'all_curve_families'/(case+'_audit.json'),dict(case=case,all_passed=True,predictive_checks=checks,
        endpoint_checks=endpoint,coverage=coverage,positions_sha256=sha(RAW/'all_curve_families'/(case+'_positions.json')),
        no_new_geographic_evaluation_before_selection=True))
    return dict(case=case,status='complete',all_passed=True,predictive_densities=len(checks),endpoint_arms=len(endpoint))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=RAW)
    parser.add_argument('--stage',choices=['nominate','fit','combine','audit'],required=True)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();configure(args.raw)
    if not 1<=args.workers<=24:raise ValueError('one to24workers required')
    out=RAW/'all_curve_families';out.mkdir(exist_ok=True);cases=read(RAW/'protocol.json')['cases']
    protocol=dict(cases=cases,all_wholly_unused_curved_tracks_at_least12points=True,
        full_causal_catalogue_initial_screen=True,qualified_top_three_per_curve_retained=True,
        one_shared_phase_and_existing_supported_physical_modes_per_family=True,
        joint_radio_cross_covariance_preserved=True,original_nomination_calibration_excludes_all_new_curves=True,
        maximum_candidate_groups_per_case=LIMIT,maximum_additional_valid_group_unions=3,
        final_original_gates_and_priors_and_matching_c_budgets=True,
        cold_regional_start=[0,0],phase_rounds=5,fit_steps=48,
        adoption='most added curved points, deterministic component order, normalized c0 score among identical masks',
        no_GPS_or_following_TLE_or_new_RF=True,source_sha256=sha(Path(__file__)))
    path=out/'protocol.json'
    if path.exists():
        if read(path)!=protocol:raise ValueError('preserve frozen all-curve family protocol')
    else:write(path,protocol)
    if args.stage=='fit':
        jobs=[(c,k) for c in cases for k in range(len(read(out/(c+'_nominations.json'))['shortlist']))]
        function=fit_one
    else:
        jobs=cases;function={'nominate':nominate,'combine':combine,'audit':audit}[args.stage]
    if args.stage=='audit' and not read(out/'combine_execution.json')['all_passed']:
        raise ValueError('finish all group fits and combinations before numerical audit')
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(function,j) for j in jobs]):
            rows.append(future.result())
    write(out/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,
        all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
