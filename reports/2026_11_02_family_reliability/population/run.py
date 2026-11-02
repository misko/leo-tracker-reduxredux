"""Bounded RF-only acceptance stress test against exact saved ALGO07 outputs."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
REPO=ROOT.parents[2]
SOURCE=REPO/'reports/2026_11_02_algo07_top10_outliers/run_manifest.json'
READINESS=REPO/'reports/2026_11_01_promotion_readiness'
sys.path[:0]=[str(BASE/'family'),str(BASE/'solver')]
from prototype import candidate_context
from solver import fit
from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo06_science.common import read,write
from prototype_dsx01_continuous_position import latlon

ARMS=('c0','fitted_c')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def error(x):
    site=np.deg2rad((37.849061591561885,-122.48574968092912));a=np.deg2rad(latlon(x))
    h=np.sin((a[0]-site[0])/2)**2+np.cos(a[0])*np.cos(site[0])*np.sin((a[1]-site[1])/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(h)))

def freeze():
    if (ROOT/'protocol.json').exists():raise FileExistsError('Protocol already frozen')
    manifest=read(SOURCE);baseline={}
    paths=[READINESS/'population_positions.csv',READINESS/'ds24/positions.csv',READINESS/'fresh_positions.csv']
    for index,path in enumerate(paths):
        for row in csv.DictReader(path.open()):
            if index==0 and row['method']!='guarded_candidate':continue
            case=row['case'];arm=row['arm']
            baseline.setdefault(case,{})[arm]=dict(error_m=float(row['error_m'] if index==0 else row['candidate_error_m'] if index==1 else row['candidate_m']),
                objective=float(row['objective'] if index==0 else row['candidate_objective']),
                associated=int(row['associated'] if index!=1 else row['candidate_associated']),
                selected=row.get('selected') or None,source=str(path),source_sha256=sha(path))
    cases=sorted(manifest['rows'],key=lambda r:r['case'])
    assert len(cases)==205 and len({tuple(r['identities']) for r in cases})==205
    for row in cases:
        row['baseline']=baseline[row['case']]
        assert set(row['baseline'])==set(ARMS)
        assert row['baseline']['fitted_c']['selected']==row['selected']
        assert abs(row['baseline']['fitted_c']['error_m']-row['error_m'])<1e-7
        assert len({row['baseline'][a]['selected'] for a in ARMS})==1
    policy=dict(created_utc_ns=time.time_ns(),revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=REPO).strip(),
        source_manifest=str(SOURCE),source_manifest_sha256=sha(SOURCE),cases=cases,available=205,
        total_source_members=229,missing_source_members=24,per_cohort=manifest['per_cohort'],
        model='fixed physical SD4 + half-damped phase refresh, guarded by both-arm normalized RF improvement',
        candidate_selection='first existing e.rank_families eligible RF family; no case-ID or GPS selection',
        preserved_existing_ALGO07='If saved guarded replacement accepted, preserve exactly; do not reconstruct ALGO06 as comparator',
        physical_SD_scale=4,control_SD_scale=1,phase_refresh='damped_half',rounds=15,maxiter=35,maxfun=140,
        common_start='saved fitted-c RF position and phase reference, same both arms and candidate/control',
        acceptance='Both candidate arms optimizer+phase closure+base/exact/mixture gates+mixture boundary<.01, unchanged all native input IDs, no lost or unrelated-reassigned owner, objective gain strictly >2log(3) vs BOTH matched SD1+half control and saved baseline in BOTH arms',
        objective_gain_threshold=float(2*np.log(3)),fallback='exact saved ALGO07 baseline for every rejected, failed, unavailable, or capped case',
        coverage='Baseline published ownership frozen. Incidental full-graph extension proposals excluded from selected coverage and never adopted.',
        arms=ARMS,geography='postfit evaluation only; never selects family/scale/solver/model/acceptance',
        development_cases=['DS26-0070','DS26-0309'],independence='Remaining203 scans are held from this two-scan model development, not independent model-discovery validation of historical RF pipeline.',
        max_workers=8,blas_threads=1,per_case_seconds=600,total_wall_seconds=1200,
        schedule='lexical case ID, never geography error rank',
        comparator_tolerances=dict(objective_absolute=1e-4,error_m_absolute=.02),
        source_sha256={str(p):sha(p) for p in [Path(__file__),BASE/'family/prototype.py',BASE/'solver/solver.py',*paths]})
    write(ROOT/'protocol.json',policy)
    print('Frozen',len(cases),'cases; existing repairs',[r['case'] for r in cases if r['selected']],flush=True)

def diagnostics():
    path=REPO/'reports/2026_11_02_algo07_top10_outliers/diagnostics/diagnose.py'
    spec=importlib.util.spec_from_file_location('population_old_diag',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def ids(p):
    return sorted(o for i,sl in zip(p.members,p.slices) for o,k in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl]) if k)

def native_inventory(p,context):
    owners={};counts={}
    def append(kind,values,norad):
        counts[kind]=counts.get(kind,0)+len(values)
        for oid in values:
            if oid in owners:raise ValueError('Native ID duplicated across likelihood pieces')
            owners[oid]=int(norad)
    for row,i,sl in zip(p.rows,p.members,p.slices):
        append('curved',[o for o,k in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl]) if k],row['candidate_norad'])
    for ent in context['entries']:append('conditional_entries',ent['observation_ids'],ent['norad'])
    for family in context['families']:
        for ent in family.entries:append('phase_mixture_families',ent['observation_ids'],ent['norad'])
    return dict(ids=sorted(owners),owners=owners,counts=counts)

def all_ids(p,context):return native_inventory(p,context)['ids']

def ids_hash(values):return hashlib.sha256('\n'.join(values).encode()).hexdigest()

def worker(case):
    start_time=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600 second case cap')));signal.alarm(600)
    policy=read(ROOT/'protocol.json');record=next(r for r in policy['cases'] if r['case']==case)
    out=ROOT/'cases'/case;out.mkdir(parents=True,exist_ok=True)
    result=dict(case=case,dataset=record['dataset'],identities=record['identities'],baseline=record['baseline'],
        baseline_selected=record['selected'],accepted=False,status='running',fit_attempted=False,
        protocol_sha256=sha(ROOT/'protocol.json'),source_input=record['input_path'],source_input_sha256=record['input_sha256'],
        development_case=case in policy['development_cases'])
    try:
        for p,h in policy['source_sha256'].items():
            if sha(p)==h:continue
            amendment=read(ROOT/'execution_amendment.json')
            assert p==str(Path(__file__).resolve()) and amendment['original_run_sha256']==h and amendment['amended_run_sha256']==sha(p),'Frozen source mismatch '+p
            result['execution_amendment_sha256']=sha(ROOT/'execution_amendment.json')
        assert sha(record['input_path'])==record['input_sha256'],'Native input mismatch'
        if record['selected']:
            result.update(status='preserved_existing_ALGO07',reason='existing guarded replacement accepted; preserve exact saved ALGO07 comparator')
        else:
            root=Path(record['input_path']).parent.parent
            e.configure(root,out);e.ROOTS[case[:4]]=root
            d,z,replay=e.load_case(case)
            result['baseline_replay']={}
            for arm,(p,x) in d['problems'].items():
                objective_difference=objective(p,d,x)-record['baseline'][arm]['objective']
                coordinate_difference=float(max(abs(np.asarray(x)-np.asarray(z['baseline_arms'][arm]['endpoint_east_north_km']))))
                associated_difference=len(z['baseline_owners'][arm])-record['baseline'][arm]['associated']
                assert abs(objective_difference)<1e-4,f'Baseline objective mismatch {arm}: {objective_difference}'
                assert coordinate_difference<1e-8,f'Baseline saved RF coordinate mismatch {arm}: {coordinate_difference}'
                assert associated_difference==0,f'Baseline coverage mismatch {arm}: {associated_difference}'
                inv=native_inventory(p,d);full_ids=inv['ids']
                assert full_ids==sorted(z['baseline_owners'][arm]),'Baseline full native union mismatch'
                assert inv['owners']==z['baseline_owners'][arm],'Baseline fitted identity mapping mismatch'
                result['baseline_replay'][arm]=dict(objective_difference=objective_difference,coordinate_difference_km=coordinate_difference,
                    associated_difference=associated_difference,all_native_union_sha256=ids_hash(full_ids),all_native_count=len(full_ids),
                    full_native_union_equals_saved_owners=True,native_counts=inv['counts'],
                    fitted_owners_sha256=hashlib.sha256(json.dumps(inv['owners'],sort_keys=True).encode()).hexdigest())
            result['replay']=replay
            ranking,eligible=e.rank_families(d,z)
            result.update(ranking=ranking,eligible=eligible)
            if not eligible:result.update(status='no_RF_trigger',reason='no family passes existing RF influence trigger')
            else:
                family=eligible[0];expected=ids(d['problems']['fitted_c'][0]);common=d['problems']['fitted_c']
                result.update(selected_family=family,native_ids_sha256=hashlib.sha256('\n'.join(expected).encode()).hexdigest(),
                    active_native_points=len(expected),fit_attempted=True,shared_start=common[1],shared_reference=common[0].reference)
                write(out/'result.json',result)
                diag=diagnostics();arms={};controls={}
                for scale,label in [(4.,'candidate'),(1.,'control')]:
                    # Exact RF-only short circuit: no failed-qualification
                    # candidate can pass the frozen acceptance conjunction.
                    if label=='control' and not all(arms[a]['qualified'] and
                        record['baseline'][a]['objective']-arms[a]['objective']>policy['objective_gain_threshold'] for a in ARMS):break
                    dd=candidate_context(d,z,scale,family)
                    for arm in ARMS:
                        fitted=fit(dd,z,arm,variant='damped_half',start=common[1],reference=common[0].reference,max_rounds=15,maxiter=35,maxfun=140)
                        p,ctx=e.build(dd,z,arm,np.asarray(fitted['reference']));x=np.asarray(fitted['x'])
                        gates=diag.gates(p,ctx,x,z,arm)
                        from algo06_science.position import family_score
                        _,details=family_score(ctx['families'],ctx,p,x,details=True)
                        boundary=[f['phase_boundary_mass'] for f in details]
                        fixed_ids=ids(p)==expected and len(expected)==len(set(expected))
                        inv=native_inventory(p,ctx);full_ids=inv['ids']
                        fixed_full_ids=full_ids==sorted(z['baseline_owners'][arm])
                        fixed_fitted_owners=inv['owners']==z['baseline_owners'][arm]
                        unrelated=[o for o in gates['reassigned_ids'] if z['baseline_owners'][arm][o]!=family]
                        qualified=bool(fitted['optimizer_success'] and fitted['phase_closed'] and gates['all_gates_pass'] and all(m<.01 for m in boundary) and fixed_ids and fixed_full_ids and fixed_fitted_owners and not gates['lost_ids'] and not unrelated)
                        item=dict(fitted,arm=arm,SD_scale=scale,qualified=qualified,native_ids_preserved=fixed_ids,
                            all_native_IDs_preserved=fixed_full_ids,all_native_union_sha256=ids_hash(full_ids),all_native_count=len(full_ids),
                            all_fitted_owners_preserved=fixed_fitted_owners,native_counts=inv['counts'],
                            fitted_owners_sha256=hashlib.sha256(json.dumps(inv['owners'],sort_keys=True).encode()).hexdigest(),
                            all_gates_pass=gates['all_gates_pass'],failed_gates=gates['failed_gates'],
                            exact_orbit_checks=gates['exact_orbit_checks'],mixture_gates_pass=gates['mixture_gates_pass'],
                            mixture_phase_boundary_masses=boundary,incumbent_lost=len(gates['lost_ids']),
                            unrelated_reassigned=len(unrelated),incumbent_reassigned=len(gates['reassigned_ids']),
                            incidental_unowned_extensions=len(gates['added_ids']),fixed_published_owners_sha256=hashlib.sha256(json.dumps(z['baseline_owners'][arm],sort_keys=True).encode()).hexdigest())
                        write(out/(label+'-'+arm+'.rf.json'),item)
                        # Geography evaluated only after this RF endpoint is sealed.
                        item['error_m']=error(x)
                        write(out/(label+'-'+arm+'.json'),item)
                        (controls if label=='control' else arms)[arm]=item
                gains={arm:dict(vs_matched_control=controls[arm]['objective']-arms[arm]['objective'] if arm in controls else None,
                    vs_saved_baseline=record['baseline'][arm]['objective']-arms[arm]['objective']) for arm in ARMS}
                control_valid=bool(controls and all(controls[a]['optimizer_success'] and controls[a]['phase_closed'] for a in ARMS))
                accepted=control_valid and all(arms[a]['qualified'] and all(v is not None and v>policy['objective_gain_threshold'] for v in gains[a].values()) for a in ARMS)
                result.update(candidate=arms,control=controls,objective_gains=gains,accepted=accepted,
                    matched_control_optimizer_phase_valid=control_valid,
                    status='accepted' if accepted else 'guard_rejected',
                    matched_control_status='complete' if controls else 'not_run_RF_candidate_qualification_or_saved_score_guard_failed',
                    reason='RF qualification and both normalized-score gains passed' if accepted else 'qualification or matched/saved RF gain guard failed')
    except Exception as exc:
        result.update(status='case_cap' if isinstance(exc,TimeoutError) else 'failed',reason=repr(exc),accepted=False)
    # Comparator GPS agreement is reporting only, after the RF decision is final.
    if 'd' in locals():
        result['baseline_geography_postdecision_audit']={a:dict(error_difference_m=error(x)-record['baseline'][a]['error_m'],
            absolute_tolerance_m=.02) for a,(p,x) in d['problems'].items()}
    result['seconds']=time.monotonic()-start_time
    result['selected_output']={a:dict(error_m=result['candidate'][a]['error_m'],objective=result['candidate'][a]['objective'],associated=result['baseline'][a]['associated'],source='SD4_half_candidate') if result['accepted'] else dict(result['baseline'][a],source='exact_saved_ALGO07') for a in ARMS}
    write(out/'result.json',result)
    print(case,result['status'],round(result['seconds'],1),flush=True)
    return result

def guarded_worker(case):
    folder=ROOT/'cases'/case;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=folder/'result.json'
        if path.exists() and read(path).get('status') not in ('running','total_cap','subprocess_failed','case_cap'):
            print(case,'existing complete receipt',flush=True);return read(path)
        if path.exists():
            previous=read(path);stamp=str(time.time_ns());write(folder/('prior-attempt-'+stamp+'.json'),previous)
        return worker(case)

def run_all():
    policy=read(ROOT/'protocol.json');began=time.monotonic();deadline=began+policy['total_wall_seconds']
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH='src:tools')
    (ROOT/'cases').mkdir(exist_ok=True)
    def launch(record):
        case=record['case'];path=ROOT/'cases'/case/'result.json'
        if path.exists() and read(path).get('status')!='running':return read(path)
        remaining=deadline-time.monotonic()
        if remaining<=0:return dict(case=case,status='total_cap',accepted=False,reason='1200s total deadline before attempt',seconds=0)
        try:
            with (ROOT/(case+'.log')).open('w') as f:
                subprocess.run([sys.executable,str(Path(__file__).resolve()),'--case',case],cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=min(600,remaining),check=True)
            return read(path)
        except Exception as exc:
            if path.exists() and read(path).get('status')!='running':return read(path)
            return dict(case=case,status='total_cap' if time.monotonic()>=deadline else 'subprocess_failed',accepted=False,reason=repr(exc),seconds=min(600,max(0,time.monotonic()-(deadline-remaining))))
    completed=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(launch,r) for r in policy['cases']]
        for future in as_completed(futures):
            result=future.result();completed.append(result)
            write(ROOT/'progress.json',dict(completed=len(completed),seconds=time.monotonic()-began,status_counts={s:sum(r['status']==s for r in completed) for s in {r['status'] for r in completed}}))
            print(result['case'],result['status'],len(completed),round(time.monotonic()-began),flush=True)
    for result in completed:
        path=ROOT/'cases'/result['case']/'result.json'
        if not path.exists() or read(path).get('status')=='running':
            record=next(r for r in policy['cases'] if r['case']==result['case'])
            result.update(dataset=record['dataset'],identities=record['identities'],baseline=record['baseline'],baseline_selected=record['selected'],
                selected_output={a:dict(record['baseline'][a],source='exact_saved_ALGO07') for a in ARMS},development_case=result['case'] in policy['development_cases'])
            write(path,result)
    write(ROOT/'completion.json',dict(status='complete_bounded_attempt_ledger',cases=len(completed),seconds=time.monotonic()-began,max_seconds=1200))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--all',action='store_true');ap.add_argument('--case');args=ap.parse_args()
    freeze() if args.freeze else run_all() if args.all else guarded_worker(args.case)
