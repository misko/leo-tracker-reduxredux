"""Frozen RF-only cohort test of normalized receiver covariance and gate-aware growth."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import re
import time
import numpy as np

from algo02_scan import pair_passes
from probe_algo03_frame_peak_recovery import context,SOURCE
from probe_ds23_frequency_events import parameters,refit,summary,cached
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon

OUT=ROOT/'reports/2026_10_20_ds23_gate_retention_cohort'
ARMS=('c0','fitted_c')


def select_offer(proposals):
    eligible=[p for p in proposals if p['added_points']>0 and p['independent_support_pass']]
    return min(eligible,key=lambda p:(-p['added_points'],p['proposal_score'],p['norad'])) if eligible else None


def initialize():
    if (OUT/'protocol.json').exists():return read(OUT/'protocol.json')
    development=read(ROOT/'reports/2026_10_20_ds23_frequency_events_v3/cohort_protocol.json')['cases']
    excluded=set(development)|{'DS23-0268','DS23-0039','DS23-0342'}
    previously_used=set(excluded)
    for directory in ROOT.glob('reports/*algo03*'):
        for path in directory.glob('*DS23*'):
            match=re.search(r'DS23-\d{4}',path.name)
            if match:previously_used.add(match.group())
    candidates=[]
    for path in sorted(SOURCE.glob('DS23-*/algo02_result.json')):
        if path.parent.name in excluded:continue
        result=read(path)
        if result['status']=='accepted':candidates.append(path.parent.name)
    if len(candidates)<20:raise ValueError('insufficient additional accepted recordings')
    rng=np.random.default_rng(104729);additional=sorted(rng.choice(candidates,20,replace=False).tolist())
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(development=development,additional=additional,cases=development+additional,
        seed=104729,additional_pool=candidates,additional_development_cases_excluded=sorted(excluded),
        additional_prior_ALGO03_exposure=[c for c in additional if c in previously_used],
        additional_is_not_an_untouched_holdout=True,
        fixed_before_new_geographic_evaluation=True,selection_does_not_read_position_errors=True,
        receiver_basis_spacing_s=10,receiver_basis_width_s=15,average_prior_variance_matched=True,
        one_original_nominee_family_growth_offer_per_scan=True,phase_grid_s=[-15,15,.25],
        original_points_aliases_labels_weights_and_physical_priors_preserved=True,
        linear_tracks_never_calibrate=True,causal_TLE_only=True,GPS_used=False,
        regional_box_width_km=25,cold_start_km=[0,0],phase_rounds=5,position_iterations=48,
        constrained_rounds=5,constrained_iterations=40,constrained_margin=.01,
        near_feasible_trigger_minimum_slack=-.10,RF_same_mask_model_choice_penalty=float(2*np.log(2)),
        fine_only_selection='paired gates and c0 full marginal bound beats same-mask original by 2 log(2)',
        growth_selection='complete curved-family offer; paired original gates; no GPS/score comparison across masks',
        development_is_reused_additional_is_same_site_not_new_location_validation=True,
        source_sha256=sha(Path(__file__)))
    write(OUT/'protocol.json',protocol);return protocol


def make(scan,node,mask,arm,reference,powers,means,hyper,entries):
    p=make_event_problem(scan,node,mask,arm,reference,powers,means,hyper,[])
    attach_event_predictive(p,entries,powers);return cached(p)


def constrained(scan,node,mask,powers,means,hyper,entries,pair):
    from ds23_feasible_position import feasible_fit
    from probe_algo03_feasible_recovery import gate_slacks
    output={}
    for arm in ARMS:
        reference=np.asarray(pair[arm]['phase_reference']);x=np.asarray(pair[arm]['endpoint_east_north_km']);history=[]
        for epoch in range(5):
            p=make(scan,node,mask,arm,reference,powers,means,hyper,entries)
            fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.asarray(list(gate_slacks(p,z,entries).values()))-.01,x,p.lower,p.upper,iterations=40)
            x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
            reference=phase
        output[arm]=summary(p,x,entries);output[arm].update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
            minimum_gate_slack=min(gate_slacks(p,x,entries).values()))
    return output


def qualify(scan,node,mask,powers,means,hyper,entries,pair):
    if pair_passes(pair,include_linear=True):return pair,dict(constrained=False,paired_valid=True)
    from probe_algo03_feasible_recovery import gate_slacks
    minima=[]
    for arm in ARMS:
        r=pair[arm];p=make(scan,node,mask,arm,np.asarray(r['phase_reference']),powers,means,hyper,entries)
        minima.append(min(gate_slacks(p,np.asarray(r['endpoint_east_north_km']),entries).values()))
    if min(minima)<-.10:return pair,dict(constrained=False,paired_valid=False,minimum_gate_slacks=minima)
    refined=constrained(scan,node,mask,powers,means,hyper,entries,pair)
    return refined,dict(constrained=True,paired_valid=pair_passes(refined,include_linear=True),minimum_gate_slacks=minima)


def offers(p,x):
    scan=p.scan;state=p.state(x);c=p.calculate(x);groups={};eligible=[]
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        t=scan.tracks[i]
        if p.keep[sl].all() or len(t['times'])<12 or np.ptp(t['times'])<10:continue
        eligible.append(k)
    if not eligible:return []
    observed={k:scan.tracks[p.members[k]]['values']-scan.hardware(scan.tracks[p.members[k]],state['beta'])-
        scan.tracks[p.members[k]]['rf_hz']/11.5e9*scan.rx_basis[p.members[k]]@state['smooth'][scan.tracks[p.members[k]]['receiver']-1] for k in eligible}
    begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    for phase in np.linspace(-15,15,121):
        phases=np.full(len(p.labels),phase)
        frequency,elevation=paired_phase_frequency(p.sky,p.flat_times,p.flat_labels,phases,*latlon(x))
        if p.supported:
            modes=paired_frequency_modes(p.sky,p.mode_bank,p.flat_times,p.flat_labels,phases,*latlon(x))
            for m,local in enumerate(p.supported_local):
                use=p.flat_labels==local;frequency[use]+=modes[use]@c['coefficient'][begin+3*m:begin+3*m+3]
        passing={}
        for k in eligible:
            row=p.rows[k];i=p.members[k];sl=p.slices[k];t=scan.tracks[i];q=t['rf_hz']/11.5e9
            terms=profile(observed[k],q*frequency[sl],*scan.white[i]);noise=batch_noise_screen(terms['innovations'],t['times'])
            valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and noise['noise_screen_pass'][0]
                and int(terms['alias'][0])==p.alias[k] and elevation[sl].min()>=0)
            if valid:passing.setdefault(row['candidate_index'],[]).append((k,float(terms['cost'][0])))
        for j,members in passing.items():
            owners={(scan.tracks[p.members[k]]['receiver'],scan.tracks[p.members[k]]['channel']) for k,_ in members}
            owners.update((scan.tracks[i]['receiver'],scan.tracks[i]['channel']) for r,i,sl in zip(p.rows,p.members,p.slices,strict=True)
                          if r['candidate_index']==j and p.keep[sl].any())
            candidate=dict(norad=int(scan.norads[j]),candidate_index=j,phase_s=float(phase),
                row_indices=[k for k,_ in members],components=[p.rows[k]['component'] for k,_ in members],
                added_points=sum(int((~p.keep[p.slices[k]]).sum()) for k,_ in members),
                proposal_score=sum(score for _,score in members),independent_support_pass=j not in p.supported or len(owners)>=2)
            previous=groups.get(j)
            if select_offer([candidate,previous] if previous else [candidate]) is candidate:groups[j]=candidate
    return sorted(groups.values(),key=lambda p:(-p['added_points'],p['proposal_score'],p['norad']))


def run_case(case):
    output=OUT/(case+'.json')
    if output.exists():return dict(case=case,cached=True)
    started=time.monotonic();scan,node,mask,base,old=context(case);powers,means,hyper=parameters(scan,base,old)
    entries=old['linear_entries'] if old['linear_paired_valid'] else [];baseline=old['policy_arms'];replay=[]
    for arm in ARMS:
        r=baseline[arm];p=make(scan,node,mask,arm,np.asarray(r['phase_reference']),powers,means,hyper,entries)
        difference=float(p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']);replay.append(difference)
        if abs(difference)>1e-3:raise ValueError('baseline RF replay mismatch')
    fine=copy.copy(scan);fine.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    node=copy.deepcopy(node);node['seed']['state']['smooth']=np.zeros((2,fine.rx_basis[0].shape[1]))
    pair={arm:refit(fine,node,mask,arm,powers,means,hyper,[],entries) for arm in ARMS}
    fine_pair,fine_receipt=qualify(fine,node,mask,powers,means,hyper,entries,pair)
    gain=float(baseline['c0']['negative_twice_elbo']-fine_pair['c0']['negative_twice_elbo'])
    fine_accepted=fine_receipt['paired_valid'] and gain>2*np.log(2)
    # The growth proposal uses the same fine-model RF point, regardless of its same-mask score gain.
    r=fine_pair['c0'];p=make(fine,node,mask,'c0',np.asarray(r['phase_reference']),powers,means,hyper,entries)
    proposal_list=offers(p,np.asarray(r['endpoint_east_north_km']));proposal=select_offer(proposal_list)
    growth_pair=None;growth_receipt=dict(paired_valid=False,reason='no supported complete-curve offer');offered_mask=mask.copy()
    if proposal is not None:
        for k in proposal['row_indices']:offered_mask[base.slices[k]]=True
        trial={arm:refit(fine,node,offered_mask,arm,powers,means,hyper,[],entries) for arm in ARMS}
        growth_pair,growth_receipt=qualify(fine,node,offered_mask,powers,means,hyper,entries,trial)
    policy=growth_pair if growth_receipt['paired_valid'] else (fine_pair if fine_accepted else baseline)
    document=dict(case=case,baseline_arms=baseline,fine_arms=fine_pair,fine_receipt=fine_receipt,
        fine_same_mask_c0_gain=gain,fine_accepted=fine_accepted,growth_arms=growth_pair,growth_receipt=growth_receipt,
        policy_arms=policy,proposal=proposal,all_family_proposals=proposal_list,original_mask=mask,offered_mask=offered_mask,
        source_sha256=sha(SOURCE/case/'algo02_result.json'),baseline_objective_replay_differences=replay,
        GPS_used=False,future_TLE_used=False,original_points_never_removed=True,seconds=time.monotonic()-started)
    write(output,document);result=dict(case=case,fine_accepted=fine_accepted,growth_accepted=growth_receipt['paired_valid'],
        offered_points=int(offered_mask.sum()-mask.sum()),seconds=document['seconds'])
    print(result,flush=True);return result


def run():
    protocol=initialize();receipts=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures={executor.submit(run_case,case):case for case in protocol['cases']}
        for future in as_completed(futures):
            try:result=future.result()
            except Exception as exc:result=dict(case=futures[future],error=repr(exc))
            receipts.append(result);write(OUT/'progress.json',dict(completed=len(receipts),total=len(futures),receipts=receipts))
    write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True,seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    initialize() if args.prepare_only else run()
