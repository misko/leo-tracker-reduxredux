"""Frozen four-cell causal reassociation study. Offline research only.

Evaluation coordinates enter the inherited endpoint reporter only. Screening,
controls and decisions consume RF scores, gates and causal provenance.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import fcntl
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
PRIOR = OUT.parent / '2026_11_01_ds26_reconsideration'
sys.path.insert(0, str(PRIOR))
import reconsider as rec
from reconsider import read, write, sha, build, objective, previous, ARMS
from algo06_science import position as position
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
import diagnose
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached

DATA = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports')
ROOTS = dict(DS26=DATA/'2026_11_01_ds26_ds27_causal_variants',
             DS27=DATA/'2026_11_01_ds26_ds27_causal_variants',
             DS28=DATA/'2026_11_01_ds28_revision2_evaluation')
METHODS = ('ALGO06', 'history_only', 'reassociation_only', 'combined')


def build(d,z,arm,reference,omit=None,phase_scale=1.):
    """Replay shared conditional attachments as well as gap attachments."""
    keep=d['keep'].copy();base=d['problems'][arm][0]
    for row,sl in zip(base.rows,base.slices):
        if row['candidate_norad']==omit:keep[sl]=False
    entries=[e for e in d['entries'] if e['norad']!=omit]
    kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
    p=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],d['means'],
        dict(d['model'],multiplier=d['model']['multiplier']*phase_scale),[],**kw)
    attach_event_predictive(p,entries,d['powers'])
    source=z.get('gap_selected') or z.get('selected')
    if source and ('path' in source or source.get('kind')=='shared_family'):
        protocol=read(Path(source.get('path',source.get('trial')))/'protocol.json')
        if z.get('gap_selected') or protocol.get('conditional_satellite_refresh'):
            from conditional_satellite_refresh import attach_conditional_satellite_refresh
            keys={e['component'] for e in protocol['targets']}
            ids=sorted({e['candidate_index'] for e in entries if e['component'] in keys})
            if ids:attach_conditional_satellite_refresh(p,entries,d['powers'],ids)
    return cached(p),dict(d,entries=entries,families=[f for f in d['families'] if f.entries[0]['norad']!=omit])


# All imported numerical entry points use this same reconstruction adapter.
rec.build=build
diagnose.build=build
previous.build=build
rec.ex.ORIGINAL_BUILD=build


def freeze():
    if (OUT/'protocol.json').exists():
        raise FileExistsError('Frozen protocol already exists')
    cohort=[]
    for dataset, root in ROOTS.items():
        for path in sorted((root/'inputs').glob(dataset+'-*.json')):
            case=path.stem
            sources=[path, root/'catalogues'/(case+'.json'), root/'position'/case/'result.json']
            cohort.append(dict(case=case, dataset=dataset, stage='validation' if dataset=='DS28' else 'evaluation',
                               sources={str(p):sha(p) for p in sources}))
    write(OUT/'protocol.json', dict(
        base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        created_utc_ns=time.time_ns(), methods=METHODS, cohort=cohort,
        code_sha256={str(p):sha(p) for p in [Path(__file__),PRIOR/'reconsider.py',PRIOR/'read_history.py']},
        unavailable_validation=['DS28-0001','DS28-0016'],
        baseline='Exact saved ALGO06 72h/30s accepted recovery composed on input baseline, not pre-recovery inputs alone',
        history='Fill absent or invalid previous elements for active and proposed identities with newest genuinely earlier causal archive element; preserve valid existing history',
        causal='Nominal epoch and collection <= scan cutoff; discovery age <=72h; previous archive collection within72h and epoch >=1s earlier than nominal',
        nomination='Frozen reconsideration rule: top2 RF influence families >=.5km, >=30 points >=2 tracks; full causal bank, two longest tracks, top2 per track/arm; same nominees in all variants',
        predictive='Frozen five random synchronized5s blocks with5s guards; positive mean and >=4/5 wins botharms. Full-data nomination makes this conditional evidence',
        proposals='Whole-family top2 only; diagnostic partitions cannot be accepted and are not refitted',
        budget='15 phase rounds,40 SLSQP iterations; same published fitted-c and family-omitted fitted-c starts for all hypotheses,controls and botharms',
        history_only_starts='published fitted-c and published c0 endpoints, same in botharms',
        acceptance='Original gates, exact orbit, phase closure <=.01s, optimizer success, all native owners preserved, no unintended reassignment; both arms RF gain beyond2log(shortlist size) versus best qualified matched-prior incumbent continuation. Also retain published objective as a conservative control bound',
        history_only_acceptance='Both arms qualified and normalized RF objective improves over matched original-prior continuation and published baseline; absent new history returns exact baseline',
        continuation='Matched control is additional conservatism vs preceding prototype; never publish a continuation-only improvement as reassociation',
        scope='One replacement per scan, no chaining; fixed native evidence/weights; no age penalty; no truth-informed rule changes',
        region=dict(center=[37.906,-122.545],width_km=25),
        external_validation='DS28 excluded from prototype development; existing dataset previously analyzed for ALGO06, not wholly untouched data; combined is prespecified primary candidate',
        seed=rec.SEED, workers=10, process_limit_s=1800, production_changed=False))


def load_case(case):
    """Restore every accepted ALGO06 family and exact saved phase endpoint."""
    root=ROOTS[case[:4]];z=read(root/'inputs'/(case+'.json'));d=rec.reconstruct(z)
    result=read(root/'position'/case/'result.json');decision=result['decisions']['72h_30s']
    replay=dict(pre_recovery=d['replay_checks'], recovery=decision)
    if decision['status']=='qualified':
        t=result['trials'][decision['trial']]
        screen=read(root/'screen'/case/'result.json')
        target=next(t for t in screen['targets'] if t['source']['fragment_id']==decision['source'])
        summary=next(s for s in target['summaries'] if s['policy']=='72h_30s')
        winner=summary['arms']['c0']['folds']['full']['winner']
        saved=position.ROOT;position.ROOT=root
        try:entry=position.add_target(d,z,target['source'],winner)
        finally:position.ROOT=saved
        assert entry==t['entry'], 'ALGO06 native recovery entry mismatch'
        f=position.NewFamily(position.prediction_scan(d['scan'],30),[entry],d['model'],
                             phase_step=.05,phase_limit_s=30,allow_uncalibrated_label=True)
        d['families']=d['families']+[f];z=copy.deepcopy(z)
        replay['algo06']={}
        for a in ARMS:
            row=t['arms'][a];x=np.asarray(row['endpoint_east_north_km'])
            p,_=build(d,z,a,np.asarray(row['phase_reference']))
            delta=float(p.calculate(x)['negative_twice_elbo']+position.family_score(d['families'],d,p,x)-row['negative_twice_elbo'])
            if abs(delta)>1e-4:raise ValueError(f'ALGO06 full replay mismatch {a} {delta}')
            d['problems'][a]=(p,x);z['baseline_arms'][a]=row
            for o in entry['observation_ids']:
                if o in z['baseline_owners'][a]:raise ValueError('Duplicate ALGO06 owner')
                z['baseline_owners'][a][o]=entry['norad']
            replay['algo06'][a]=dict(objective_difference=delta,added_points=len(entry['observation_ids']))
    replay['rebuilt']={}
    for a,(p,x) in d['problems'].items():
        rebuilt,_=build(d,z,a,p.reference)
        delta=objective(rebuilt,d,x)-objective(p,d,x)
        if abs(delta)>1e-4:raise ValueError(f'Rebuilt baseline objective mismatch {a}: {delta}')
        replay['rebuilt'][a]=delta
    return d,z,replay


def eligible_previous(n, current, receipt, text_ids, cutoff):
    old=receipt.get('sources',{}).get(str(n))
    return bool(old and n in text_ids and old['collected_utc_ns']<=cutoff and
                current-old['epoch_utc_ns']>=1_000_000_000)


def complete_history(d,z,case,identities,folder):
    """Fill missing history without swapping existing valid prior epochs."""
    from sgp4.api import Satrec
    from leo.sky.propagation import parse_element_set_records
    scan=d['scan'];path=scan.previous_tle_path;receipt=read(path.parent/'previous_receipt.json')
    old_records={int(r.satellite_number):r for r in parse_element_set_records(path.read_text())}
    cutoff=z['scan_receipt']['cutoff_utc_ns'];ledger=rec.causal_records(case,z);latest={}
    for n in sorted(set(map(int,identities))):
        element=scan.elements.get(str(n),ledger.get(str(n)))
        if element is None:raise ValueError(f'Missing nominal element {n}')
        sat=Satrec.twoline2rv(*element['lines'])
        epoch=int(round((sat.jdsatepoch-2440587.5+sat.jdsatepochF)*86400e9))
        prov=element.get('provenance',element)
        if epoch>cutoff or prov.get('collected_utc_ns',cutoff+1)>cutoff:
            raise ValueError(f'Unverified causal nominal {n}')
        if not eligible_previous(n,epoch,receipt,old_records,cutoff):latest[str(n)]=epoch
    if not latest:return d,dict(requested=[],available=[],missing=[],changed=False)
    request=dict(cutoff=cutoff,latest=latest);export_path=folder/'export.json'
    if export_path.exists():
        cached=read(export_path)
        if cached['request']!=request:raise ValueError('History cache mismatch')
        exported=cached['export']
    else:
        proc=subprocess.run(['sudo','-n','env','PYTHONDONTWRITEBYTECODE=1',
            'PYTHONPATH='+str(REPO/'src'),sys.executable,str(PRIOR/'read_history.py')],
            input=json.dumps(request),text=True,capture_output=True,check=True,timeout=90)
        exported=json.loads(proc.stdout);write(export_path,dict(request=request,export=exported))
    chosen={int(n):r for n,r in exported['chosen'].items()}
    for n,r in chosen.items():
        if not (cutoff-int(72*3.6e12)<=r['collected_utc_ns']<=cutoff and latest[str(n)]-r['epoch_utc_ns']>=1e9):
            raise ValueError('Invalid causal history export')
    info=dict(requested=list(latest),available=sorted(chosen),missing=sorted(set(map(int,latest))-set(chosen)),changed=bool(chosen),old_sha256=sha(path))
    if not chosen:return d,info
    lines=[]
    for n,r in old_records.items():
        if n not in chosen:lines.append(r.text.strip())
    for n,r in chosen.items():
        lines.append('\n'.join(r['lines']));receipt['sources'][str(n)]={k:v for k,v in r.items() if k!='lines'}
    new=folder/'previous.tle';new.parent.mkdir(parents=True,exist_ok=True);new.write_text('\n'.join(lines)+'\n')
    write(new.parent/'previous_receipt.json',receipt)
    s=copy.copy(scan);s.receipt=dict(s.receipt,previous_tle_sha256=sha(new));s.previous_tle_path=new
    for attr in ('previous_shape_cache','diagnostic_phase_width_cache','causal_uncertainty_modes','reference_motion_derivatives','mean_motion_derivatives'):
        if hasattr(s,attr):delattr(s,attr)
    dd=dict(d,scan=s,problems=dict(d['problems']))
    # Predictive mixtures also consume the corrected causal uncertainty.
    dd['families']=[position.NewFamily(position.prediction_scan(s,f.phase_limit_s),f.entries,d['model'],
        phase_step=f.receipt['phase_step_s'],phase_limit_s=f.phase_limit_s,allow_uncalibrated_label=True) for f in d['families']]
    labels=d['problems']['fitted_c'][0].labels
    _,receipts=phase_widths(s,labels);forecast=forecast_phase_mean(receipts,d['model']['shrinkage'])
    dd['means']=np.array([forecast[k] if int(s.norads[j]) in chosen else d['means'][k] for k,j in enumerate(labels)])
    for a,(p,x) in d['problems'].items():dd['problems'][a]=(build(dd,z,a,p.reference)[0],x)
    info['new_sha256']=sha(new)
    return dd,info


def active_ids(d):
    return {int(d['scan'].norads[j]) for j in d['problems']['fitted_c'][0].labels} | {
        e['norad'] for e in d['entries']} | {e['norad'] for f in d['families'] for e in f.entries}


def rank_families(d,z):
    """Identical trigger, omitting unused omission Hessian evaluations."""
    rows={};eye=np.eye(2)*.05
    for a,(p,x) in d['problems'].items():
        g,H=rec.derivatives(lambda v:objective(p,d,v),x)
        for n in sorted({r['candidate_norad'] for r,s in zip(p.rows,p.slices) if p.keep[s].any()}):
            q,dd=build(d,z,a,p.reference,omit=n)
            go=np.array([(objective(q,dd,x+v)-objective(q,dd,x-v))/.1 for v in eye])
            displacement=float(np.linalg.norm(np.linalg.pinv(H)@(go-g)))
            entries=[(r,s) for r,s in zip(p.rows,p.slices) if r['candidate_norad']==n and p.keep[s].any()]
            item=rows.setdefault(n,dict(norad=n,rank_score=0.,arms={},points=sum(int(p.keep[s].sum()) for r,s in entries),tracks=len(entries)))
            item['arms'][a]=dict(local_displacement_km=displacement,hessian_eigenvalues=np.linalg.eigvalsh(H))
            item['rank_score']+=displacement
    result=sorted(rows.values(),key=lambda r:(-r['rank_score'],r['norad']))
    selected=[r['norad'] for r in result if r['rank_score']>=.5 and r['points']>=30 and r['tracks']>=2][:2]
    return result,selected


def remap(d,z,case,h):
    saved=rec.ex.PRIOR;rec.ex.PRIOR=OUT/'ledgers'
    try:dd=rec.ex.remap(d,z,case,h)
    finally:rec.ex.PRIOR=saved
    base=dd['problems']['fitted_c'][0]
    _,receipt=phase_widths(dd['scan'],base.labels)
    forecast=forecast_phase_mean(receipt,dd['model']['shrinkage'])
    means=dict(zip(d['problems']['fitted_c'][0].labels,d['means']))
    dd['means']=np.array([means.get(j,forecast[k]) for k,j in enumerate(base.labels)])
    for a,(p,x) in list(dd['problems'].items()):dd['problems'][a]=(build(dd,z,a,p.reference)[0],x)
    return dd


def fit_rows(d,z,starts,allowed,path):
    rows=read(path) if path.exists() else []
    base=d['problems']['fitted_c'][0]
    expected=sorted(o for i,sl in zip(base.members,base.slices) for o,u in zip(d['scan'].tracks[i]['observation_ids'],base.keep[sl]) if u)
    for a in ARMS:
        for label,start in starts.items():
            if any(r['arm']==a and r['start']==label for r in rows):continue
            began=time.monotonic()
            try:
                r=previous.fit(d,z,a,start,True,rounds=15)
                p,ctx=build(d,z,a,np.asarray(r['reference']))
                _,details=position.family_score(ctx['families'],ctx,p,np.asarray(r['x']),details=True)
                r['mixture_phase_interior']=all(f['phase_boundary_mass']<.01 for f in details)
                r['qualified'] &= r['mixture_phase_interior']
                ids=sorted(o for tr in r['tracks'] for o in tr['observation_ids'])
                if ids!=expected or len(ids)!=len(set(ids)):raise ValueError('Native evidence changed')
                r['unexpected_reassigned_ids']=[o for o in r['reassigned_ids'] if z['baseline_owners'][a][o] not in allowed]
                r['qualified'] &= not r['unexpected_reassigned_ids']
                r['owners_sha256']=hashlib.sha256(json.dumps(r.pop('proposed_owners'),sort_keys=True).encode()).hexdigest()
                r['native_ids_sha256']=hashlib.sha256('\n'.join(ids).encode()).hexdigest()
                r.update(arm=a,start=label,status='complete')
            except Exception as exc:r=dict(arm=a,start=label,status='incomplete',qualified=False,reason=repr(exc),seconds=time.monotonic()-began)
            rows.append(r)
            write(path,rows)
    return rows


def paired(rows):
    return {a:min((r for r in rows if r['arm']==a and r.get('qualified')),key=lambda r:r['objective'],default=None) for a in ARMS}


def choose(records,baseline):
    eligible=[r for r in records if r.get('accepted')]
    if not eligible:return dict(selected=None,final=baseline)
    best=max(eligible,key=lambda r:sum(r['gains'].values()))
    return dict(selected=best['name'],final={a:dict(x=r['x'],error_m=r['error_m'],objective=r['objective'],
        associated=baseline[a]['associated'],rms_hz=r['rms_hz']) for a,r in best['pair'].items()})


def run(case):
    began=time.monotonic();out=OUT/case;out.mkdir(parents=True,exist_ok=True)
    rec.CATALOGUES=ROOTS[case[:4]]/'catalogues'
    d,z,replay=load_case(case);write(out/'replay.json',replay)
    ledger=rec.causal_records(case,z);write(OUT/'ledgers'/case/'tle-ledger.json',dict(causal=ledger))
    baseline={a:dict(x=x,error_m=previous.error(x),objective=objective(p,d,x),associated=len(z['baseline_owners'][a]),
                    rms_hz=float(np.sqrt(np.mean(p.calculate(x)['conditional_residual_hz'][p.keep]**2)))) for a,(p,x) in d['problems'].items()}
    write(out/'baseline.json',baseline)
    hd,hi=complete_history(d,z,case,active_ids(d),out/'incumbent_history')
    write(out/'history.json',hi)
    methods={m:dict(selected=None,final=baseline) for m in METHODS};hist_records=[]
    if hi['changed']:
        starts={a:d['problems'][a][1] for a in ARMS}
        old=paired(fit_rows(d,z,starts,set(),out/'history_control.json'))
        new=paired(fit_rows(hd,z,starts,set(),out/'history_candidate.json'))
        ok=all(old.values()) and all(new.values())
        gains={a:min(old[a]['objective'],baseline[a]['objective'])-new[a]['objective'] for a in ARMS} if ok else {}
        hist_records=[dict(name='complete_history',pair=new,gains=gains,accepted=bool(ok and all(v>0 for v in gains.values())))]
        methods['history_only']=choose(hist_records,baseline)
    ranking,targets=rank_families(d,z)
    write(out/'trigger.json',dict(ranking=ranking,selected=targets))
    records={m:[] for m in ('reassociation_only','combined')};failures=[]
    if targets:nums,bank,propagation_failed=rec.bank_for(ledger,z['scan_receipt']['origin_utc_ns'])
    else:nums=[];propagation_failed=[]
    for n in targets:
        folder=out/str(n);folder.mkdir(exist_ok=True)
        try:
            screened=read(folder/'screen.json') if (folder/'screen.json').exists() else rec.screen(d,z,n,nums,bank,folder)
            write(folder/'screen.json',screened)
        except Exception as exc:
            failures.append(dict(target=n,stage='screen',reason=repr(exc)));continue
        proposals=[h for h in screened.get('proposals',[]) if 'prediction_limit' not in h and all(h['predictive'][a]['pass_check'] for a in ARMS)]
        if not proposals:continue
        starts={'published':d['problems']['fitted_c'][1],'family_omitted':np.asarray(screened['cavity']['fitted_c']['x'])}
        controls={False:paired(fit_rows(d,z,starts,set(),folder/'control_original.json'))}
        controls[True]=paired(fit_rows(hd,z,starts,set(),folder/'control_history.json')) if hi['changed'] else controls[False]
        for h in proposals:
            for m,history in [('reassociation_only',False),('combined',True)]:
                trial=folder/(h['name']+'-'+m);trial.mkdir(exist_ok=True)
                try:
                    base=hd if history else d
                    if history:base,hinfo=complete_history(base,z,case,set(h['mapping'].values()),trial/'history')
                    else:hinfo=dict(changed=False)
                    dd=remap(base,z,case,h)
                    rows=fit_rows(dd,z,starts,set(h['allowed_families']),trial/'fits.json');pair=paired(rows);control=controls[history]
                    ok=all(pair.values()) and all(control.values())
                    bound={a:min(control[a]['objective'],objective((hd if history else d)['problems'][a][0],hd if history else d,d['problems'][a][1])) for a in ARMS} if all(control.values()) else {}
                    gains={a:bound[a]-pair[a]['objective']-h['penalty'] for a in ARMS} if ok else {}
                    record=dict(name=h['name'],target=n,hypothesis=h,history=hinfo,pair=pair,control=control,gains=gains,
                                accepted=bool(ok and all(v>0 for v in gains.values())),fits_path=str(trial/'fits.json'))
                except Exception as exc:record=dict(name=h['name'],target=n,hypothesis=h,accepted=False,reason=repr(exc))
                records[m].append(record);write(trial/'decision.json',record)
                print(case,m,h['name'],record['accepted'],flush=True)
    for m in records:
        methods[m]=choose(records[m],baseline)
    # The combined cell can also retain an accepted history-only correction.
    if hist_records and hist_records[0]['accepted'] and methods['combined']['selected'] is None:
        methods['combined']=methods['history_only']
    write(out/'result.json',dict(case=case,baseline=baseline,methods=methods,history=hi,history_records=hist_records,
          records=records,targets=targets,failures=failures,propagation_failures=propagation_failed,
          seconds=time.monotonic()-began,production_changed=False))
    print(case,'DONE',{m:r['selected'] for m,r in methods.items()},flush=True)


def batch(stage,workers):
    protocol=read(OUT/'protocol.json');cohort=[r for r in protocol['cohort'] if r['stage']==stage];results=[]
    def work(row):
        case=row['case'];out=OUT/case
        if (out/'result.json').exists():return dict(case=case,status='cached')
        for path,digest in row['sources'].items():
            if sha(path)!=digest:raise ValueError('Frozen source changed: '+path)
        log=OUT/'logs'/(case+'.log');log.parent.mkdir(exist_ok=True)
        began=time.monotonic()
        with log.open('w') as handle:
            try:
                proc=subprocess.run([sys.executable,__file__,'case',case],stdout=handle,stderr=subprocess.STDOUT,
                    timeout=protocol['process_limit_s'],env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
                status='complete' if proc.returncode==0 else 'failed'
            except subprocess.TimeoutExpired:status='timeout'
        return dict(case=case,status=status,seconds=time.monotonic()-began,log=str(log))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(work,r) for r in cohort]):
            r=f.result();results.append(r);write(OUT/(stage+'-jobs.json'),results);print(len(results),len(cohort),r,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','case','evaluation','validation']);p.add_argument('case',nargs='?');p.add_argument('--workers',type=int,default=10);a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='case':
        # Independent queue processes may meet at a late case. A single writer
        # and attempt receipt avoid duplicated fitting or extra search budget.
        locks=OUT/'locks';locks.mkdir(exist_ok=True)
        with (locks/(a.case+'.lock')).open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            folder=OUT/a.case;folder.mkdir(exist_ok=True)
            if not (folder/'result.json').exists():
                attempt=folder/'attempt.json'
                if attempt.exists():raise RuntimeError('Prior bounded attempt incomplete; do not silently grant a second budget')
                write(attempt,dict(started_utc_ns=time.time_ns(),code_sha256=sha(__file__)))
                run(a.case)
    else:batch(a.action,a.workers)
