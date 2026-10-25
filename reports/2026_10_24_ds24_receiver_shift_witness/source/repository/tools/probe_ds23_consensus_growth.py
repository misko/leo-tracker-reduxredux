"""Complete-curve shared-phase reentry before alternative-family relabeling.

Inference reads causal inputs and original RF nominations, never GPS or future
elements. Geographic reporting lives in a separate evaluator.
"""

import argparse
import copy
import gc
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

import numpy as np

from ds23_consensus_growth import choose_consensus,eligible_curve
from dbg01_unassociated import ownership,candidate_gates
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from learn_ds23_causal_phase_forecast import distribution_cost
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached,refit,summary
from probe_ds23_sign_carrier_position import context_signed
from run_ds23_combined_recovery_full import ARMS,valid
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import profile,whitening
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_consensus_growth'
BULK=Path('/srv/bulk/leo/research/ds23-consensus-growth-20261021')


def hashes():
    return {n:sha(ROOT/'tools'/n) for n in ['probe_ds23_consensus_growth.py','ds23_consensus_growth.py']}


def prepare():
    path=OUT/'protocol.json'
    if path.exists():
        d=read(path)
        if d['source_sha256']!=hashes():raise ValueError('frozen consensus-growth source changed')
        return d
    from run_ds23_combined_recovery_full import OUT as COMBINED
    available=read(COMBINED/'protocol.json')['available_cases']
    pool=[c for c in available if c not in ['DS23-0268','DS23-0405']]
    rng=np.random.default_rng(8675309);chosen=rng.choice(pool,28,replace=False).tolist()
    d=dict(engineering=['DS23-0268','DS23-0405'],development=sorted(chosen[:8]),confirmation=sorted(chosen[8:]),
        seed=8675309,selection_reads_no_position_errors=True,
        confirmation_scan_disjoint_but_previously_studied_same_site_not_new_location=True,
        source_sha256=hashes(),minimum_added_points_per_curve=12,minimum_span_s=10,
        minimum_distinct_new_receiver_channel_owners=2,
        nominations='every original RF-nominated inactive curved family, before ranking identity-replacement gains',
        common_phase_coarse_step_s=.25,common_phase_refined_step_s=.05,refined_half_width_s=.5,
        maximum_joint_family_offers=3,selection='most added complete points then candidate catalogue index',
        preserve_original_curved_and_predictive_observation_IDs=True,
        curve_gate_noise_scale_hz=150,fragment_constant_prior_hz=300,
        all_original_noise_powers_physical_priors_aliases_for_incumbent_points_unchanged=True,
        cold_start_east_north_km=[0,0],regional_center=[37.906,-122.545],box_width_km=25,
        phase_rounds=5,position_iterations_per_round=48,
        acceptance='both c arms pass unchanged original gates, phases within15s and final phase change<=.01s',
        fallback='exact signed-prior incumbent pair',no_GPS=True,no_following_TLE=True,
        per_case_seconds=300,workers=10,publish_only_if_both_position_metrics_improve_on_confirmation=True)
    OUT.mkdir(parents=True,exist_ok=True);BULK.mkdir(parents=True,exist_ok=True);write(path,d)
    return d


def make(scan,node,mask,arm,reference,powers,means,hyper,entries):
    p=make_event_problem(scan,node,mask,arm,np.array(reference),powers,means,hyper,[])
    attach_event_predictive(p,entries,powers)
    return cached(p)


def nominate(p,x,powers,hyper,occupied):
    scan=p.scan;state=p.state(x);groups={}
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        t=scan.tracks[i]
        if not eligible_curve(t,p.keep[sl],occupied):continue
        q=t['rf_hz']/11.5e9
        y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        groups.setdefault(row['candidate_index'],[]).append(dict(row_index=k,component=t['key'],
            receiver=t['receiver'],channel=t['channel'],points=len(t['times']),times=t['times'],
            corrected=y,q=q,power=float(powers[k]),white=whitening(t['times'])))
    labels=sorted(groups);widths,receipts=phase_widths(scan,labels)
    means=forecast_phase_mean(receipts,hyper['shrinkage']);offers=[];screens=[]
    for position,j in enumerate(labels):
        rows=groups[j]
        if len({(r['receiver'],r['channel']) for r in rows})<2:continue
        sub=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],velocity_km_s=scan.sky['velocity_km_s'][[j]])
        times=np.unique(np.concatenate([r['times'] for r in rows]))
        def grid(phases):
            results=[dict(r,passing=[],cost=[],aliases=[]) for r in rows]
            for phase in phases:
                frequency,elevation=phase_frequency_grid(sub,times,*latlon(x),phase_seconds=phase)
                for r,result in zip(rows,results,strict=True):
                    ix=np.searchsorted(times,r['times'])
                    terms=profile(r['corrected'],r['q']*frequency[:,ix],*r['white'],bias_sigma=300)
                    passed,_=candidate_gates(terms,elevation[:,ix],r['times'])
                    result['passing'].append(bool(passed[0]));result['cost'].append(float(terms['cost'][0]))
                    result['aliases'].append(int(terms['alias'][0]))
            prior=distribution_cost(np.asarray(phases)-means[position],widths[position],hyper['multiplier'],hyper['nu'])
            return choose_consensus(phases,results,prior),results
        coarse=np.linspace(-15,15,121);offer,results=grid(coarse)
        if offer:
            phases=np.unique(np.r_[coarse,np.arange(max(-15,offer['phase_s']-.5),min(15,offer['phase_s']+.5)+.001,.05)])
            offer,results=grid(phases)
            offer.update(candidate_index=int(j),norad=int(scan.norads[j]))
            offers.append(offer)
        screens.append(dict(candidate_index=int(j),norad=int(scan.norads[j]),eligible_components=[r['component'] for r in rows],
            points=sum(r['points'] for r in rows),offer=offer))
    offers.sort(key=lambda o:(-o['added_points'],o['candidate_index'],o['row_indices']))
    return offers[:3],screens


def run(case):
    destination=BULK/(case+'.json')
    if destination.exists():return dict(case=case,cached=True,status=read(destination)['status'])
    protocol=prepare();began=time.monotonic();record=dict(case=case,status='failed',trials=[])
    def timeout(*_):raise TimeoutError('300second consensus-growth budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(protocol['per_case_seconds'])
    try:
        scan,node,mask,powers,means,hyper,entries,signed,signed_path=context_signed(case)
        incumbent=signed['policy_arms'];policy=incumbent;selected=None;occupied=set();null={}
        track_lookup={t['key']:t for t in scan.tracks}
        for arm in ARMS:
            old=incumbent[arm];p=make(scan,node,mask,arm,old['phase_reference'],powers,means,hyper,entries)
            x=np.array(old['endpoint_east_north_km']);delta=p.calculate(x)['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('signed incumbent RF replay failed')
            metrics=summary(p,x,entries)['gates']
            from evaluate_ds23_phase_refreshed import extend_associations
            extended=extend_associations(p,x,metrics)
            rows=[dict(r,observation_ids=r.get('observation_ids',track_lookup[r['component']]['observation_ids'])) for r in extended['tracks']]
            occupied.update(ownership(rows));null[arm]=delta
        p=make(scan,node,mask,'c0',incumbent['c0']['phase_reference'],powers,means,hyper,entries)
        offers,screens=nominate(p,np.array(incumbent['c0']['endpoint_east_north_km']),powers,hyper,occupied)
        write(BULK/(case+'_offers.json'),dict(case=case,offers=offers,screens=screens,occupied_original_ids=sorted(occupied)))
        for offer in offers:
            offered=mask.copy();changed=copy.deepcopy(node)
            for k in offer['row_indices']:
                offered[p.slices[k]]=True;changed['aliases'][k]=offer['aliases'][k]
            pair={}
            for arm in ARMS:
                pair[arm]=refit(scan,changed,offered,arm,powers,means,hyper,[],entries)
                gc.collect()
            accepted=valid(pair)
            trial=dict(offer=offer,arms=pair,accepted=accepted,mask=offered,node=changed)
            record['trials'].append(trial)
            if accepted:policy=pair;selected=trial;break
            write(BULK/(case+'_checkpoint.json'),record)
        record.update(status='complete',policy_arms=policy,incumbent_arms=incumbent,
            selected_offer=selected['offer'] if selected else None,
            selected_mask=selected['mask'] if selected else mask,
            selected_node=selected['node'] if selected else node,
            original_mask=mask,powers=powers,means=means,hyper=hyper,entries=entries,
            signed_incumbent_path=str(signed_path.relative_to(ROOT)),signed_incumbent_sha256=sha(signed_path),
            null_RF_replay_differences=null,all_original_curved_points_retained=True,
            all_original_predictive_entries_unchanged=True,no_GPS=True,no_following_TLE=True)
    except Exception as exc:
        record.update(status='budget_exhausted' if isinstance(exc,TimeoutError) else 'failed',error=repr(exc))
        if 'incumbent' in locals():record.update(policy_arms=incumbent,incumbent_arms=incumbent)
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-began;record['protocol_sha256']=sha(OUT/'protocol.json')
    write(destination,record);gc.collect()
    result=dict(case=case,status=record['status'],accepted=bool(record.get('selected_offer')),seconds=record['seconds'])
    print(result,flush=True);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['prepare','engineering','development','confirmation'],required=True)
    args=parser.parse_args();protocol=prepare()
    if args.stage=='prepare':return
    cases=protocol[args.stage];began=time.monotonic();receipts=[]
    with ProcessPoolExecutor(max_workers=min(10,len(cases))) as pool:
        futures=[pool.submit(run,c) for c in cases]
        for f in as_completed(futures):
            receipts.append(f.result());write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,total=len(cases),seconds=time.monotonic()-began))
    write(OUT/(args.stage+'_execution.json'),dict(receipts=receipts,all_terminal=True,seconds=time.monotonic()-began))


if __name__=='__main__':main()
