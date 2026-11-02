"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import copy
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from . import reconsider as rec
from .reconsider import read, write, sha, objective, previous, ARMS
from algo06_science import position
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from . import diagnose
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached

OUT=Path('.')
ROOTS={}

def collect_history(request):
    raise RuntimeError('ALGO07 requires a private causal history collector')


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
        exported=collect_history(request);write(export_path,dict(request=request,export=exported))
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
                r['phase_boundary_masses']=[f['phase_boundary_mass'] for f in details]
                r['endpoint_latlon']=list(r['latlon'])
                r['mixture_phase_interior']=all(f['phase_boundary_mass']<.01 for f in details)
                r['qualified'] &= r['mixture_phase_interior']
                ids=sorted(o for tr in r['tracks'] for o in tr['observation_ids'])
                if ids!=expected or len(ids)!=len(set(ids)):raise ValueError('Native evidence changed')
                r['unexpected_reassigned_ids']=[o for o in r['reassigned_ids'] if z['baseline_owners'][a][o] not in allowed]
                r['qualified'] &= not r['unexpected_reassigned_ids']
                r['owners_sha256']=hashlib.sha256(json.dumps(r['proposed_owners'],sort_keys=True).encode()).hexdigest()
                r['native_ids_sha256']=hashlib.sha256('\n'.join(ids).encode()).hexdigest()
                r.update(arm=a,start=label,status='complete')
            except Exception as exc:r=dict(arm=a,start=label,status='incomplete',qualified=False,reason=repr(exc),seconds=time.monotonic()-began)
            rows.append(r)
            write(path,rows)
    return rows

def paired(rows):
    return {a:min((r for r in rows if r['arm']==a and r.get('qualified')),key=lambda r:r['objective'],default=None) for a in ARMS}

# Every numerical entry point must use this exact reconstruction adapter.
rec.build=build
diagnose.build=build
previous.build=build
rec.ex.ORIGINAL_BUILD=build

def configure(input_root, output_root, *, history_collector=None, collect_history=None):
    """Configure private roots and the caller-owned read-only history port."""
    global OUT, ROOTS
    OUT=Path(output_root).resolve()
    ROOTS={'SCAN':Path(input_root).resolve()}
    rec.CATALOGUES=ROOTS['SCAN']/'catalogues'
    rec.ex.PRIOR=OUT/'ledgers'
    callback=collect_history if collect_history is not None else history_collector
    if callback is not None:
        globals()['collect_history']=callback
    rec.build=build
    diagnose.build=build
    previous.build=build
    rec.ex.ORIGINAL_BUILD=build
