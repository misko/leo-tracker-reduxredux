"""Full-causal-catalogue reentry of large complete inactive curve groups.

All trials keep incumbent evidence. A frozen-calibration score only nominates
identities; joint refitting and every original gate decide adoption.
"""

import argparse
import copy
import gc
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

import numpy as np

from ds23_catalogue_reentry import complete_groups,selected_indices
from ds23_causal_phase_location import adjust_means
from probe_ds23_consensus_growth import make
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_frequency_events import refit,summary
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from learn_ds23_causal_phase_forecast import distribution_cost
from dbg01_unassociated import ownership
from run_ds23_combined_recovery_full import valid,ARMS
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import profile,whitening
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_catalogue_reentry'
BULK=Path('/srv/bulk/leo/research/ds23-catalogue-reentry-20261021')


def prepare():
    original=read(ROOT/'reports/2026_10_21_ds23_consensus_growth/protocol.json')
    path=OUT/'protocol.json'
    d={k:original[k] for k in ['engineering','development','confirmation','seed']}
    d.update(source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_catalogue_reentry.py','ds23_catalogue_reentry.py']},
        maximum_groups=2,group_order='most added complete curved points, then original catalogue index',
        all_original_RF_nominations_eligible_for_grouping=True,
        all_causal_catalogue_identities_screened_per_group=True,
        coarse_phase_step_s=.25,refined_phase_step_s=.05,refined_half_width_s=.5,
        candidate_limit=3,original_nominee_always_included=True,
        no_frozen_calibration_noise_veto_for_proposals=True,
        posterior_phase_and_calibration_may_change_only_in_joint_full_evidence_fit=True,
        adoption='best c0 normalized RF bound among paired gate-passing fits on the SAME enlarged observation set',
        fixed_300Hz_fragment_constant_prior_and_original_noise_physical_priors=True,
        signed_causal_phase_means_extended_to_all_catalogue_from_identical_pre_RF_history=True,
        original_GLRT_values_masks_and_aliases_preserved_for_incumbent_points=True,
        linear_tracks_remain_predictive_and_do_not_calibrate=True,
        same_c0_fitted_c_masks_identities_aliases_priors_and_budgets=True,
        regional_center=[37.906,-122.545],regional_box_width_km=25,cold_start_km=[0,0],
        phase_rounds=5,position_iterations_per_round=48,workers=10,per_case_seconds=400,
        constrained_rounds=5,constrained_iterations=40,constrained_trigger_minimum_slack=-.25,
        no_GPS=True,no_future_TLE=True,confirmation_disjoint_same_site_previously_inspected=True)
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    if path.exists() and read(path)!=d:raise ValueError('frozen catalogue-reentry protocol changed')
    if not path.exists():write(path,d)
    return d


def catalogue_offers(p,x,powers,all_means,widths,hyper,group):
    scan=p.scan;state=p.state(x);data=[]
    for k in group['rows']:
        i=p.members[k];t=scan.tracks[i];q=t['rf_hz']/11.5e9
        values=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        data.append(dict(row=k,times=t['times'],q=q,values=values,white=whitening(t['times']),power=powers[k]))
    times=np.unique(np.concatenate([d['times'] for d in data]));n=len(scan.norads)
    best=np.full(n,np.inf);centers=np.zeros(n)
    for phase in np.linspace(-15,15,121):
        f,e=phase_frequency_grid(scan.sky,times,*latlon(x),phase_seconds=phase)
        score=distribution_cost(phase-all_means,widths,hyper['multiplier'],hyper['nu'])
        for d in data:
            ix=np.searchsorted(times,d['times']);terms=profile(d['values'],d['q']*f[:,ix],*d['white'],bias_sigma=300)
            score+=d['power']*terms['cost'];score=np.where(e[:,ix].min(axis=1)>=0,score,np.inf)
        improve=score<best;best[improve]=score[improve];centers[improve]=phase
    offered=[]
    for j in selected_indices(best,group['original_index']):
        if not np.isfinite(best[j]):continue
        bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],velocity_km_s=scan.sky['velocity_km_s'][[j]])
        local=None
        for phase in np.unique(np.r_[centers[j],np.arange(max(-15,centers[j]-.5),min(15,centers[j]+.5)+.001,.05)]):
            f,e=phase_frequency_grid(bank,times,*latlon(x),phase_seconds=phase)
            score=float(distribution_cost(phase-all_means[j],widths[j],hyper['multiplier'],hyper['nu']));aliases=[];rms=[]
            for d in data:
                ix=np.searchsorted(times,d['times']);terms=profile(d['values'],d['q']*f[:,ix],*d['white'],bias_sigma=300)
                score+=d['power']*float(terms['cost'][0]);aliases.append(int(terms['alias'][0]));rms.append(float(terms['rms'][0]))
                if e[:,ix].min()<0:score=np.inf
            if np.isfinite(score) and (local is None or score<local['proposal_score']):
                local=dict(candidate_index=int(j),norad=int(scan.norads[j]),phase_s=float(phase),
                    proposal_score=score,aliases=aliases,curve_RMS_hz=rms)
        if local:offered.append(local)
    return offered


def run(case):
    path=BULK/(case+'.json')
    if path.exists():return dict(case=case,cached=True,status=read(path)['status'])
    protocol=prepare();started=time.monotonic();record=dict(case=case,trials=[])
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('400second catalogue-reentry budget')))
    signal.alarm(protocol['per_case_seconds'])
    try:
        scan,node,mask,powers,means,hyper,entries,signed,signed_path=context_signed(case)
        incumbent=signed['policy_arms'];record.update(incumbent_arms=incumbent,policy_arms=incumbent)
        occupied=set();lookup={t['key']:t for t in scan.tracks};null={}
        from evaluate_ds23_phase_refreshed import extend_associations
        for arm in ARMS:
            r=incumbent[arm];p=make(scan,node,mask,arm,r['phase_reference'],powers,means,hyper,entries)
            x=np.array(r['endpoint_east_north_km']);delta=p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('signed incumbent failed RF replay')
            m=summary(p,x,entries)['gates'];extended=extend_associations(p,x,m)
            occupied.update(ownership([dict(v,observation_ids=v.get('observation_ids',lookup[v['component']]['observation_ids'])) for v in extended['tracks']]))
            null[arm]=delta
        p=make(scan,node,mask,'c0',incumbent['c0']['phase_reference'],powers,means,hyper,entries)
        widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
        all_means=forecast_phase_mean(receipts,hyper['shrinkage'])
        if signed['accepted']:all_means=adjust_means(all_means,receipts,hyper,signed['selection'])
        np.testing.assert_allclose(all_means[p.labels],means,atol=1e-12,rtol=0)
        groups=complete_groups(p,occupied)[:2];chosen=None
        for group in groups:
            offers=catalogue_offers(p,np.array(incumbent['c0']['endpoint_east_north_km']),powers,all_means,widths,hyper,group)
            write(BULK/(case+f"_group{group['original_index']}_offers.json"),dict(group=group,offers=offers))
            mask2=mask.copy()
            for k in group['rows']:mask2[p.slices[k]]=True
            accepted=[]
            for offer in offers:
                changed=copy.deepcopy(node)
                for k,alias in zip(group['rows'],offer['aliases'],strict=True):
                    row=changed['seed']['rows'][k];row.update(candidate_index=offer['candidate_index'],candidate_norad=offer['norad'])
                    changed['aliases'][k]=alias
                labels=sorted({r['candidate_index'] for r in changed['seed']['rows']})
                if {e['candidate_index'] for e in entries}-set(labels):continue
                means2=all_means[labels];pair={}
                for arm in ARMS:
                    pair[arm]=refit(scan,changed,mask2,arm,powers,means2,hyper,[],entries);gc.collect()
                good=valid(pair);constraint_receipt=dict(attempted=False)
                if not good:
                    from probe_algo03_feasible_recovery import gate_slacks
                    from probe_ds23_gate_retention_cohort import constrained
                    minima=[]
                    for arm in ARMS:
                        trial_problem=make(scan,changed,mask2,arm,pair[arm]['phase_reference'],powers,means2,hyper,entries)
                        minima.append(min(gate_slacks(trial_problem,np.asarray(pair[arm]['endpoint_east_north_km']),entries).values()))
                    constraint_receipt['minimum_unconstrained_slacks']=minima
                    if min(minima)>=-.25:
                        before=pair;pair=constrained(scan,changed,mask2,powers,means2,hyper,entries,pair)
                        good=valid(pair);constraint_receipt.update(attempted=True,unconstrained_arms=before)
                trial=dict(group=group,offer=offer,arms=pair,paired_valid=good,constraint_receipt=constraint_receipt,
                    mask=mask2,node=changed,means=means2)
                record['trials'].append(trial)
                if good:accepted.append(trial)
                write(BULK/(case+'_checkpoint.json'),record)
            if accepted:
                chosen=min(accepted,key=lambda t:t['arms']['c0']['negative_twice_elbo']);break
        record.update(status='complete',selected=chosen,policy_arms=chosen['arms'] if chosen else incumbent,
            original_mask=mask,powers=powers,entries=entries,hyper=hyper,original_means=means,
            signed_incumbent_path=str(signed_path.relative_to(ROOT)),signed_incumbent_sha256=sha(signed_path),
            null_RF_replay_differences=null,no_GPS=True,no_future_TLE=True)
    except Exception as exc:record.update(status='budget_exhausted' if isinstance(exc,TimeoutError) else 'failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-started;record['protocol_sha256']=sha(OUT/'protocol.json')
    write(path,record);gc.collect();result=dict(case=case,status=record['status'],accepted=bool(record.get('selected')),seconds=record['seconds'],error=record.get('error'))
    print(result,flush=True);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','engineering','development','confirmation'],required=True)
    args=parser.parse_args();protocol=prepare()
    if args.stage=='prepare':return
    receipts=[]
    with ProcessPoolExecutor(max_workers=min(10,len(protocol[args.stage]))) as pool:
        for f in as_completed([pool.submit(run,c) for c in protocol[args.stage]]):
            receipts.append(f.result());write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,total=len(protocol[args.stage])))
    write(OUT/(args.stage+'_execution.json'),dict(receipts=receipts,all_terminal=True))


if __name__=='__main__':main()
