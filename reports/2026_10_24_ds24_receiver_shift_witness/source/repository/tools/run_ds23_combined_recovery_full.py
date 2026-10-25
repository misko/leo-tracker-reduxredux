"""Frozen, GPS-free DS23 combined recovery; report-side geography is separate."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time

import numpy as np

from algo02_scan import bind_run_directory, load_scan, pair_passes, validate_history
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_receiver_family_search import fine_receiver_basis, orphan_predictive_labels
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import cached, refit, summary
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_algo02_ds23 import DEFAULT_RUN, verify_freeze
from verify_ds23_recovered_positions import RUNS
from leo.analysis.research.retained_track_likelihood import PERIOD, profile

OUT = ROOT/'reports/2026_10_20_ds23_combined_recovery_full'
ARMS = ('c0', 'fitted_c')


def source_hashes():
    names = ('run_ds23_combined_recovery_full.py', 'ds23_combined_recovery_search.py',
             'ds23_frequency_events.py', 'ds23_receiver_family_search.py',
             'probe_ds23_frequency_events.py', 'probe_ds23_gate_retention_cohort.py',
             'ds23_feasible_position.py', 'probe_algo03_feasible_recovery.py')
    return {name: sha(ROOT/'tools'/name) for name in names}


def prepare():
    verify_freeze(DEFAULT_RUN)
    path = OUT/'protocol.json'
    if path.exists():
        protocol = read(path)
        if protocol['source_sha256'] != source_hashes():
            raise ValueError('combined recovery inference source changed after freeze')
        return protocol
    cases = [r['dataset_label'] for r in read(DEFAULT_RUN/'sample.json')['selected']]
    roots = {}
    for case in cases:
        root = RUNS.get(case, DEFAULT_RUN)
        result = root/case/'algo02_result.json'
        if result.exists() and read(result).get('status') == 'accepted':
            roots[case] = str(root)
    protocol = dict(cases=cases, available_cases=sorted(roots),
        missing_cases=sorted(set(cases)-set(roots)), input_roots=roots,
        baseline_sha256={c:sha(Path(r)/c/'algo02_result.json') for c,r in roots.items()},
        source_sha256=source_hashes(), workers=30, per_scan_seconds=900,
        catalogue='all causal candidates in original scan bank; no satellite whitelist',
        original_GLRT_graph_and_noise_unchanged=True, original_observations_never_removed=True,
        regional_center=[37.906,-122.545], regional_box_width_km=25, cold_start_km=[0,0],
        paired_c0_fitted_c=True, linear_measurements_do_not_calibrate=True,
        fine_basis=dict(spacing_s=10,width_s=15,average_prior_variance_matched=True),
        event=dict(maximum=1,prior_sigma_hz=300,minimum_spanning_channels=2,
                   minimum_points_each_side=3,coarse_grid_s=[10,290,2],refined_step_s=.25,
                   focus='longest original graph curve without any accepted original point'),
        catalogue_alternatives_maximum=5,growth_rounds_maximum=4,growth_offers_per_round_maximum=2,
        phase_rounds=5,position_iterations=48,constrained_rounds=5,
        constrained_iterations=40,constrained_minimum_slack_trigger=-.25,
        constrained_interior=.01,phase_bounds_s=[-15,15],
        same_mask_selection='paired original gates; c0 RF gain exceeds discrete search penalty; fitted-c RF gain positive',
        growth_selection='complete original curved rows; paired unchanged gates; retain all incumbent observations; prefer most added points then proposal cost; no raw score comparison across masks',
        growth_calibration_support='existing supported family or at least two receiver/channel owners',
        GPS_used=False,post_scan_TLE_used=False,cross_scan_RF_position_prior=False,
        engineering_case_previously_inspected='DS23-0268',
        full_population_is_same_site_not_new_location_validation=True)
    OUT.mkdir(parents=True,exist_ok=True);write(path,protocol)
    return protocol


def context(case):
    root=Path(read(OUT/'protocol.json')['input_roots'][case]);bind_run_directory(root)
    scan=load_scan(root,case)
    raw=read(root/case/'result.json');old=read(root/case/'algo02_result.json')
    forecast=root/'causal_phase_history'/(case+'_forecast.json')
    history=root/'causal_phase_history'/(case+'.json')
    hyper,_=validate_history(read(history),read(forecast),scan,sha(history))
    if hyper!=old['hyperparameters_from_pre_RF_TLE_only']:
        raise ValueError('original historical physical prior changed')
    node=raw['final_node'];mask=np.asarray(old['mask'],bool)
    return scan,node,mask,problem(scan,node,'c0',mask),old


def model_scan(scan,config):
    if not config['fine_basis']:return scan
    fine=copy.copy(scan)
    fine.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    return fine


def make(scan,config,arm,reference):
    labels=sorted({r['candidate_index'] for r in config['node']['seed']['rows']})
    p=make_event_problem(model_scan(scan,config),config['node'],np.asarray(config['mask'],bool),
        arm,np.asarray(reference),np.asarray(config['powers']),np.asarray(config['means'])[labels],
        config['hyper'],config['events'])
    attach_event_predictive(p,config['entries'],np.asarray(config['powers']))
    return cached(p)


def reconstruct(case,record,arm):
    scan,*_=context(case);config=record['policy_model'];saved=record['policy_arms'][arm]
    return make(scan,config,arm,saved['phase_reference']),np.asarray(saved['endpoint_east_north_km']),config['entries']


def valid(pair):
    if not pair_passes(pair,include_linear=True):return False
    return all(np.max(np.abs(np.asarray(r['state']['phases'])))<=15.000001 for r in pair.values())


def growth_supported(p,offer):
    """Existing curved support or two owners, independent of orbit-mode support."""
    j=offer['candidate_index'];rows=set(offer.get('rows',offer.get('row_indices',[])))
    retained=False;owners=set()
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        active=row['candidate_index']==j and np.asarray(p.keep[sl]).any()
        retained=retained or active
        if active or k in rows:
            track=p.scan.tracks[i];owners.add((track['receiver'],track['channel']))
    return bool(retained or len(owners)>=2)


def trial(scan,config):
    labels=sorted({r['candidate_index'] for r in config['node']['seed']['rows']})
    pair={a:refit(model_scan(scan,config),config['node'],np.asarray(config['mask'],bool),a,
        np.asarray(config['powers']),np.asarray(config['means'])[labels],config['hyper'],
        config['events'],config['entries']) for a in ARMS}
    receipt=dict(constrained=False,paired_valid=valid(pair))
    if receipt['paired_valid']:return pair,receipt
    from ds23_feasible_position import feasible_fit
    from probe_algo03_feasible_recovery import gate_slacks
    minima=[]
    for a in ARMS:
        p=make(scan,config,a,pair[a]['phase_reference'])
        minima.append(min(gate_slacks(p,np.asarray(pair[a]['endpoint_east_north_km']),config['entries']).values()))
    receipt['unconstrained_minimum_slacks']=minima
    if min(minima)<-.25:return pair,receipt
    for a in ARMS:
        x=np.asarray(pair[a]['endpoint_east_north_km']);reference=np.asarray(pair[a]['phase_reference']);history=[]
        for epoch in range(5):
            p=make(scan,config,a,reference)
            fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.asarray(list(gate_slacks(p,z,config['entries']).values()))-.01,
                x,p.lower,p.upper,iterations=40)
            x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            change=float(np.max(abs(phase-reference)))
            history.append(dict(fit=fitted,phase_change_s=change));reference=phase
        pair[a]=dict(summary(p,x,config['entries']),history=history,final_phase_change_s=change)
    receipt.update(constrained=True,paired_valid=valid(pair))
    return pair,receipt


def detect_event(p,x,powers,entries):
    """Original RF-only shared-step proposal; all decisions precede GPS evaluation."""
    scan=p.scan;state=p.state(x);frequency,elevation=p.conditional_frequency(x)
    owned={oid for i,sl in zip(p.members,p.slices,strict=True)
           for oid,use in zip(scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if use}
    owned.update(oid for e in entries for oid in e['observation_ids'])
    unused=[t for t in scan.tracks if not owned.intersection(t['observation_ids'])]
    if not unused:return dict(events=[],penalty=0,offered_rows=[])
    focus=max(unused,key=lambda t:np.ptp(t['times']));curves=[]
    for k,(row,i,sl,alias) in enumerate(zip(p.rows,p.members,p.slices,p.alias,strict=True)):
        t=scan.tracks[i]
        if len(t['times'])<12 or np.ptp(t['times'])<10:continue
        q=t['rf_hz']/11.5e9
        y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y,q*frequency[sl],*scan.white[i])
        if terms['rms'][0]>750 or abs(terms['bias'][0])>3000 or elevation[sl].min()<0:continue
        curves.append(dict(row=k,component=t['key'],receiver=t['receiver'],channel=t['channel'],
            times=t['times'],raw=y+alias*PERIOD-q*frequency[sl],sigma=p.point_noise[sl]/np.sqrt(powers[k])))
    def evaluate(tau):
        spanning=[r for r in curves if r['receiver']==focus['receiver'] and
                  sum(r['times']<tau)>=3 and sum(r['times']>=tau)>=3]
        if len({r['channel'] for r in spanning})<2:return None
        info=1.;rhs=0.
        for r in spanning:
            w=1/r['sigma'];t=r['times'];affine=np.column_stack((np.ones(len(t)),t-t.mean()))*w[:,None]
            raw=r['raw']*w;u=(t>=tau)*300*w
            raw-=affine@np.linalg.lstsq(affine,raw,rcond=None)[0]
            u-=affine@np.linalg.lstsq(affine,u,rcond=None)[0]
            info+=float(u@u);rhs+=float(u@raw)
        return dict(time_s=float(tau),receiver=focus['receiver'],gain=rhs*rhs/info-np.log(info),
                    amplitude_hz=300*rhs/info,rows=[r['row'] for r in spanning])
    coarse=[r for tau in np.arange(10.,290.01,2.) if focus['times'].min()<tau<focus['times'].max()
            and (r:=evaluate(tau)) is not None]
    if not coarse:return dict(events=[],penalty=0,offered_rows=[],focus=focus['key'])
    center=max(coarse,key=lambda r:r['gain'])['time_s']
    refined=[r for tau in np.arange(max(10,center-2),min(290,center+2)+.01,.25)
             if focus['times'].min()<tau<focus['times'].max() and (r:=evaluate(tau)) is not None]
    best=max(coarse+refined,key=lambda r:r['gain']);penalty=float(2*np.log(max(282,len(coarse)+len(refined))*4))
    events=[dict(kind='receiver',receiver=int(best['receiver']),time_s=best['time_s'],sigma_hz=300.)] if best['gain']>penalty else []
    return dict(events=events,penalty=penalty,best=best,offered_rows=best['rows'] if events else [],focus=focus['key'])


def run_case(case):
    output=OUT/case/'result.json'
    if output.exists():return dict(case=case,cached=True,seconds=read(output)['seconds'])
    started=time.monotonic();protocol=read(OUT/'protocol.json')
    def timeout(*_):raise TimeoutError('frozen per-scan 900 second budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(protocol['per_scan_seconds'])
    scan,node,mask,base,old=context(case)
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
    means=forecast_phase_mean(receipts,old['hyperparameters_from_pre_RF_TLE_only']['shrinkage'])
    config=dict(fine_basis=False,events=[],node=copy.deepcopy(node),mask=mask,
        entries=old['linear_entries'] if old['linear_paired_valid'] else [],powers=old['weights'],
        means=means,hyper=old['hyperparameters_from_pre_RF_TLE_only'])
    policy=old['policy_arms'];chosen=copy.deepcopy(config);stages=[]
    directory=OUT/case;directory.mkdir(parents=True,exist_ok=True)
    def save(status='running',error=None):
        document=dict(case=case,input_root=protocol['input_roots'][case],policy_arms=policy,
            baseline_arms=old['policy_arms'],policy_model=chosen,original_mask=mask,stages=stages,
            status=status,error=error,seconds=time.monotonic()-started,GPS_used=False,future_TLE_used=False,
            source_protocol_sha256=sha(OUT/'protocol.json'),original_points_never_removed=True)
        write(directory/('result.json' if status!='running' else 'checkpoint.json'),document)
        if status!='running':(directory/'checkpoint.json').unlink(missing_ok=True)
    try:
        for a in ARMS:
            p=make(scan,config,a,policy[a]['phase_reference']);delta=p.calculate(np.asarray(policy[a]['endpoint_east_north_km']))['negative_twice_elbo']-policy[a]['negative_twice_elbo']
            if abs(delta)>1e-3:raise ValueError('baseline RF replay mismatch')
        p=make(scan,config,'c0',policy['c0']['phase_reference'])
        event=detect_event(p,np.asarray(policy['c0']['endpoint_east_north_km']),np.asarray(config['powers']),config['entries'])
        write(directory/'event_proposal.json',event)
        # Evaluate both receiver covariance choices on the same original observations.
        fine=copy.deepcopy(config);fine['fine_basis']=True
        fine['node']['seed']['state']['smooth']=np.zeros((2,fine_receiver_basis(scan.tracks[0]['times']).shape[1]))
        pair,receipt=trial(scan,fine)
        gain=policy['c0']['negative_twice_elbo']-pair['c0']['negative_twice_elbo']
        accepted=receipt['paired_valid'] and gain>2*np.log(2) and policy['fitted_c']['negative_twice_elbo']>pair['fitted_c']['negative_twice_elbo']
        stages.append(dict(name='fine_receiver',arms=pair,receipt=receipt,c0_same_mask_gain=gain,accepted=bool(accepted)))
        # Fine covariance remains a proposal model even when its unchanged-mask trial fails.
        working=fine;working_pair=pair
        if accepted:chosen=copy.deepcopy(fine);policy=pair
        save()
        if event['events']:
            candidate=copy.deepcopy(fine);candidate['events']=event['events']
            epair,ereceipt=trial(scan,candidate)
            gain=pair['c0']['negative_twice_elbo']-epair['c0']['negative_twice_elbo']
            incumbent_gain=policy['c0']['negative_twice_elbo']-epair['c0']['negative_twice_elbo']
            penalty=event['penalty']+(0. if chosen['fine_basis'] else 2*np.log(2))
            accepted=ereceipt['paired_valid'] and incumbent_gain>penalty and policy['fitted_c']['negative_twice_elbo']>epair['fitted_c']['negative_twice_elbo']
            stages.append(dict(name='receiver_event',arms=epair,receipt=ereceipt,
                c0_same_mask_gain=incumbent_gain,fine_null_gain=gain,penalty=penalty,accepted=bool(accepted)))
            if accepted:chosen=copy.deepcopy(candidate);policy=epair
            # An event must earn its search penalty before driving later proposals.
            if gain>event['penalty']:working=candidate;working_pair=epair
            save()
        from ds23_combined_recovery_search import screen_blocks, alternatives, apply_recovery_proposals, growth_offers
        p=make(scan,working,'c0',working_pair['c0']['phase_reference'])
        proposals,screen,_,_=screen_blocks(p,np.asarray(working_pair['c0']['endpoint_east_north_km']),np.asarray(working['powers']),working['hyper'],max_blocks=2)
        write(directory/'catalogue_screen.json',screen)
        options=alternatives(proposals,screen)
        for option in options:
            name,changes=option['id'],option['proposals']
            if not changes:continue
            candidate=copy.deepcopy(working)
            try:
                candidate['node'],candidate['entries']=apply_recovery_proposals(working['node'],working['entries'],scan.tracks,changes)
            except ValueError as exc:
                stages.append(dict(name=name,accepted=False,hypothesis_rejected=str(exc)))
                continue
            if orphan_predictive_labels(candidate['node'],candidate['entries']):continue
            alt,receipt=trial(scan,candidate)
            penalty=float(2*len(changes)*np.log(max(2,len(scan.norads)-1))+2*np.log(max(2,len(options))))
            gain=policy['c0']['negative_twice_elbo']-alt['c0']['negative_twice_elbo']
            accepted=receipt['paired_valid'] and gain>penalty and policy['fitted_c']['negative_twice_elbo']>alt['fitted_c']['negative_twice_elbo']
            stages.append(dict(name=name,arms=alt,receipt=receipt,changes=changes,c0_same_mask_gain=gain,penalty=penalty,accepted=bool(accepted)))
            if accepted:chosen=copy.deepcopy(candidate);policy=alt
            save()
        # Reconsider complete original curves under the selected calibrated model.
        # Never compare raw marginal bounds across different observation counts.
        growth_base=chosen if chosen['fine_basis'] else working
        growth_pair=policy if chosen['fine_basis'] else working_pair
        from probe_ds23_gate_retention_cohort import offers
        for growth_round in range(4):
            p=make(scan,growth_base,'c0',growth_pair['c0']['phase_reference'])
            x=np.asarray(growth_pair['c0']['endpoint_east_north_km'])
            original_offers=[o for o in offers(p,x) if growth_supported(p,o)]
            catalogue_offers=growth_offers(p,x,np.asarray(growth_base['powers']),growth_base['hyper'],max_offers=2)
            offers_list=catalogue_offers+[dict(o,rows=o['row_indices']) for o in original_offers]
            # Counts are comparable across proposals; their conditional screening
            # scores are not, so break ties by catalogue order and row identity.
            offers_list.sort(key=lambda o:(-o['added_points'],o['candidate_index'],tuple(o['rows'])))
            eligible=[];seen=set()
            for offer in offers_list:
                key=(offer['candidate_index'],tuple(offer['rows']))
                if key not in seen:eligible.append(offer);seen.add(key)
                if len(eligible)==2:break
            write(directory/('growth_proposals_'+str(growth_round)+'.json'),dict(offers=offers_list))
            gained=False
            for offer in eligible:
                candidate=copy.deepcopy(growth_base);offered=np.asarray(candidate['mask'],bool).copy()
                if offer.get('kind')=='growth':
                    try:
                        candidate['node'],candidate['entries']=apply_recovery_proposals(candidate['node'],candidate['entries'],scan.tracks,[offer])
                    except ValueError as exc:
                        stages.append(dict(name='complete_curve_growth',accepted=False,hypothesis_rejected=str(exc)))
                        continue
                for k in offer['rows']:offered[p.slices[k]]=True
                candidate['mask']=offered
                alt,receipt=trial(scan,candidate)
                accepted=receipt['paired_valid'] and int(offered.sum())>int(np.asarray(chosen['mask']).sum())
                stages.append(dict(name='complete_curve_growth',growth_round=growth_round,proposal=offer,
                    arms=alt,receipt=receipt,accepted=bool(accepted),offered_points=int(offered.sum())))
                if accepted:
                    chosen=copy.deepcopy(candidate);policy=alt;growth_base=chosen;growth_pair=policy;gained=True
                save()
                if gained:break
            if not gained:break
        save('complete')
    except Exception as exc:
        save('budget_exhausted' if isinstance(exc,TimeoutError) else 'failed',repr(exc))
    finally:signal.alarm(0)
    result=read(output)
    receipt=dict(case=case,status=result['status'],seconds=result['seconds'],
        original_points=int(mask.sum()),retained_points=int(np.asarray(chosen['mask']).sum()),
        accepted_stages=[s['name'] for s in stages if s.get('accepted')],error=result['error'])
    print(receipt,flush=True);return receipt


def run(cases,workers):
    protocol=prepare();started=time.monotonic();receipts=[]
    selected=cases or protocol['available_cases']
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures={executor.submit(run_case,c):c for c in selected}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as exc:r=dict(case=futures[future],status='worker_failed',error=repr(exc))
            receipts.append(r);write(OUT/'progress.json',dict(completed=len(receipts),total=len(selected),receipts=receipts,seconds=time.monotonic()-started))
    write(OUT/('pilot_execution.json' if cases else 'execution.json'),dict(receipts=receipts,all_terminal=True,seconds=time.monotonic()-started,missing_cases=protocol['missing_cases']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--cases',nargs='*');parser.add_argument('--workers',type=int,default=30)
    args=parser.parse_args();prepare() if args.prepare_only else run(args.cases,args.workers)
