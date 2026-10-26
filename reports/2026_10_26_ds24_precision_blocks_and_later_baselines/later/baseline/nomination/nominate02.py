"""Apply the unchanged accepted-owner RF rule to terminal retained parents."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import numpy as np

HERE=Path(__file__).resolve().parent;BASE=HERE.parent;WORK=BASE/'work'
STUDY=Path('/srv/bulk/leo/research/ds24-precision-block-transfer-r01')
OLD=Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence')
INFO=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/information')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
sys.path.insert(0,str(INFO))
import ranking
r=ranking.r
sys.path.insert(0,str(BASE))
from selector_v2 import nominate
spec=importlib.util.spec_from_file_location('original_influence_math',OLD/'local_math.py')
local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)
CASES=tuple(f'LATER4-{i:04}' for i in range(1,5));ARMS=('c0','fitted_c')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())


def write(path,value):r.write_new(HERE/path,value)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def alarm(seconds):
    if seconds<=0:raise TimeoutError('remaining original baseline budget exhausted')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('original baseline cumulative cap')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def producer_pair_valid(pair):
    return set(pair)==set(ARMS) and r.algo.pair_passes(pair,include_linear=True)


def context(case,root=WORK):
    """Load explicit saved retained inputs; never call engine.context/refit."""
    saved=read(root/'family_cavity/position'/(case+'.json'))
    if saved['status']!='complete' or not saved.get('reconstructed_fresh_reference'):
        raise ValueError('full retained reference unavailable')
    if not producer_pair_valid(saved['policy_arms']):raise ValueError('retained producer paired reference unqualified')
    selected=saved['selected'] if saved['accepted'] else None
    r.algo.bind_run_directory(root);scan=r.algo.load_scan(root,case)
    for element in scan.elements.values():
        p=element['provenance']
        if max(p['element_epoch_utc_ns'],p['collected_utc_ns'])>scan.receipt['cutoff_utc_ns']:raise ValueError('noncausal catalogue')
    history=root/'causal_phase_history'/(case+'.json');forecast=read(history.with_name(case+'_forecast.json'))
    r.algo.validate_history(read(history),forecast,scan,sha(history))
    if any(t['validation_time_ns']>scan.receipt['cutoff_utc_ns'] for t in forecast['transitions']):raise ValueError('noncausal phase history')
    node=selected['node'] if selected else saved['baseline_node'];active=set();cursor=0
    tracks={t['key']:t for t in scan.tracks}
    for row in node['seed']['rows']:
        n=len(tracks[row['component']]['observation_ids'])
        if any(saved['original_mask'][cursor:cursor+n]):active.add(row['candidate_index'])
        cursor+=n
    phase_diagnostic={}
    for arm in ARMS:
        phases=np.asarray(saved['policy_arms'][arm]['state']['phases'])
        phase_diagnostic[arm]=dict(maximum_unclipped_absolute_phase_s=float(np.max(abs(phases))),
            over15=[dict(candidate_index=int(j),norad=int(scan.norads[j]),phase_s=float(phases[j]),active_curved_family=j in active)
                for j in np.flatnonzero(abs(phases)>15.000001)])
    return dict(case=case,scan=scan,node=node,
        keep=np.asarray(saved['original_mask'],bool),powers=np.asarray(saved['powers']),model=saved['model'],
        means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'],arms=saved['policy_arms'],
        observations=read(root/case/'observations.json'),absolute_phase_diagnostic=phase_diagnostic)


def ledger(d,bases):
    ordered=[];coverage={}
    for arm in ARMS:coverage[arm]=r.membership(d,arm,d['arms'][arm])
    p=bases['c0']['p'];obs={o['observation_id']:o for o in d['observations']}
    if len(obs)!=len(d['observations']):raise ValueError('duplicate original observations')
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        tr=p.scan.tracks[i]
        for oid,used in zip(tr['observation_ids'],p.keep[sl],strict=True):
            if used:ordered.append(dict(observation_id=oid,owner=tr['key'],family=int(row['candidate_norad']),
                time_s=obs[oid]['time_s'],q=tr['rf_hz']/11.5e9,role='curved'))
    lookup={t['key']:t for t in d['scan'].tracks}
    for entry in d['entries']:
        tr=lookup[entry['component']]
        if tr['observation_ids']!=entry['observation_ids']:raise ValueError('predictive whole-owner ID ordering differs')
        ordered +=[dict(observation_id=oid,owner=tr['key'],family=int(entry['norad']),time_s=obs[oid]['time_s'],q=tr['rf_hz']/11.5e9,role='predictive') for oid in entry['observation_ids']]
    ids=[o['observation_id'] for o in ordered]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate likelihood ownership')
    for arm in ARMS:
        if len(ids)!=len(bases[arm]['j']) or set(ids)!=set(coverage[arm]['curved_observation_ids']+coverage[arm]['predictive_observation_ids']):
            raise ValueError('design/curved/predictive/native-ID ordering differs')
    owners=[]
    for track in d['scan'].tracks:
        native=track['observation_ids'];ss=set(native);reasons=[]
        if len(native)!=len(ss):raise ValueError('duplicate original owner ID')
        if len(native)<20:reasons.append('fewer_than_20_original_points')
        if any(not ss<=set(coverage[a]['curved_observation_ids']) for a in ARMS):reasons.append('not_complete_curved_likelihood_in_both_arms')
        ix=[i for i,row in enumerate(ordered) if row['owner']==track['key']]
        families=sorted({ordered[i]['family'] for i in ix})
        owners.append(dict(case=d['case'],owner=track['key'],receiver=track['receiver'],channel=track['channel'],rf_hz=track['rf_hz'],
            points=len(native),start_s=track['start_s'],end_s=track['end_s'],quality_status=track['quality_status'],
            observation_ids=native,family=families[0] if len(families)==1 else None,likelihood_indices=ix,
            eligible=not reasons,exclusion_reasons=reasons,
            role_counts={a:{role:len(ss&set(coverage[a][key])) for role,key in [('curved','curved_observation_ids'),('predictive','predictive_observation_ids'),('postfit_only','postfit_only_observation_ids')]} for a in ARMS}))
    return dict(case=d['case'],owners=owners,ordered_rows=ordered,coverage=coverage,
        absolute_phase_diagnostic=d['absolute_phase_diagnostic'])


def physical_key(recording,session,probe,duration):
    # One paired payload can contain both receivers. Do not count it twice.
    return [recording,session,int(probe['visit_index']),int(probe['probe_index']),int(probe['channel']),
        int(probe['window_start_counter']),int(duration),float(probe['actual_rf_hz'])]


def complete_requests(case,role,owner):
    tracking=read(WORK/case/'tracking.json');obs={o['observation_id']:o for o in read(WORK/case/'observations.json')}
    source=tracking['source'];fs=source['sample_rate_hz'];origin=tracking['clock_anchor']['sample_counter']
    member=next(m for m in read(WORK/'sample.json')['selected'] if m['dataset_label']==case)
    result=[]
    for oid in owner['observation_ids']:
        o=obs[oid]
        matches=[p for p in source['probes'] if p['receiver_id']==o['native_receiver_id'] and p['channel']==o['channel'] and
            abs((p['valid_start_counter']-origin)/fs+p['probe_start_ms']/1000+source['probe_ms']/2000-o['time_s'])<1e-8]
        if len(matches)!=1:raise ValueError('native ID lacks unique original probe')
        p=matches[0];passing=[c for c in p['candidates'] if c['passed_fractional_margin_gate']]
        if not passing:raise ValueError('native winner missing')
        c=max(passing,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        if c['fractional_tracking_cfo_hz']!=o['measured_cfo_hz'] or c['fractional_margin']!=o['fractional_margin']:raise ValueError('original public candidate selection differs')
        probe=dict(visit_index=p['visit_index'],probe_index=p['probe_index'],channel=p['channel'],actual_rf_hz=p['actual_rf_hz'],
            window_start_counter=p['valid_start_counter']+round(p['probe_start_ms']*fs/1000))
        duration=round(source['probe_ms']*fs/1000)
        result.append(dict(case=case,role=role,owner=owner['owner'],native_observation_id=oid,receiver_id=o['native_receiver_id'],
            original_observation=o,original_candidate=c,probe=probe,duration_samples=duration,
            recording_id=member['recording_id'],source_session_id=source['session_id'],
            physical_probe_key=physical_key(member['recording_id'],source['session_id'],probe,duration),
            acquired_cfo_hz=None,acquired_status='unavailable_in_original_contract',
            original_tracking_path=str(WORK/case/'tracking.json'),original_tracking_sha256=sha(WORK/case/'tracking.json')))
    return result


def freeze():
    began=time.monotonic()
    proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(HERE/'test_nominate.py'),str(HERE/'test_nominate02.py')],capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
    elapsed=time.monotonic()-began
    write('test_receipt02.json',dict(seconds=elapsed,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr))
    baseline=read(BASE/'later_protocol.json')
    prior=read(HERE/'protocol.json')['additional_preparation_seconds']+read(HERE/'actual_smoke.json')['seconds']
    if baseline['preparation_seconds']+prior+elapsed>60:raise ValueError('baseline preparation cap exhausted')
    paths=[Path(__file__),HERE/'test_nominate.py',HERE/'test_nominate02.py',HERE/'actual_smoke02.py',HERE/'PROTOCOL.md',HERE/'FIDELITY_ADDENDUM02.md',HERE/'test_receipt02.json',
        HERE/'protocol.json',HERE/'actual_smoke.json',HERE/'nominate.py',BASE/'selector_v2.py',BASE/'selector_v2_tests.json',BASE/'later_protocol.json',
        INFO/'ranking.py',INFO/'inventory.py',OLD/'panel.py',OLD/'local_math.py',STUDY/'COORDINATOR_PLAN.md']
    paths +=[BASE/'later_RF_seal.json']
    paths +=[Path(p) for p in baseline['source_bindings']]
    write('protocol02.json',dict(schema='later-retained-complete-owner-nomination/v2',cases=CASES,arms=ARMS,
        source_bindings={str(p):sha(p) for p in sorted(set(paths))},additional_preparation_seconds=prior+elapsed,
        prior_failed_smoke_and_preparation_seconds=prior,current_freeze_test_seconds=elapsed,
        original_baseline_cumulative_cap=840,maximum_nomination_seconds=120,workers=1,BLAS_threads=1,
        parent_prerequisite=str(BASE/'later_RF_seal.json'),fixed_input_tree=str(WORK),
        all4_slots_retained=True,whole_curved_owner_minimum_points=20,
        RF_rule='original full-shared-nuisance polynomial susceptibility + exact selector_v2',
        producer_prerequisite='exact pair_passes(include_linear=True); absolute phases diagnostic only',
        no_IQ_detector_correction_position_fit_or_GPS=True,no_fallback_family_or_owner=True))
    print('FROZEN',sha(HERE/'protocol02.json'),flush=True)


def run():
    if (HERE/'RF_seal.json').exists():raise FileExistsError('no retry')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('BLAS1 required')
    protocol=read(HERE/'protocol02.json');ph=sha(HERE/'protocol02.json')
    for p,h in protocol['source_bindings'].items():
        if sha(p)!=h:raise ValueError('bound source changed: '+p)
    baseline_seal=BASE/'later_RF_seal.json'
    for p,h in read(baseline_seal)['files'].items():
        if sha(p)!=h:raise ValueError('terminal baseline source/output changed: '+p)
    for path,flag in [(STUDY/'audit/nomination_preflight.json','all_passed'),(STUDY/'nomination_go.json','approved')]:
        gate=read(path)
        if not gate[flag] or gate['protocol_sha256']!=ph or gate['baseline_RF_seal_sha256']!=sha(baseline_seal):raise ValueError('exact terminal-parent B/root GO required')
    smoke=read(HERE/'actual_smoke02.json')
    if not smoke['all_passed'] or smoke['nomination_protocol_sha256']!=ph or smoke['baseline_RF_seal_sha256']!=sha(baseline_seal):
        raise ValueError('exact real-context load smoke required')
    execution=read(BASE/'later_execution.json');prior=execution['cumulative_worker_seconds']+protocol['additional_preparation_seconds']+smoke['seconds']
    began=time.monotonic();remaining=min(120,840-prior);records=[];allrequests=[]
    statuses={r['case']:r for r in execution['rows']}
    for case in CASES:
        row=dict(case=case,status='unavailable_baseline',baseline_status=statuses[case]['status'],target=None,control=None)
        if statuses[case]['status']=='complete':
            try:
                alarm(remaining-(time.monotonic()-began));d=context(case);bases={a:ranking.parent_design(d,a) for a in ARMS}
                data=ledger(d,bases);models={};checks=[]
                for arm in ARMS:
                    b=bases[arm];h,error=local.position_response(b['j'],b['u'],b['weights'],b['gram'],b['cross'],b['information'])
                    models[arm]=(h,b['weak']);checks.append(dict(arm=arm,Schur_replay_max_error=error,
                        derivative_error=b['derivative_error'],Gamma_change=b['final_log_precision_change'],
                        parent_objective_difference=b['parent_objective_difference'],role_map=b['role_map']))
                ordered=data['ordered_rows'];families=[];owners=[]
                for family in sorted({x['family'] for x in ordered}):
                    ix=[i for i,o in enumerate(ordered) if o['family']==family];times=[ordered[i]['time_s'] for i in ix];q=[ordered[i]['q'] for i in ix]
                    f=dict(case=case,family=family,likelihood_points=len(ix),has_eligible_owner=any(o['eligible'] and o['family']==family for o in data['owners']),arms={})
                    for arm in ARMS:f['arms'][arm]=local.susceptibility(*models[arm],ix,times,q)[0]
                    f['paired_score']=min(f['arms'].values());families.append(f)
                for owner in data['owners']:
                    o=dict(owner,arms={},paired_score=None)
                    if o['eligible']:
                        ix=o['likelihood_indices'];times=[ordered[i]['time_s'] for i in ix];q=[ordered[i]['q'] for i in ix]
                        for arm in ARMS:o['arms'][arm]=local.susceptibility(*models[arm],ix,times,q)[0]
                        o['paired_score']=min(o['arms'].values())
                    owners.append(o)
                target,control=nominate(families,owners)
                # Freeze exact selected complete IDs before native-probe lookup.
                write(Path(case)/'selection.json',dict(case=case,target=target,control=control,families=families,owners=owners))
                requests=[]
                for role,owner in [('target',target),('control',control)]:
                    if owner is not None:requests+=complete_requests(case,role,owner)
                native=[x['native_observation_id'] for x in requests]
                if len(native)!=len(set(native)):raise ValueError('target/control native IDs overlap')
                write(Path(case)/'ownership.json',data);write(Path(case)/'checks.json',checks)
                write(Path(case)/'complete_requests.json',requests);allrequests+=requests
                row.update(status='complete' if target is not None else 'no_eligible_complete_owner',absolute_phase_diagnostic=d['absolute_phase_diagnostic'],
                    target=target['owner'] if target else None,
                    control=control['owner'] if control else None,target_IDs=len(target['observation_ids']) if target else 0,
                    control_IDs=len(control['observation_ids']) if control else 0,eligible_owners=sum(o['eligible'] for o in owners),
                    native_receiver_windows=len(native),deduplicated_physical_probes=len({tuple(x['physical_probe_key']) for x in requests}))
            except Exception as exc:row.update(status='failed_or_budget_limited',error=repr(exc),traceback=traceback.format_exc())
            finally:signal.setitimer(signal.ITIMER_REAL,0)
        records.append(row);write(Path(case)/'result.json',row);print(case,row['status'],flush=True)
    elapsed=time.monotonic()-began
    write('complete_requests.json',allrequests)
    write('summary.json',dict(rows=records,all4_slots_terminal=True,selected_native_receiver_windows=len(allrequests),
        deduplicated_physical_probes=len({tuple(x['physical_probe_key']) for x in allrequests}),
        baseline_RF_seal_sha256=sha(baseline_seal),run_seconds=elapsed,cumulative_baseline_seconds=prior+elapsed,
        no_IQ_detector_correction_position_fit_or_GPS=True))
    write('RF_seal.json',dict(protocol_sha256=ph,baseline_RF_seal_sha256=sha(baseline_seal),
        files={str(p):sha(p) for p in HERE.rglob('*') if p.is_file() and p.name!='RF_seal.json' and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts}))
    print('TERMINAL',prior+elapsed,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));a=parser.parse_args()
    {'freeze':freeze,'run':run}[a.action]()
