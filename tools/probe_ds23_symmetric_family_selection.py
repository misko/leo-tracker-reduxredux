"""Matched signed-prior whole-family identity search with symmetric label codes.

No supplied coordinate is imported. Proposal candidates come from a previously
frozen whole-catalogue RF screen; original and trial observations are identical.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_receiver_family_search import fine_receiver_basis,orphan_predictive_labels
from ds23_symmetric_family_code import family_code,observed_labels,symmetric_gain,replace_whole_family
from ds23_feasible_position import feasible_fit
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_causal_phase_mean import forecast_phase_mean
from ds23_causal_phase_location import adjust_means
from probe_ds23_frequency_events import cached,refit,summary
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry,phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/'reports/2026_10_20_ds23_symmetric_family_selection_v2'
BANK=ROOT/'reports/2026_10_20_ds23_receiver_family_search_v2'
SIGNED=ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'
ARMS=('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (
        Path(__file__),ROOT/'tools/ds23_symmetric_family_code.py',
        ROOT/'tools/ds23_frequency_events.py',ROOT/'tools/ds23_feasible_position.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen symmetric experiment source changed')
        return p
    original=read(BANK/'protocol.json')
    bindings={case:dict(path=str((BANK/case/'result.json').relative_to(ROOT)),
                       sha256=sha(BANK/case/'result.json')) for case in original['cases']}
    p=dict(cases=original['cases'],workers=20,development_scan='DS23-0268',
        cohort_already_exposed_not_untouched_validation=True,source_sha256=hashes(),proposal_bindings=bindings,
        incumbent='published signed phase prior policy, including its original fallbacks',
        proposal_rule='at most two distinct whole-family replacements from frozen receiver-block catalogue nominees',
        receiver_covariances=['original','fine normalized 10s/15s'],
        discrete_prior='p(K) proportional 1/(K(K+1)); uniform assignments to K of N labels; both incumbent and challenger coded',
        continuous_complexity='existing normalized marginalized RF bound unchanged',
        adoption='original paired gates, both c-arm symmetric score gains positive; lowest c0 coded RF score',
        cold_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations_per_round=48,
        constrained_finalists=2,constrained_phase_rounds=5,constrained_iterations_per_round=40,
        gate_thresholds_unchanged_stricter_normalized_interior=.01,
        observations_masks_noise_powers_and_other_priors_matched_in_c_arms=True,
        candidate_labels_aliases_schedule_identical_between_c_arms=True,
        linear_points_never_update_radio_calibration=True,
        no_GPS_future_TLE_new_RF_or_point_removal=True)
    p.update(implementation_amendment='resize the cold seed smooth coefficient matrix with each receiver basis; initial pilot stopped on dimension mismatch before producing a policy',
             previous_failed_pilot='reports/2026_10_20_ds23_symmetric_family_selection')
    write(path,p);return p


def bound_incumbent(case):
    binding=read(SIGNED/'evaluation_audit.json')['evidence'][case]
    path=ROOT/binding['path']
    if sha(path)!=binding['sha256']:raise ValueError('signed incumbent evidence changed')
    return read(path),binding


def build(scan,node,keep,arm,reference,powers,means,model,entries):
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    p=make_event_problem(scan,node,keep,arm,reference,powers,means[labels],model,[])
    attach_event_predictive(p,entries,powers);cached(p);return p


def constrain(scan,node,keep,powers,means,model,entries,pair):
    result={}
    for arm in ARMS:
        x=np.asarray(pair[arm]['endpoint_east_north_km'])
        reference=np.asarray(pair[arm]['phase_reference']);history=[]
        for epoch in range(5):
            p=build(scan,node,keep,arm,reference,powers,means,model,entries)
            fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.array(list(gate_slacks(p,z,entries).values()))-.01,
                x,p.lower,p.upper,iterations=40)
            x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            change=float(np.max(abs(phase-reference)))
            history.append(dict(epoch=epoch,fit=fitted,phase_change_s=change));reference=phase
        result[arm]=dict(summary(p,x,entries),history=history,final_phase_change_s=change,
                        minimum_gate_slack=min(gate_slacks(p,x,entries).values()))
    return result


def aliases_for_family(p,x,proposal,entries):
    old,new=proposal['block']['original_index'],proposal['candidate_index']
    state=p.state(x);phase=proposal['phase_s'];result={}
    bank=dict(time_s=p.scan.sky['time_s'],position_km=p.scan.sky['position_km'][[new]],
              velocity_km_s=p.scan.sky['velocity_km_s'][[new]])
    all_rows=[('curve',k,i) for k,(r,i) in enumerate(zip(p.rows,p.members,strict=True)) if r['candidate_index']==old]
    all_rows += [('linear',k,e['track_index']) for k,e in enumerate(entries) if e['candidate_index']==old]
    for kind,k,i in all_rows:
        t=p.scan.tracks[i];q=t['rf_hz']/11.5e9
        geometry=prepare_phase_geometry(bank,t['times'],np.array([phase]))
        expected,_,_=phase_linear_frequency(geometry,*latlon(x))
        y=t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y,q*expected,*p.scan.white[i],bias_sigma=300.)
        result[kind,k]=int(terms['alias'][0])
    return result


def run(case):
    protocol=prepare();directory=OUT/case;directory.mkdir(exist_ok=True)
    if (directory/'result.json').exists():return dict(case=case,cached=True)
    binding=protocol['proposal_bindings'][case];bankpath=ROOT/binding['path']
    if sha(bankpath)!=binding['sha256']:raise ValueError('frozen RF proposal bank changed')
    bank=read(bankpath);scan,node,keep,base,old=context(case)
    signed,signed_binding=bound_incumbent(case)
    if signed['baseline_arms']!=old['policy_arms'] or not np.array_equal(signed['original_mask'],keep):
        raise ValueError('signed incumbent has different observations')
    model=old['hyperparameters_from_pre_RF_TLE_only'];powers=np.asarray(old['weights'])
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    nominees=[];seen=set()
    for proposal in bank['proposals']:
        key=(proposal['block']['original_index'],proposal['candidate_index'])
        if key not in seen:seen.add(key);nominees.append(proposal)
    union=sorted({r['candidate_index'] for r in node['seed']['rows']}|{p['candidate_index'] for p in nominees})
    _,receipts=phase_widths(scan,union)
    ordinary=forecast_phase_mean(receipts,model['shrinkage'])
    selected=adjust_means(ordinary,receipts,model,signed['selection']) if signed['accepted'] else ordinary
    means=np.zeros(len(scan.norads));means[union]=selected
    incumbent=signed['policy_arms'];nulls=[];initial=None
    for arm in ARMS:
        saved=incumbent[arm]
        p=build(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model,entries)
        x=np.asarray(saved['endpoint_east_north_km']);delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3:raise ValueError('signed incumbent does not replay')
        nulls.append(dict(arm=arm,RF_difference=delta))
        if arm=='c0':initial=(p,x)
    base_code=family_code(len(scan.norads),observed_labels(node,entries,keep,base.slices))
    hypotheses=[dict(name='null',node=node,entries=entries)]
    for k,proposal in enumerate(nominees):
        aliases=aliases_for_family(*initial,proposal,entries)
        changed,predictive=replace_whole_family(node,entries,proposal['block']['original_index'],
            proposal['candidate_index'],proposal['norad'],aliases)
        if orphan_predictive_labels(changed,predictive):raise ValueError('whole replacement orphaned an original factor')
        hypotheses.append(dict(name=f'whole_{k}',node=changed,entries=predictive,proposal=proposal))
    started=time.monotonic();trials=[]
    for covariance in ('original','fine'):
        changed=copy.copy(scan)
        if covariance=='fine':changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
        for h in hypotheses:
            if covariance=='original' and h['name']=='null':continue
            candidate=copy.deepcopy(h['node']);candidate['seed']['state']=zero_state(changed)
            labels=sorted({r['candidate_index'] for r in candidate['seed']['rows']})
            arms={a:refit(changed,candidate,keep,a,powers,means[labels],model,[],h['entries']) for a in ARMS}
            code=family_code(len(scan.norads),observed_labels(candidate,h['entries'],keep,base.slices))
            gain={a:symmetric_gain(incumbent[a]['negative_twice_elbo'],base_code,
                                  arms[a]['negative_twice_elbo'],code) for a in ARMS}
            trial=dict(h,node=candidate,covariance=covariance,arms=arms,paired_valid=pair_passes(arms,include_linear=True),
                       code=code,RF_coded_gains=gain)
            trials.append(trial);write(directory/(covariance+'_'+h['name']+'.json'),trial)
            print(case,covariance,h['name'],'valid',trial['paired_valid'],'gain',gain['c0'],flush=True)
    # The same symmetric prior decides which failed finalists receive refinement.
    finalists=sorted([t for t in trials if not t['paired_valid'] and t['RF_coded_gains']['c0']>0],
                      key=lambda t:-t['RF_coded_gains']['c0'])[:2]
    for t in finalists:
        changed=copy.copy(scan)
        if t['covariance']=='fine':changed.rx_basis=[fine_receiver_basis(v['times']) for v in scan.tracks]
        arms=constrain(changed,t['node'],keep,powers,means,model,t['entries'],t['arms'])
        gains={a:symmetric_gain(incumbent[a]['negative_twice_elbo'],base_code,
                               arms[a]['negative_twice_elbo'],t['code']) for a in ARMS}
        repaired=dict(t,arms=arms,constrained=True,paired_valid=pair_passes(arms,include_linear=True),RF_coded_gains=gains)
        trials.append(repaired);write(directory/(t['covariance']+'_'+t['name']+'_constrained.json'),repaired)
    eligible=[t for t in trials if t['paired_valid'] and all(g>0 for g in t['RF_coded_gains'].values())]
    chosen=max(eligible,key=lambda t:t['RF_coded_gains']['c0']) if eligible else None
    result=dict(case=case,accepted=chosen is not None,selected=chosen,
        policy_arms=chosen['arms'] if chosen else incumbent,incumbent_arms=incumbent,
        baseline_arms=old['policy_arms'],signed_incumbent_binding=signed_binding,
        original_code=base_code,original_mask=keep,means_s=means,powers=powers,
        trials=[dict(name=t['name'],covariance=t['covariance'],constrained=t.get('constrained',False),
            paired_valid=t['paired_valid'],RF_coded_gains=t['RF_coded_gains'],code=t['code']) for t in trials],
        disabled_model_replays=nulls,GPS_used=False,future_TLE_used=False,
        no_original_curved_or_predictive_observation_removed=True,source_sha256=hashes(),
        seconds=time.monotonic()-started)
    write(directory/'result.json',result)
    print(case,'accepted',result['accepted'],'seconds',result['seconds'],flush=True)
    return dict(case=case,accepted=result['accepted'],seconds=result['seconds'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args()
    protocol=prepare()
    if args.case:run(args.case)
    else:
        receipts=[]
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures={pool.submit(run,c):c for c in protocol['cases']}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/'progress.json',dict(receipts=receipts,completed=len(receipts),total=len(futures)))
        write(OUT/'execution.json',dict(all_terminal=True,receipts=receipts))
