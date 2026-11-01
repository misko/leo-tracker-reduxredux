"""Skill diagnostics: native curves, first-post TLEs, matched nuisance ladders."""
import argparse, hashlib, copy, csv
from pathlib import Path
import numpy as np
from sgp4.api import Satrec
from diagnose import ROOT,INPUT,ARMS,read,write,reconstruct,residual_stats
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon

SOURCE=INPUT.parent
MODELS={'L1_offset':(0.,False),'L2_small_drift':(.5,False),'L3_phase':(.5,True),'L4_rate_discrepancy':(2.,True)}

def polynomial(t,y):
    u=(t-t.mean())/max(np.ptp(t)/2,1);rows=[]
    for degree in range(5):
        X=np.vander(u,degree+1,increasing=True);coef=np.linalg.lstsq(X,y,rcond=None)[0];fit=X@coef;r=y-fit
        leverage=np.sum(X*np.linalg.pinv(X).T,axis=1)
        rows.append(dict(degree=degree,bic=float(len(t)*np.log(max(np.mean(r*r),1))+(degree+1)*np.log(len(t))),
            coefficients=coef,prediction=fit,residual=r,endpoint_leverage=leverage[[0,-1]],
            loo_endpoint_residual_hz=r[[0,-1]]/(1-leverage[[0,-1]]),**residual_stats(t,r)))
    winner=min(rows,key=lambda r:r['bic'])
    return dict(selected_degree=winner['degree'],rows=rows,
        caveat='Descriptive independent-noise BIC on native points; irregular correlation means it is not a calibrated evidence probability.')

def catalogue(case,z):
    out=ROOT/case;path=out/'tle-ledger.json'
    if path.exists():return read(path)
    causal=read(SOURCE/'catalogues'/(case+'.json'))['elements']
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));start=z['scan_receipt']['origin_utc_ns'];end=start+int(300e9);horizon=end+int(48*3600e9)
    snapshots=[s for s in archive.list_snapshots('space-track') if end<s.collected_utc_ns<=horizon]
    later={};seen={};ledger=[]
    for s in snapshots:
        records=parse_element_set_records(archive.read(s))
        for r in records:
            lines=[v for v in r.text.splitlines() if v.startswith(('1 ','2 '))]
            if len(lines)!=2:continue
            key=tuple(lines)
            if key in seen:epoch=seen[key]
            else:
                sat=Satrec.twoline2rv(*lines);epoch=int(round((sat.jdsatepoch-2440587.5+sat.jdsatepochF)*86400e9));seen[key]=epoch
            if not end<epoch<=horizon:continue
            n=str(r.satellite_number);old=later.get(n)
            if old and (old['element_epoch_utc_ns'],old['collected_utc_ns'])<=(epoch,s.collected_utc_ns):continue
            later[n]=dict(lines=lines,element_epoch_utc_ns=epoch,collected_utc_ns=s.collected_utc_ns,snapshot_digest=s.digest,
                element_sha256=hashlib.sha256(('\n'.join(lines)+'\n').encode()).hexdigest())
        ledger.append(dict(collected_utc_ns=s.collected_utc_ns,digest=s.digest))
    result=dict(causal=causal,later=later,snapshots=ledger,
        later_policy='minimum element epoch strictly after scan end; earliest archive collection tie break; collected within 48h after scan end; no score selection',
        scan_end_utc_ns=end,horizon_utc_ns=horizon)
    write(path,result);return result

def bank_for(records,origin):
    nums=np.array(sorted(map(int,records)));grid=np.arange(-40.,341.,1.)
    cat=ElementSetCatalogue(tuple(map(str,nums)),tuple(map(int,nums)),tuple(Satrec.twoline2rv(*records[str(n)]['lines']) for n in nums))
    pos,vel,good=ecef_states(cat,origin,grid);bank=dict(time_s=grid,position_km=pos[good],velocity_km_s=vel[good])
    return nums[good],bank,nums[~good].tolist()

def target_set(d,z,audit):
    p,_=d['problems']['fitted_c'];rank={}
    for a in ARMS:
        for f in audit['arms'][a]['family_influence']:rank[f['norad']]=rank.get(f['norad'],0)+f['shift_norm_km']
    numbers=sorted(rank,key=lambda n:(-rank[n],n))[:2];targets=[]
    for n in numbers:
        options=[(int(p.keep[sl].sum()),i,sl) for r,i,sl in zip(p.rows,p.members,p.slices) if r['candidate_norad']==n and p.keep[sl].any()]
        if options:
            _,i,sl=max(options);targets.append(dict(track_index=i,indices=np.flatnonzero(p.keep[sl]),role='influential_associated',assigned_norad=n))
        else:
            entries=[e for e in d['entries'] if e['norad']==n]+[e for f in d['families'] for e in f.entries if e['norad']==n]
            if entries:
                e=max(entries,key=lambda e:e['points']);i=e['track_index'];targets.append(dict(track_index=i,indices=np.arange(len(d['scan'].tracks[i]['times'])),role='influential_predictive',assigned_norad=n))
    if z['targets']:
        t=z['targets'][0];targets.append(dict(track_index=t['track_index'],indices=np.asarray(t['source_local_indices']),role='longest_unassociated',assigned_norad=None))
    return targets

def fit_candidates(t,y,q,nums,bank,position,assigned,phase0):
    ix=np.unique(np.linspace(0,len(t)-1,min(20,len(t))).astype(int));phases=np.arange(-30.,30.01,2.)
    candidates={m:set() for m in MODELS};coarse={m:np.full(len(nums),np.inf) for m in MODELS}
    # Both frozen-phase models share phase0 for fair per-cell candidate treatment.
    allphi=np.unique(np.r_[phases,phase0])
    for phi in allphi:
        f,e=phase_frequency_grid(bank,t[ix],*latlon(position),phase_seconds=phi);f=f*q
        for m,(rate,free) in MODELS.items():
            if not free and phi!=phase0:continue
            terms=profile_rate(y[ix],f,t[ix],rate_sigma_hz_s=rate,bias_sigma_hz=300.)
            cost=terms['cost']+((phi/5)**2 if free else 0.)
            coarse[m]=np.minimum(coarse[m],np.where(e.min(axis=1)>=0,cost,np.inf))
    for m in MODELS:
        candidates[m].update(int(j) for j in np.argsort(coarse[m])[:3] if np.isfinite(coarse[m][j]))
        if assigned in nums:candidates[m].add(int(np.flatnonzero(nums==assigned)[0]))
    results=[]
    for m,(rate,free) in MODELS.items():
        pp=np.linspace(-30,30,601) if free else np.array([phase0])
        for j in sorted(candidates[m]):
            bb=dict(time_s=bank['time_s'],position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),
                velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
            f,e=paired_phase_frequency(bb,np.tile(t,len(pp)),np.repeat(np.arange(len(pp)),len(t)),pp,*latlon(position));f=f.reshape(len(pp),-1)*q;e=e.reshape(len(pp),-1)
            terms=profile_rate(y,f,t,rate_sigma_hz_s=rate,bias_sigma_hz=300.)
            scores=terms['cost']+(pp/5)**2 if free else terms['cost'];scores=np.where(e.min(axis=1)>=0,scores,np.inf)
            if not np.isfinite(scores).any():continue
            best=int(np.argmin(scores));r=terms['residual_hz'][best];stats=residual_stats(t,r)
            rows=dict(model=m,norad=int(nums[j]),score=float(scores[best]),phase_s=float(pp[best]),
                alias=int(terms['alias'][best]),bias_hz=float(terms['bias_hz'][best]),rate_hz_s=float(terms['rate_hz_s'][best]),
                minimum_elevation_deg=float(e[best].min()),prediction_orbit_hz=f[best],residual_hz=r,
                physical_screen_pass=bool(stats['rms_hz']<=450 and abs(terms['bias_hz'][best])<=3000 and abs(terms['rate_hz_s'][best])<=2 and stats['noise']['noise_screen_pass']),
                **stats)
            rows['prediction_adjusted_hz']=f[best]+rows['bias_hz']+rows['rate_hz_s']*(t-t.mean())-rows['alias']*PERIOD
            # Diagnostic affine minimum at this same orbital phase, not identity evidence.
            rr=y-f[best];u=t-t.mean();rr=rr-rr.mean();slope=float(u@rr/(u@u));rows['free_affine_rms_hz']=float(np.sqrt(np.mean((rr-slope*u)**2)));rows['free_affine_rate_hz_s']=slope
            results.append(rows)
    return results

def run(case):
    z=read(INPUT/(case+'.json'));d=reconstruct(z);out=ROOT/case;audit=read(out/'audit.json');targetmeta=target_set(d,z,audit);ledger=catalogue(case,z)
    targets=[]
    for k,meta in enumerate(targetmeta):
        tr=d['scan'].tracks[meta['track_index']];ix=meta['indices'];times=np.asarray(tr['times'])[ix];ys={};raw=np.asarray(tr['values'])[ix]
        for arm,(p,x) in d['problems'].items():
            state=p.state(x);cal=d['scan'].hardware(tr,state['beta'])+tr['rf_hz']/11.5e9*d['scan'].rx_basis[meta['track_index']]@state['smooth'][tr['receiver']-1]
            ys[arm]=(tr['values']-cal)[ix]
        poly=polynomial(times,raw)
        targets.append(dict(index=k,meta=meta,key=tr['key'],receiver=tr['receiver'],channel=tr['channel'],rf_hz=tr['rf_hz'],
            times_s=times,raw_unwrapped_hz=raw,corrected_hz=ys,observation_ids=[tr['observation_ids'][i] for i in ix],pieces=tr['pieces'],polynomial=poly,results=[]))
    for regime in ('causal','later'):
        nums,bank,failed=bank_for(ledger[regime],z['scan_receipt']['origin_utc_ns'])
        write(out/(regime+'-search-coverage.json'),dict(catalogue_count=len(nums),failed_propagation=failed,models=MODELS,
            shortlist='all catalogue candidates screened on <=20 native times, top3 per model plus original identity exact-fitted on every target point',
            prior=dict(offset_hz=300,small_rate_hz_s=.5,discrepancy_rate_hz_s=2,phase_s=5,noise_hz=150),
            scope='per-source nuisance diagnostic with incumbent hardware frozen; not a shared calibration or acceptance test'))
        for target in targets:
            for arm,(p,x) in d['problems'].items():
                assigned=target['meta']['assigned_norad'];phase0=0.
                if assigned in d['scan'].norads:
                    j=list(d['scan'].norads).index(assigned);phase0=float(p.state(x)['phases'][j])
                rows=fit_candidates(np.array(target['times_s']),np.array(target['corrected_hz'][arm]),target['rf_hz']/11.5e9,nums,bank,x,assigned,phase0)
                target['results']+= [dict(r,regime=regime,arm=arm) for r in rows]
                print(case,regime,target['index'],arm,[(m,min([r for r in rows if r['model']==m],key=lambda r:r['score'])['norad']) for m in MODELS if any(r['model']==m for r in rows)],flush=True)
            write(out/f"target-{target['index']}.json",target)
    write(out/'targets.json',targets)
    inventory=[]
    for regime in ('causal','later'):
        for n,r in ledger[regime].items():
            inventory.append(dict(norad=n,regime=regime,epoch_utc_ns=r['element_epoch_utc_ns'],collection_utc_ns=r['collected_utc_ns'],
                age_h=(z['scan_receipt']['origin_utc_ns']-r['element_epoch_utc_ns'])/3.6e12,
                sha256=hashlib.sha256(('\n'.join(r['lines'])+'\n').encode()).hexdigest()))
    with (out/'tle_inventory.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=inventory[0]);w.writeheader();w.writerows(inventory)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');ap.add_argument('--archive-only',action='store_true');args=ap.parse_args()
    if args.archive_only:catalogue(args.case,read(INPUT/(args.case+'.json')))
    else:run(args.case)
