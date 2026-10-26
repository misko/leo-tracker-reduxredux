"""Reuse the original information kernel; bounded ownership and local designs."""
import argparse
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

START=time.monotonic()
import numpy as np
import ledger as L
sys.path.insert(0,str(L.OLD))
spec=importlib.util.spec_from_file_location('original_information_ranking',L.OLD/'ranking.py')
K=importlib.util.module_from_spec(spec);spec.loader.exec_module(K)
IMPORT_SECONDS=time.monotonic()-START
HERE=L.HERE

def save(p,x):K.r.write_new(p,x)
def timer(seconds):
    if seconds<=0:raise TimeoutError('600s cumulative numerical cap')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded diagnostic deadline')))
    signal.setitimer(signal.ITIMER_REAL,seconds)
def threads():
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):
        raise ValueError('explicit BLAS1 environment required')

def covered(case):
    p=HERE/'ownership'/case/'parent.json'
    if p.exists():return L.read(p)['coverage'],p
    m=next(q for q in L.read(HERE/'metadata.json')['cases'] if q['case']==case)
    if m['ownership_status']=='reused_bound_receipt':return L.read(m['ownership_receipt'])['coverage'],Path(m['ownership_receipt'])
    return None,None

def bindings():
    files=[Path(__file__),HERE/'ledger.py',HERE/'test_expand.py',HERE/'PROTOCOL.md',HERE/'metadata.json',HERE/'inventory.json',HERE/'preparation.json',HERE/'scope_audit.json',L.OLD/'ranking.py']
    for q in L.cases():
        case=q['case'];files += [L.SOURCE/case/name for name in ('tracks.json','observations.json','bank.npz','radio_noise.json','receipt.json','nominal_elements.json')]
        files += [L.SOURCE/'family_cavity/position'/f'{case}.json',L.SOURCE/'causal_phase_history'/f'{case}.json',L.SOURCE/'causal_phase_history'/f'{case}_forecast.json']
        files += [L.SOURCE/'causal_prior'/case/name for name in ('previous.tle','receipt.json','previous_receipt.json')]
        _,p=covered(case)
        if p:files.append(p)
    for m in list(sys.modules.values()):
        p=getattr(m,'__file__',None)
        if p:
            p=Path(p)
            if p.is_file() and p.suffix=='.py' and (str(p).startswith('/srv/bulk/leo/research/') or str(p).startswith('/home/mouse9911/gits/leo-tracker-reduxredux/')):files.append(p)
    frozen=L.read(HERE/'metadata.json')['bindings']
    frozen.update(L.read(HERE/'scope_audit.json')['input_bindings'])
    for p,h in frozen.items():
        if L.sha(p)!=h:raise ValueError('metadata authority changed: '+p)
    return dict(frozen,**{str(p):L.sha(p) for p in sorted(set(files))})

def prepare():
    threads();start=START;meta=L.read(HERE/'metadata.json')
    known,_=L.exposure();rows=[];cases=[];smoke=None
    for m in meta['cases']:
        case=m['case'];cov,p=covered(case);failure=None
        if cov is None:
            elapsed=time.monotonic()-start
            timer(min(30.,250.-elapsed))
            began=time.monotonic()
            try:
                d=K.r.context(case)
                cov={a:K.r.membership(d,a,d['arms'][a]) for a in L.ARMS}
                pp=L.SOURCE/'family_cavity/position'/f'{case}.json';tp=L.SOURCE/case/'tracks.json'
                obj=dict(case=case,coverage=cov,source_parent_sha256=L.sha(pp),source_tracks_sha256=L.sha(tp),source_observations_sha256=L.sha(L.SOURCE/case/'observations.json'),
                    seconds=time.monotonic()-began,position_fits=0,new_nominations=0,GPS_used=False)
                p=HERE/'ownership'/case/'parent.json';save(p,obj)
                if smoke is None:
                    b={a:K.parent_design(d,a) for a in L.ARMS}
                    smoke=dict(case=case,arms={a:dict(parent_objective_difference=b[a]['parent_objective_difference'],Gamma_change=b[a]['final_log_precision_change'],columns=len(b[a]['prior']),rows=len(b[a]['j'])) for a in L.ARMS})
            except Exception as exc:
                failure=dict(error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-began)
                save(HERE/'ownership'/case/'failure.json',failure);cov=None;p=None
            finally:signal.setitimer(signal.ITIMER_REAL,0)
        parent=L.read(L.SOURCE/'family_cavity/position'/f'{case}.json')
        cr=L.make_rows(case,L.read(L.SOURCE/case/'tracks.json'),parent,cov,known)
        for q in cr:
            if cov:
                j=q['candidate_index'];q['family_has_parent_physical_modes']=j in cov['c0']['supported_families'] if j is not None else None
                q['incumbent_mode_block']=bool(q['family_has_parent_likelihood'] and not q['family_has_parent_physical_modes'])
            else:q['incumbent_mode_block']=None;q['family_has_parent_physical_modes']=None
        rows+=cr
        cases.append(dict(m,ownership_status='complete' if cov else 'failed',ownership_receipt=str(p) if p else None,ownership_sha256=L.sha(p) if p else None,
            native_owners=len(cr),eligible_complete_owners=sum(q['eligible'] for q in cr),failure=failure))
    inv=dict(cases=cases,sources=rows,metadata_sha256=L.sha(HERE/'metadata.json'),selection_case_order=[q['case'] for q in meta['cases']],
        missing_ownership_no_backfill=True,identity_qualification=False,all_scans_exposed_development=True,position_fits=0,GPS_used=False)
    save(HERE/'inventory.json',inv)
    old=L.read(L.OLD/'protocol.json');old_bad=[p for p,h in old['source_and_input_bindings'].items() if not Path(p).exists() or L.sha(p)!=h]
    preparation=dict(seconds=time.monotonic()-start,import_seconds=IMPORT_SECONDS,metadata_seconds=meta['seconds'],smoke=smoke,
        old_four_reuse_all_bindings_unchanged=not old_bad,old_four_changed_bindings=old_bad,
        cases=len(cases),complete_ownership_cases=sum(q['ownership_status']=='complete' for q in cases),eligible_sources=sum(q['eligible'] for q in rows),
        new_position_fits=0,new_nomination=0,GPS_used=False)
    save(HERE/'preparation.json',preparation)
    began=time.monotonic();f=bindings()
    tests=L.read(HERE/'test_receipt.json')
    protocol=dict(schema='whole-source-applicability-local-information/v1',cases=[q['case'] for q in cases],source_and_input_bindings=f,
        minimum_fractional_weak_variance_reduction_each_arm=.05,maximum_distinct_new_case_nominees=4,
        new_choice_excluded_cases=list(L.OLD_FOUR),source_exposure_scope='original four-case information inventory and original two-case recovery candidate_targets; no never-examined claim',
        selection='chronological cases; greatest min-arm reduction, then points, duration, component; same ownership pool count/duration controls; no replacement',
        scientific_kernel=str(L.OLD/'ranking.py'),old_four_results=str(L.OLD/'results.json'),old_four_reuse=not old_bad,
        maximum_cumulative_worker_seconds=600,workers=1,BLAS_threads=1,per_case_seconds=30,
        metadata_seconds=meta['seconds'],preparation_seconds=preparation['seconds'],test_seconds=tests['seconds'],freeze_seconds=time.monotonic()-began,
        no_position_fits=True,no_GPS_or_errors=True,no_new_nomination=True,conditional_identity_only=True)
    protocol['source_and_input_bindings'][str(L.OLD/'results.json')]=L.sha(L.OLD/'results.json')
    protocol['source_and_input_bindings'][str(L.OLD/'inventory.json')]=L.sha(L.OLD/'inventory.json')
    save(HERE/'protocol.json',protocol)
    print(json.dumps(dict(preparation=preparation,protocol_sha256=L.sha(HERE/'protocol.json'))),flush=True)

def pick(rows,case_order):
    chosen=[]
    for case in case_order:
        if case in L.OLD_FOUR:continue
        pool=[q for q in rows if q['case']==case and q.get('eligible') and q.get('status')=='complete' and q.get('unexhausted_within_declared_audit') and q.get('paired_ranking_score',-1)>=.05]
        if pool:
            chosen.append(sorted(pool,key=lambda q:(-q['paired_ranking_score'],-q['points'],-q['span_s'],q['component']))[0])
        if len(chosen)==4:break
    return chosen

def ranks(rows,case_order):
    for case in case_order:
        pool=[q for q in rows if q['case']==case and q['eligible']]
        for i,q in enumerate(sorted(pool,key=lambda q:(-q['points'],-q['span_s'],q['component'])),1):q['count_rank']=i
        for i,q in enumerate(sorted(pool,key=lambda q:(-q['span_s'],-q['points'],q['component'])),1):q['duration_rank']=i
        for i,q in enumerate(sorted([q for q in pool if q.get('status')=='complete'],key=lambda q:(-q['paired_ranking_score'],-q['points'],-q['span_s'],q['component'])),1):q['information_rank']=i
        new=[q for q in pool if q['unexhausted_within_declared_audit']]
        for i,q in enumerate(sorted(new,key=lambda q:(-q['points'],-q['span_s'],q['component'])),1):q['unexhausted_count_rank']=i
        for i,q in enumerate(sorted(new,key=lambda q:(-q['span_s'],-q['points'],q['component'])),1):q['unexhausted_duration_rank']=i
        for i,q in enumerate(sorted([q for q in new if q.get('status')=='complete'],key=lambda q:(-q['paired_ranking_score'],-q['points'],-q['span_s'],q['component'])),1):q['unexhausted_information_rank']=i

def interrupt_rows(pool,error):
    for q in pool:
        if 'status' not in q or q.get('status')=='in_progress' or (q.get('arms') and len(q['arms'])<2):
            q.update(status='unavailable',error='case stopped: '+error)

def run():
    threads();start=START;pr=L.read(HERE/'protocol.json');ap=L.read(HERE.parent/'audit'/'inventory_preflight.json')
    assert ap['all_passed'] and ap['protocol_sha256']==L.sha(HERE/'protocol.json')
    for p,h in pr['source_and_input_bindings'].items():
        if L.sha(p)!=h:raise ValueError('frozen input/source changed: '+p)
    prefix=sum(pr[k] for k in ('metadata_seconds','preparation_seconds','test_seconds','freeze_seconds'))
    inv=L.read(HERE/'inventory.json');rows=copy.deepcopy(inv['sources']);parents=[];failures=[]
    old=L.read(L.OLD/'results.json');oldrows={(q['case'],q['component']):q for q in old['rows']}
    for m in inv['cases']:
        case=m['case'];pool=[q for q in rows if q['case']==case and q['eligible']]
        if case in L.OLD_FOUR:
            for q in pool:
                if pr['old_four_reuse']:
                    oldq=copy.deepcopy(oldrows[case,q['component']]);q.update({k:v for k,v in oldq.items() if k in ('arms','status','paired_ranking_score')});q['reused_original_information']=True
                else:q.update(status='blocked',error='old source/input bindings changed; no repeated four-case ranks')
            parents.extend(dict(q,reused_original_information=True) for q in old['parents'] if q['case']==case) if pr['old_four_reuse'] else None
            continue
        if m['ownership_status']!='complete':
            failures.append(dict(case=case,error='full accepted-ID ownership unavailable'));continue
        began=time.monotonic();remaining=600-prefix-(began-start)
        if remaining<=0:
            failures.append(dict(case=case,error='global numerical cap reached before case'));break
        timer(min(pr['per_case_seconds'],remaining))
        try:
            d=K.r.context(case);bases={}
            for a in L.ARMS:
                b=K.parent_design(d,a);bases[a]=b;p=HERE/'arrays'/f'{case}_{a}_parent.npz';p.parent.mkdir(exist_ok=True)
                np.savez_compressed(p,gram=b['gram'],cross=b['cross'],root=b['root'],response=b['response'],information=b['information'],weak=b['weak'],prior=b['prior'],position_design=b['j'],nuisance_design=b['u'],weights=b['weights'])
                parents.append(dict(case=case,arm=a,information=b['information'],weak=b['weak'],weak_variance_km2=b['variance'],role_map=b['role_map'],columns=b['columns'],array_path=str(p),array_sha256=L.sha(p),derivative_error=b['derivative_error'],parent_objective_difference=b['parent_objective_difference'],final_log_precision_change=b['final_log_precision_change']))
            for q in pool:
                q.update(arms={},status='in_progress')
                for a in L.ARMS:
                    try:
                        b=bases[a];t=K.target_design(d,b,q);red=K.redacted_target(d,b,q)
                        diff=max(float(np.max(np.abs(t[k]-red[k]))) for k in ('j','h','variance','extra'))
                        if diff!=0:raise ValueError('target CFO changes design score')
                        gain,cov,eff=K.gain(t['j'],t['h'],t['variance'],t['extra'],b['root'],b['response'])
                        aug=b['information']+gain
                        if not np.isfinite(aug).all() or np.linalg.eigvalsh(aug)[0]<=0:raise ValueError('nonpositive augmented information')
                        v=float(b['weak']@np.linalg.solve(aug,b['weak']));reduction=1-v/b['variance']
                        if not -1e-10<=reduction<=1+1e-10:raise ValueError('invalid variance reduction')
                        p=HERE/'arrays'/f'{case}_row{q["row_index"]:03d}_{a}.npz'
                        np.savez_compressed(p,j=t['j'],h=t['h'],noise_variance=t['variance'],extra=t['extra'],conditional_covariance=cov,effective_j=eff,information_gain=gain)
                        q['arms'][a]=dict(status='complete',information_gain=gain,augmented_information=aug,baseline_weak_variance_km2=b['variance'],augmented_baseline_weak_variance_km2=v,fractional_weak_variance_reduction=reduction,baseline_weak_SD_km=np.sqrt(b['variance']),augmented_weak_SD_km=np.sqrt(v),covariance_semantics=t['kind'],minimum_elevation_deg=t['minimum_elevation_deg'],phase_reference_s=t['phase_reference_s'],derivative_error=t['derivative_error'],target_CFO_redaction_maximum_difference=diff,array_path=str(p),array_sha256=L.sha(p))
                    except TimeoutError:raise
                    except Exception as exc:q['arms'][a]=dict(status='blocked',error=repr(exc))
                q['status']='complete' if all(v['status']=='complete' for v in q['arms'].values()) and len(q['arms'])==2 else 'blocked'
                if q['status']=='complete':q['paired_ranking_score']=min(v['fractional_weak_variance_reduction'] for v in q['arms'].values())
                save(HERE/'completed'/f'{case}_row{q["row_index"]:03d}.json',q)
        except Exception as exc:
            failures.append(dict(case=case,error=repr(exc),traceback=traceback.format_exc()))
            interrupt_rows(pool,repr(exc))
            for q in pool:
                if q['status']=='unavailable' and q.get('arms'):
                    save(HERE/'partial'/f'{case}_row{q["row_index"]:03d}.json',q)
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        print(json.dumps(dict(case=case,pool=len(pool),seconds=time.monotonic()-began,cumulative_worker_seconds=prefix+time.monotonic()-start)),flush=True)
        if prefix+time.monotonic()-start>=600:break
    for q in rows:
        if q['eligible'] and 'status' not in q:q.update(status='unavailable',error='global cap or unavailable case')
        elif not q['eligible']:q['status']='excluded'
    ranks(rows,inv['selection_case_order']);chosen=pick(rows,inv['selection_case_order'])
    result=dict(rows=rows,parents=parents,case_failures=failures,selection=[dict(case=q['case'],component=q['component'],candidate_norad=q['candidate_norad'],paired_ranking_score=q['paired_ranking_score'],information_rank=q['information_rank'],count_rank=q['count_rank'],duration_rank=q['duration_rank']) for q in chosen],seconds=time.monotonic()-start,cumulative_worker_seconds=prefix+time.monotonic()-start,protocol_sha256=L.sha(HERE/'protocol.json'),no_new_position_fits=True,no_GPS_or_errors=True,identity_qualification=False)
    save(HERE/'results.json',result)
    save(HERE/'RF_seal.json',dict(files={str(p):L.sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts},position_fits=0,GPS_used=False))
    print(json.dumps(dict(terminal=True,selected=result['selection'],seconds=result['cumulative_worker_seconds'])),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['prepare','run']);opts=a.parse_args();globals()[opts.action]()
