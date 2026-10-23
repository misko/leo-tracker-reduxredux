"""Native propagation and bounded physical step diagnostics for frozen cases."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from types import SimpleNamespace
import argparse
import contextlib
import signal
import time
import numpy as np
import experiment as exp
from experiment import OUT,SOURCE,CASES,ARMS,context,apply_trial,paths,preserve,qualifies,coverage
import probe_ds23_iteration010_path_feasibility as feasible
from probe_ds23_frequency_events import refit,summary
from ds23_frequency_events import make_event_problem,attach_event_predictive,extend_event_associations
from audit_ds23_algo01_coverage import retained_metrics
from dbg01_unassociated import ownership
from run_algo01_ds23_sample import read,write,sha


def native(case):
    d,frozen=context(case);records={};directory=OUT/'raw'/case
    choices={'norescue':read(directory/'norescue.json')['selected'],
             'common_family_rank':read(directory/'ranking.json')['selected']}
    for name,t in choices.items():
        if t is None or t.get('name')=='reference':
            parent=d;cov=frozen['reference']['coverage'];kind='default'
        else:
            parent=apply_trial(d,t);cov=t['coverage'];kind=t['kind']
        folder=directory/name;folder.mkdir(exist_ok=True)
        paths.OUT=folder/'native';paths.OUT.mkdir(exist_ok=True)
        paths.runner=SimpleNamespace(configure=lambda:None)
        paths.parent=lambda _:(parent,cov,kind,t)
        paths.one(case)
        primary=read(paths.OUT/(case+'.json'))['methods']['persistent5s']
        feasible.OUT=folder/'native_feasibility';feasible.OUT.mkdir(exist_ok=True)
        feasible.binding=SimpleNamespace(configure=lambda:None,paths=paths,OUT=paths.OUT)
        feasible.one(case);signal.alarm(0)
        rescue=read(feasible.OUT/(case+'.json'));chosen=rescue if rescue.get('accepted') else primary
        final=parent;final_cov=cov
        if chosen.get('accepted'):
            fragments=chosen.get('selected_paths') or read(paths.OUT/(case+'_persistent5s_selection.json'))['selected']
            scan,entries=paths.native.append_native_paths(parent['scan'],parent['entries'],fragments,paths.native.receiver_basis(parent['scan']))
            final=dict(parent,scan=scan,entries=entries,arms=chosen['arms']);final_cov=chosen['coverage']
            assert preserve(frozen['reference']['coverage'],final_cov) and preserve(cov,final_cov)
        records[name]=dict(arms=final['arms'],coverage=final_cov,parent_arms=parent['arms'],parent_coverage=cov,
            parent_name=t.get('name','reference') if t else 'reference',native_accepted=bool(chosen.get('accepted')),
            native_constrained_rescue=bool(rescue.get('accepted')),audit=exp.audit(final,kind,final['arms']))
        write(directory/'native.json',dict(case=case,methods=records,downstream_native_algorithm_unchanged=True))
        print(case,name,records[name]['parent_name'],'native',records[name]['native_accepted'],flush=True)


def step_proposal(times,residual,sigma):
    times=np.asarray(times);residual=np.asarray(residual);sigma=np.asarray(sigma)
    if len(times)<16:return None
    a=np.column_stack((np.ones(len(times)),times-times.mean()))/sigma[:,None]
    y=residual/sigma;baseline=y-a@np.linalg.lstsq(a,y,rcond=None)[0]
    trials=[]
    for cut in range(8,len(times)-7):
        indicator=(np.arange(len(times))>=cut).astype(float)/sigma
        z=indicator-a@np.linalg.lstsq(a,indicator,rcond=None)[0]
        info=float(z@z)
        if info<1e-12:continue
        amplitude=float(z@baseline/info);gain=float((z@baseline)**2/info)
        trials.append(dict(cut=cut,time_s=float((times[cut-1]+times[cut])/2),amplitude_hz=amplitude,
            improvement_chi2=gain,standard_error_hz=1/np.sqrt(info),trials=len(times)-15))
    return max(trials,key=lambda r:r['improvement_chi2']) if trials else None


def combine_ownership(extended,explicit):
    keys={e['component'] for e in explicit};ids=ownership(explicit)
    rows=[r for r in extended if r['compatible'] and r['component'] not in keys and not ids.intersection(r['observation_ids'])]
    return rows+explicit


def event_coverage(d,arm,saved,events):
    p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(saved['phase_reference']),d['powers'],d['means'],d['model'],events)
    attach_event_predictive(p,d['entries'],d['powers']);x=np.asarray(saved['endpoint_east_north_km'])
    assert abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])<1e-5
    extended=extend_event_associations(p,x,retained_metrics(p,x));lookup={t['key']:t for t in d['scan'].tracks}
    rows=[dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']]
    # Preserve explicit predictive entries and check their original gates.
    explicit=[dict(e,compatible=g['compatible']) for e,g in zip(d['entries'],saved['linear_gates'],strict=True)]
    rows=combine_ownership(rows,explicit)
    ids=ownership(rows);allids={o['observation_id'] for o in d['observations']};assert ids<=allids
    return dict(associated=len(ids),total_GLRT=len(allids),percent=100*len(ids)/len(allids),accepted_observation_ids=sorted(ids))


def physical(case):
    d,frozen=context(case);old=frozen['graph']['selected'];directory=OUT/'raw'/case
    assert old is not None and frozen['graph']['kind']=='default'
    dd=apply_trial(d,old)
    ordinary=read(directory/'norescue.json')['trials']
    matched=[t for t in ordinary if t['kind']=='default' and t['additions']==old['additions']]
    assert len(matched)==1
    initial=matched[0]['unconstrained_initial_arms'];p=paths.build(dd,'default','c0',initial['c0']['phase_reference'])
    x=np.asarray(initial['c0']['endpoint_east_north_km']);c=p.calculate(x);added={a['component'] for a in old['additions']}
    proposals=[];tracks=[]
    native_lookup={o['observation_id']:o['measured_cfo_hz'] for o in d['observations']}
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        track=p.scan.tracks[i];use=dd['keep'][sl]
        if not use.any():continue
        record=dict(component=track['key'],receiver=track['receiver'],channel=track['channel'],norad=row['candidate_norad'],
            candidate_index=row['candidate_index'],times=track['times'][use],points=int(use.sum()),
            residual_hz=c['conditional_residual_hz'][sl][use],sigma_hz=p.point_noise[sl][use],added=track['key'] in added,
            native_CFO_hz=np.array([native_lookup[o] for o in track['observation_ids']])[use],pieces=track['pieces'])
        tracks.append(record)
        if record['added']:
            proposal=step_proposal(record['times'],record['residual_hz'],record['sigma_hz'])
            if proposal:proposals.append(dict(proposal,component=record['component'],receiver=record['receiver'],candidate_index=record['candidate_index'],norad=record['norad']))
    best=max(proposals,key=lambda r:r['improvement_chi2']) if proposals else None
    if best is None:
        write(directory/'physical.json',dict(case=case,no_eligible_step=True,tracks=tracks));return
    tau=best['time_s'];target=next(t for t in tracks if t['component']==best['component']);witnesses=[]
    for track in tracks:
        if track['added'] or track['norad']==best['norad'] or track['receiver']!=best['receiver']:continue
        times=track['times'];left=(times<tau)&(times>=tau-20);right=(times>=tau)&(times<=tau+20)
        if min(left.sum(),right.sum())<3:continue
        use=left|right;t=times[use];sigma=track['sigma_hz'][use];y=track['residual_hz'][use]/sigma
        a=np.column_stack((np.ones(len(t)),t-t.mean(),t>=tau))/sigma[:,None]
        coef=np.linalg.lstsq(a,y,rcond=None)[0];cov=np.linalg.inv(a.T@a)
        witnesses.append(dict(component=track['component'],norad=track['norad'],channel=track['channel'],
            amplitude_hz=float(coef[-1]),standard_error_hz=float(np.sqrt(cov[-1,-1])),
            same_sign=bool(coef[-1]*best['amplitude_hz']>0),
            overlaps_target_interval=True,descriptive_conditional_residual_fit_not_independent_calibration=True))
    receiver_support=len({w['norad'] for w in witnesses if w['same_sign'] and abs(w['amplitude_hz'])>2*w['standard_error_hz']})>=2
    owners={(t['receiver'],t['channel']) for t in tracks if t['norad']==best['norad'] and not t['added'] and
            sum(t['times']<tau)>=3 and sum(t['times']>=tau)>=3}
    family_support=len({rx for rx,ch in owners})>=2
    search_penalty=float(2*np.log(max(1,sum(t['trials'] for t in proposals))*3))
    variants={'null':[],
        'receiver_step':[dict(kind='receiver',receiver=best['receiver'],time_s=tau,sigma_hz=300.)],
        'family_step':[dict(kind='family',candidate_index=best['candidate_index'],time_s=tau,sigma_hz=300.)]}
    results={}
    for name,events in variants.items():
        pair={a:refit(dd['scan'],dd['node'],dd['keep'],a,dd['powers'],dd['means'],dd['model'],events,dd['entries']) for a in ARMS}
        cov={a:event_coverage(dd,a,s,events) for a,s in pair.items()}
        results[name]=dict(arms=pair,coverage=cov,paired_valid=qualifies(pair),parent_IDs_preserved=preserve(frozen['reference']['coverage'],cov),events=events)
        print(case,'physical',name,results[name]['paired_valid'],flush=True)
    for name,r in results.items():
        r['same_mask_gain']={a:results['null']['arms'][a]['negative_twice_elbo']-r['arms'][a]['negative_twice_elbo'] for a in ARMS}
        r['witness_supported']=receiver_support if name=='receiver_step' else family_support if name=='family_step' else False
        r['eligible_for_further_validation']=bool(name!='null' and r['paired_valid'] and r['parent_IDs_preserved'] and r['witness_supported'] and all(g>search_penalty for g in r['same_mask_gain'].values()))
    write(directory/'physical.json',dict(case=case,proposal=best,all_proposals=proposals,tracks=tracks,witnesses=witnesses,
        receiver_support=receiver_support,family_cross_receiver_support=family_support,search_penalty=search_penalty,results=results,
        source_of_residual='ordinary unconstrained initial cold fit, same selected graph mask',
        no_GPS_or_TLE_change=True,no_candidate_adopted_automatically=True,
        witness_screen_is_descriptive_not_full_independent_cross_validation=True))


def worker(case,stage):
    start=time.monotonic();folder=OUT/'raw'/case
    with (folder/(stage+'.log')).open('w') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded followup stage')));signal.alarm(600)
            globals()[stage](case);record=dict(case=case,status='complete',seconds=time.monotonic()-start)
        except Exception as exc:
            import traceback
            record=dict(case=case,status='failed',error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-start)
        finally:signal.alarm(0)
    write(folder/(stage+'_status.json'),record);return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['native','physical']);args=parser.parse_args()
    protocol=dict(source_sha256=sha(Path(__file__)),native_cases=CASES,physical_cases=CASES[:3],
        physical_selection='largest affine-adjusted residual step improvement on selected recovered curve, ordinary c0 fit; no GPS',
        step_prior_sigma_hz=300,physical_same_mask_null_receiver_family=True,matched_phase_rounds5_iterations48=True,
        physical_models_never_auto_adopted=True,independent_family_significance_screen_is_descriptive=True,
        native_stage='unchanged persistent5s selection and near-feasible rescue on each newly selected parent')
    protocol.update(previous_protocol_sha256=sha(OUT/'followup_protocol.json'),
        coverage_adapter_repair='explicit predictive ownership takes precedence over duplicate post-fit extension, same as original paths.coverage; no scientific fit or gate change')
    path=OUT/'followup_protocol_v2.json'
    if path.exists():assert read(path)==protocol
    else:write(path,protocol)
    cases=CASES if args.stage=='native' else CASES[:3]
    with ProcessPoolExecutor(max_workers=len(cases)) as pool:
        rows=[]
        for future in as_completed([pool.submit(worker,c,args.stage) for c in cases]):
            row=future.result();rows.append(row);print(row,flush=True)
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
