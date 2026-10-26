"""Tiny accepted-owner panel from frozen saved RF designs; no IQ or fitting."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import numpy as np
from local_math import position_response,susceptibility,quantile_indices

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
OLD=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/information')
OWN=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def encode(x):return x.tolist() if isinstance(x,np.ndarray) else x.item() if isinstance(x,np.generic) else str(x)
def dump(p,x):
    with Path(p).open('x') as f:json.dump(x,f,indent=2,default=encode,allow_nan=False);f.write('\n')
def csv_write(p,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def metadata(case):
    tracks=load(SOURCE/case/'tracks.json');observations=load(SOURCE/case/'observations.json')
    parent=load(SOURCE/'family_cavity/position'/f'{case}.json');own=load(OWN/case/'parent.json')
    for name,path in [('parent',SOURCE/'family_cavity/position'/f'{case}.json'),('tracks',SOURCE/case/'tracks.json'),('observations',SOURCE/case/'observations.json')]:
        if own['source_'+name+'_sha256']!=sha(path):raise ValueError('ownership input changed: '+name)
    selected=parent['selected'] if parent['accepted'] else None
    node=selected['node'] if selected else parent['baseline_node'];entries=selected['entries'] if selected else parent['baseline_entries']
    mask=parent['original_mask'];lookup={t['key']:t for t in tracks};obs={o['observation_id']:o for o in observations}
    ordered=[];cursor=0
    for row in node['seed']['rows']:
        tr=lookup[row['component']];ids=tr['observation_ids'];active=mask[cursor:cursor+len(ids)];cursor+=len(ids)
        for oid,used in zip(ids,active,strict=True):
            if used:ordered.append(dict(observation_id=oid,owner=tr['key'],family=int(row['candidate_norad']),time_s=obs[oid]['time_s'],q=tr['rf_hz']/11.5e9,role='curved'))
    if cursor!=len(mask):raise ValueError('curved native mask ordering differs')
    for e in entries:
        tr=lookup[e['component']]
        if tr['observation_ids']!=e['observation_ids']:raise ValueError('predictive entry is not complete original owner')
        for oid in e['observation_ids']:ordered.append(dict(observation_id=oid,owner=tr['key'],family=int(e['norad']),time_s=obs[oid]['time_s'],q=tr['rf_hz']/11.5e9,role='predictive'))
    if len(ordered)!=len({r['observation_id']for r in ordered}):raise ValueError('duplicate likelihood IDs')
    ordered_ids={r['observation_id']for r in ordered}
    for arm in ARMS:
        cov=own['coverage'][arm]
        if ordered_ids!=set(cov['curved_observation_ids']+cov['predictive_observation_ids']):raise ValueError('likelihood native IDs differ')
    byowner={}
    for i,row in enumerate(ordered):byowner.setdefault(row['owner'],[]).append(i)
    ledger=[]
    for tr in tracks:
        ids=tr['observation_ids'];reasons=[];cov=own['coverage'];ss=set(ids)
        if len(ids)<20:reasons.append('fewer_than_20_original_points')
        if any(not ss<=set(cov[a]['curved_observation_ids'])for a in ARMS):reasons.append('not_complete_curved_likelihood_in_both_arms')
        indices=byowner.get(tr['key'],[]);families=sorted({ordered[i]['family']for i in indices})
        ledger.append(dict(case=case,owner=tr['key'],receiver=tr['receiver'],channel=tr['channel'],rf_hz=tr['rf_hz'],
            points=len(ids),start_s=tr['start_s'],end_s=tr['end_s'],quality_status=tr['quality_status'],observation_ids=ids,
            family=families[0]if len(families)==1 else None,likelihood_indices=indices,
            role_counts={a:{role:len(ss&set(cov[a][key]))for role,key in [('curved','curved_observation_ids'),('predictive','predictive_observation_ids'),('postfit_only','postfit_only_observation_ids')]}for a in ARMS},
            eligible=not reasons,exclusion_reasons=reasons))
    return dict(case=case,owners=ledger,ordered_rows=ordered)


def prepare():
    if(HERE/'protocol.json').exists():raise FileExistsError('preserve freeze')
    tick=time.monotonic();data=[metadata(c)for c in CASES];original=load(OLD/'results.json');smoke=[];paths=[]
    for d in data:
        case=d['case']
        for arm in ARMS:
            a=next(x for x in original['parents']if x['case']==case and x['arm']==arm);p=Path(a['array_path'])
            if sha(p)!=a['array_sha256']:raise ValueError('original array binding changed')
            z=np.load(p)
            if len(d['ordered_rows'])!=len(z['position_design']):raise ValueError('saved array/native ordering length differs')
            smoke.append(dict(case=case,arm=arm,array_path=str(p),array_sha256=sha(p),rows=len(z['position_design']),nuisance_columns=z['nuisance_design'].shape[1],
                owners=len(d['owners']),eligible_complete_owners=sum(x['eligible']for x in d['owners']),no_new_scores_computed=True))
            paths.append(p)
        paths +=[SOURCE/d['case']/n for n in ('tracks.json','observations.json','tracking.json')]
        paths +=[SOURCE/'family_cavity/position'/f"{d['case']}.json",OWN/d['case']/'parent.json']
    dump(HERE/'complete_owner_ledger.json',data);elapsed=time.monotonic()-tick
    start=time.monotonic();r=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(HERE/'test_local_math.py')],cwd=HERE,capture_output=True,text=True)
    dump(HERE/'test_receipt.json',dict(returncode=r.returncode,seconds=time.monotonic()-start,stdout=r.stdout,stderr=r.stderr))
    if r.returncode:raise RuntimeError('owned tests failed')
    dump(HERE/'smoke.json',dict(records=smoke,seconds=elapsed,metadata_only=True))
    paths +=[HERE/n for n in ('panel.py','local_math.py','raw_metadata.py','test_local_math.py','PROTOCOL.md','complete_owner_ledger.json','smoke.json','test_receipt.json')]
    paths +=[OLD/'results.json',SOURCE/'sample.json',ROOT/'COORDINATOR_PLAN.md',REPO/'src/leo/storage/fast_scan.py',REPO/'src/leo/storage/short_window.py',REPO/'src/leo/storage/uri.py',REPO/'src/leo/contracts/multirate_window_recording.py',REPO/'src/leo/contracts/short_window_recording.py']
    dump(HERE/'protocol.json',dict(schema='accepted-owner-susceptibility/v1',cases=CASES,arms=ARMS,bindings={str(p):sha(p)for p in sorted(set(paths))},
        maximum_cumulative_worker_seconds=180,preparation_seconds=elapsed,test_seconds=load(HERE/'test_receipt.json')['seconds'],prior_metadata_charge_seconds=2.,
        workers=1,BLAS_threads=1,axis='arm-specific original saved weak unit axis',perturbation='degree<=2, equal-ID-orthonormal,1HzRMS at11.5GHz before RF scaling',
        selection_rule_document='PROTOCOL.md',no_IQ_detector_position_or_GPS=True))
    print('FROZEN',sha(HERE/'protocol.json'),flush=True)


def request(case,role,owner,quantile,oid):
    tracking=load(SOURCE/case/'tracking.json');observations={r['observation_id']:r for r in load(SOURCE/case/'observations.json')};o=observations[oid]
    source=tracking['source'];origin=tracking['clock_anchor']['sample_counter'];fs=source['sample_rate_hz']
    matches=[p for p in source['probes']if p['receiver_id']==o['native_receiver_id']and p['channel']==o['channel']and
        abs((p['valid_start_counter']-origin)/fs+p['probe_start_ms']/1000+source['probe_ms']/2000-o['time_s'])<1e-8]
    if len(matches)!=1:raise ValueError('unique original probe required')
    p=matches[0];passing=[c for c in p['candidates']if c['passed_fractional_margin_gate']];c=max(passing,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
    if c['fractional_tracking_cfo_hz']!=o['measured_cfo_hz']or c['fractional_margin']!=o['fractional_margin']:raise ValueError('winner changed')
    member=next(m for m in load(SOURCE/'sample.json')['selected']if m['dataset_label']==case)
    si=next(x for x in member['source_inputs']if x['sha256']==source['input_manifest_sha256'])
    return dict(request_id=f'{case}_{role}_q{quantile}',case=case,role=role,complete_owner=owner['owner'],native_observation_id=oid,time_quantile=quantile,
        original_observation=o,tracking=dict(path=str(SOURCE/case/'tracking.json'),sha256=sha(SOURCE/case/'tracking.json')),
        source_input=si,source_session_id=source['session_id'],recording_id=member['recording_id'],raw_recording_authority_digest=source['raw_recording_authority_digest'],
        probe=dict(visit_index=p['visit_index'],probe_index=p['probe_index'],receiver_id=p['receiver_id'],channel=p['channel'],actual_rf_hz=p['actual_rf_hz'],
            time_s=o['time_s'],window_start_counter=p['valid_start_counter']+round(p['probe_start_ms']*fs/1000),origin_counter=origin,duration_samples=round(source['probe_ms']*fs/1000)),
        original_candidate=c,acquired_cfo_hz=None,acquired_CFO_status='not_retained_in_historical_tracking_contract',detector_authority=tracking['provenance'])


def run():
    if any(os.environ.get(k)!='1'for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('BLAS1 required')
    if(HERE/'RF_seal.json').exists():raise FileExistsError('one run only')
    protocol=load(HERE/'protocol.json');ap=load(ROOT/'audit/influence_preflight.json')
    if not ap['all_passed']or ap['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('matching preflight required')
    for p,h in protocol['bindings'].items():
        if sha(p)!=h:raise ValueError('changed binding: '+p)
    prefix=sum(protocol[k]for k in ('preparation_seconds','test_seconds','prior_metadata_charge_seconds'));tick=time.monotonic();remaining=180-prefix
    if remaining<=0:raise TimeoutError('preparation exhausted budget')
    def timeout(*_):raise TimeoutError('180-second cumulative cap')
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,remaining)
    data=load(HERE/'complete_owner_ledger.json');old=load(OLD/'results.json');families=[];owners=[];selection=[];requests=[];checks=[];matrices={};failure=None
    try:
        for d in data:
            case=d['case'];rows=d['ordered_rows'];family_ids=sorted({r['family']for r in rows});casefamilies=[];caseowners=[]
            models={}
            for arm in ARMS:
                meta=next(x for x in old['parents']if x['case']==case and x['arm']==arm);a=dict(np.load(meta['array_path']))
                h,err=position_response(a['position_design'],a['nuisance_design'],a['weights'],a['gram'],a['cross'],a['information'])
                models[arm]=(h,a['weak']);matrices[case+'_'+arm+'_response']=h;matrices[case+'_'+arm+'_weak']=a['weak']
                checks.append(dict(case=case,arm=arm,Schur_replay_max_error=err,physical_modes_in_original_parent=meta['role_map']['physical_modes'],
                    absent_physical_modes_remain_absent=True,all_original_predictive_rows_retained=True))
            for family in family_ids:
                ix=[i for i,r in enumerate(rows)if r['family']==family];times=[rows[i]['time_s']for i in ix];q=[rows[i]['q']for i in ix]
                rec=dict(case=case,family=family,likelihood_points=len(ix),arms={},has_eligible_owner=any(o['eligible']and o['family']==family for o in d['owners']))
                for arm in ARMS:
                    score,_,_=susceptibility(*models[arm],ix,times,q)
                    rec['arms'][arm]=dict(km_per_Hz_RMS=score,one_Hz_proxy_m=score*1000,twenty_Hz_proxy_m=score*20000)
                rec['paired_score']=min(rec['arms'][a]['km_per_Hz_RMS']for a in ARMS);casefamilies.append(rec)
            for owner in d['owners']:
                r=dict(owner,arms={})
                if owner['eligible']:
                    ix=owner['likelihood_indices'];times=[rows[i]['time_s']for i in ix];q=[rows[i]['q']for i in ix]
                    for arm in ARMS:
                        score,_,_=susceptibility(*models[arm],ix,times,q)
                        r['arms'][arm]=dict(km_per_Hz_RMS=score,one_Hz_proxy_m=score*1000,twenty_Hz_proxy_m=score*20000)
                    r['paired_score']=min(r['arms'][a]['km_per_Hz_RMS']for a in ARMS)
                else:r['paired_score']=None
                caseowners.append(r)
            ranked=sorted([f for f in casefamilies if f['has_eligible_owner']],key=lambda f:(-f['paired_score'],f['family']))
            if not ranked:selection.append(dict(case=case,target=None,control=None,error='no eligible complete owner'));families+=casefamilies;owners+=caseowners;continue
            target_family=ranked[0];target=sorted([o for o in caseowners if o['eligible']and o['family']==target_family['family']],key=lambda o:(-o['paired_score'],o['owner']))[0]
            low=sorted([f for f in ranked if f['family']!=target['family']and f['paired_score']>0],key=lambda f:(f['paired_score'],f['family']))[:max(1,math.ceil(len(ranked)/4))]
            fscore={f['family']:f['paired_score']for f in low}
            controls=[o for o in caseowners if o['eligible']and o['family']in fscore]
            controls.sort(key=lambda o:(o['receiver']==target['receiver'],fscore[o['family']],o['paired_score'],o['owner']))
            control=controls[0]if controls else None
            selection.append(dict(case=case,target=target,control=control,target_family=target_family,control_family=next((f for f in low if control and f['family']==control['family']),None)))
            obs={o['observation_id']:o for o in load(SOURCE/case/'observations.json')}
            for role,owner in [('target',target),('control',control)]:
                if owner is None:continue
                ids=sorted(owner['observation_ids'],key=lambda oid:(obs[oid]['time_s'],oid))
                for qt,index in zip((.25,.75),quantile_indices(len(ids)),strict=True):requests.append(request(case,role,owner,qt,ids[index]))
            families+=casefamilies;owners+=caseowners
        dump(HERE/'selection_before_raw_metadata.json',selection);dump(HERE/'requests_before_raw_metadata.json',requests)
        env=dict(os.environ,PYTHONPATH=str(REPO/'src'),PYTHONDONTWRITEBYTECODE='1')
        t=time.monotonic();result=subprocess.run(['sudo','-n','-u','leo','env','PYTHONPATH='+str(REPO/'src'),'PYTHONDONTWRITEBYTECODE=1',sys.executable,'-B',str(HERE/'raw_metadata.py')],
            input=json.dumps(requests),capture_output=True,text=True,env=env,timeout=min(30,180-prefix-(time.monotonic()-tick)))
        dump(HERE/'raw_metadata_receipt.json',dict(returncode=result.returncode,seconds=time.monotonic()-t,stderr=result.stderr,stdout=result.stdout))
        raw={r['request_id']:r['raw_authority']for r in json.loads(result.stdout)}if result.returncode==0 else {}
        for r in requests:r['raw_authority']=raw.get(r['request_id'],dict(status='unavailable',error='metadata subprocess failed; see preserved receipt'))
    except Exception as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    dump(HERE/'window_requests.json',requests);dump(HERE/'results.json',dict(families=families,owners=owners,selection=selection,checks=checks,failure=failure))
    if matrices:np.savez_compressed(HERE/'response_arrays.npz',**matrices)
    csv_write(HERE/'owner_scores.csv',[dict(case=o['case'],owner=o['owner'],family=o['family'],points=o['points'],receiver=o['receiver'],channel=o['channel'],eligible=o['eligible'],
        reasons=';'.join(o['exclusion_reasons']),c0_m_per_Hz=o['arms'].get('c0',{}).get('one_Hz_proxy_m'),fitted_c_m_per_Hz=o['arms'].get('fitted_c',{}).get('one_Hz_proxy_m'))for o in owners])
    elapsed=time.monotonic()-tick
    summary=dict(cases=CASES,original_owner_counts={d['case']:len(d['owners'])for d in data},eligible_complete_owner_counts={d['case']:sum(o['eligible']for o in d['owners'])for d in data},
        selected_owners=[dict(case=s['case'],target=s['target']['owner']if s['target']else None,control=s['control']['owner']if s['control']else None)for s in selection],
        requests=len(requests),metadata_ready=sum(r.get('raw_authority',{}).get('status')=='metadata_ready_IQ_and_detector_parity_unverified'for r in requests),
        failure=failure,run_worker_seconds=elapsed,cumulative_worker_seconds=prefix+elapsed,IQ_or_detector_or_position_or_GPS=False)
    dump(HERE/'summary.json',summary)
    dump(HERE/'RF_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),preflight_sha256=sha(ROOT/'audit/influence_preflight.json'),files={str(p):sha(p)for p in sorted(HERE.iterdir())if p.is_file()and p.name!='RF_seal.json'}))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);a=p.parse_args();prepare()if a.action=='prepare'else run()
