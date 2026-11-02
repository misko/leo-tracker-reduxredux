"""Bounded research adapter: actual ALGO06 composition, immutable native inputs."""
import argparse, csv, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np

REPO=Path(__file__).resolve().parents[3]
OLD=REPO/'reports/2026_11_01_ds26_outlier_root_cause'
sys.path.insert(0,str(OLD))
import track_debug as legacy
from algo07_science import engine
from algo06_science.common import read,write
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
from sgp4.api import Satrec

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
CASES=['DS26-'+s for s in ['0203','0070','0072','0221','0044','0100','0014','0201','0309','0209']]
ARMS=('c0','fitted_c')
MODELS=legacy.MODELS

def setup():
    engine.configure(SOURCE,ROOT/'engine-cache')
    engine.ROOTS={'DS26':SOURCE}

def archive(cases):
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records
    reader=TleArchiveReader(Path('/var/lib/leo/tle'))
    requests=[]
    for case in cases:
        out=ROOT/case;out.mkdir(parents=True,exist_ok=True)
        z=read(SOURCE/'inputs'/f'{case}.json');end=z['scan_receipt']['origin_utc_ns']+int(300e9)
        causal=read(SOURCE/'catalogues'/f'{case}.json')['elements'];cutoff=z['scan_receipt']['cutoff_utc_ns']
        for r in causal.values():
            assert 0<=cutoff-r['element_epoch_utc_ns']<=72*3.6e12 and r['collected_utc_ns']<=cutoff
        old=OLD/case/'tle-ledger.json'
        if old.exists():
            prior=read(old)
            if prior['causal']==causal and prior['scan_end_utc_ns']==end and prior['horizon_utc_ns']==end+48*3600e9:
                write(out/'tle-ledger.json',dict(prior,reused_from=str(old),reused_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),causal_verified=True))
                continue
        requests.append(dict(case=case,causal=causal,end=end,horizon=end+int(48*3600e9),later={},snapshots=[]))
    epochs={}
    for snap in reader.list_snapshots('space-track'):
        eligible=[r for r in requests if r['end']<snap.collected_utc_ns<=r['horizon']]
        if not eligible:continue
        records=parse_element_set_records(reader.read(snap))
        for r in eligible:r['snapshots'].append(dict(collected_utc_ns=snap.collected_utc_ns,digest=snap.digest))
        for element in records:
            lines=[x for x in element.text.splitlines() if x.startswith(('1 ','2 '))]
            if len(lines)!=2:continue
            key=tuple(lines)
            if key not in epochs:
                sat=Satrec.twoline2rv(*lines);epochs[key]=int(round((sat.jdsatepoch-2440587.5+sat.jdsatepochF)*86400e9))
            epoch=epochs[key];n=str(element.satellite_number)
            for req in eligible:
                if not req['end']<epoch<=req['horizon']:continue
                old=req['later'].get(n)
                if old and (old['element_epoch_utc_ns'],old['collected_utc_ns'])<=(epoch,snap.collected_utc_ns):continue
                req['later'][n]=dict(lines=lines,element_epoch_utc_ns=epoch,collected_utc_ns=snap.collected_utc_ns,snapshot_digest=snap.digest,element_sha256=hashlib.sha256(('\n'.join(lines)+'\n').encode()).hexdigest())
    for r in requests:
        write(ROOT/r['case']/'tle-ledger.json',dict(causal=r['causal'],later=r['later'],snapshots=r['snapshots'],scan_end_utc_ns=r['end'],horizon_utc_ns=r['horizon'],causal_verified=True,later_policy='minimum element epoch strictly after scan end; earliest collection tie break; collected within 48h; full catalogue; no causal substitution'))
        print('archive',r['case'],len(r['causal']),len(r['later']),flush=True)

def targets(d,z,case):
    ranking_path=REPO/'reports/2026_11_01_reconsideration_population'/case/'trigger.json'
    ranking=read(ranking_path)['ranking']
    fresh=ROOT.parent/'diagnostics'/case/'fit-plan.json'
    if fresh.exists():
        ranking_path=fresh;rank=read(fresh)['rank'];ranking=[dict(norad=int(n),rank_score=v) for n,v in sorted(rank.items(),key=lambda v:(-v[1],int(v[0])))]
    p=d['problems']['fitted_c'][0];result=[]
    for rank in ranking[:2]:
        n=rank['norad'];options=[]
        for row,i,sl in zip(p.rows,p.members,p.slices):
            ix=np.flatnonzero(p.keep[sl]);tr=d['scan'].tracks[i]
            if row['candidate_norad']==n and len(ix):options.append((float(np.ptp(tr['times'][ix])),len(ix),i,ix))
        for e in d['entries']+[e for f in d['families'] for e in f.entries]:
            if e['norad']==n:
                i=e['track_index'];tr=d['scan'].tracks[i];ids=set(e['observation_ids']);ix=np.array([k for k,o in enumerate(tr['observation_ids']) if o in ids])
                if len(ix):options.append((float(np.ptp(tr['times'][ix])),len(ix),i,ix))
        if options:
            _,_,i,ix=max(options,key=lambda v:(v[0],v[1]));result.append(dict(track_index=i,indices=ix,role='influential_associated',assigned_norad=n))
    if z['targets']:
        selected=max(z['targets'],key=lambda t:(t.get('duration_s',t.get('span_s',0)),len(t['source_local_indices'])))
        result.append(dict(track_index=selected['track_index'],indices=np.asarray(selected['source_local_indices']),role='longest_unassociated',assigned_norad=None))
    return result,dict(path=str(ranking_path),sha256=hashlib.sha256(ranking_path.read_bytes()).hexdigest(),ranking=ranking,rule='top2 summed c-arm influence, then longest retained duration per family; longest saved unassociated source')

def fit_matched(t,ys,q,nums,bank,positions,assigned,phase0):
    ix=np.unique(np.linspace(0,len(t)-1,min(20,len(t))).astype(int));allphi=np.unique(np.r_[np.arange(-30.,30.01,2.),list(phase0.values())])
    coarse={m:np.zeros(len(nums)) for m in MODELS}
    for arm in ARMS:
        costs={m:np.full(len(nums),np.inf) for m in MODELS}
        for phi in allphi:
            f,e=phase_frequency_grid(bank,t[ix],*latlon(positions[arm]),phase_seconds=phi);f=f*q
            for m,(rate,free) in MODELS.items():
                if not free and phi!=phase0[arm]:continue
                score=profile_rate(ys[arm][ix],f,t[ix],rate_sigma_hz_s=rate,bias_sigma_hz=300.)['cost']+((phi/5)**2 if free else 0.)
                costs[m]=np.minimum(costs[m],np.where(e.min(axis=1)>=0,score,np.inf))
        for m in MODELS:coarse[m]+=costs[m]
    rows=[];coverage=[]
    for m,(rate,free) in MODELS.items():
        indices=[int(j) for j in np.argsort(coarse[m])[:3] if np.isfinite(coarse[m][j])]
        if assigned in nums:
            j=int(np.flatnonzero(nums==assigned)[0])
            if j not in indices:indices.append(j)
        coverage.append(dict(model=m,coarse_count=len(nums),exact_nominees=[int(nums[j]) for j in indices]))
        for arm in ARMS:
            pp=np.linspace(-30,30,601) if free else np.array([phase0[arm]])
            for j in indices:
                bb=dict(time_s=bank['time_s'],position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
                f,e=paired_phase_frequency(bb,np.tile(t,len(pp)),np.repeat(np.arange(len(pp)),len(t)),pp,*latlon(positions[arm]));f=f.reshape(len(pp),-1)*q;e=e.reshape(len(pp),-1)
                terms=profile_rate(ys[arm],f,t,rate_sigma_hz_s=rate,bias_sigma_hz=300.);score=terms['cost']+((pp/5)**2 if free else 0.)
                score=np.where(e.min(axis=1)>=0,score,np.inf)
                if not np.isfinite(score).any():continue
                k=int(np.argmin(score));r=terms['residual_hz'][k];stats=legacy.residual_stats(t,r)
                row=dict(model=m,arm=arm,norad=int(nums[j]),score=float(score[k]),phase_s=float(pp[k]),alias=int(terms['alias'][k]),bias_hz=float(terms['bias_hz'][k]),rate_hz_s=float(terms['rate_hz_s'][k]),minimum_elevation_deg=float(e[k].min()),prediction_orbit_hz=f[k],residual_hz=r,**stats)
                row['prediction_adjusted_hz']=f[k]+row['bias_hz']+row['rate_hz_s']*(t-t.mean())-row['alias']*PERIOD
                row['physical_screen_pass']=bool(stats['rms_hz']<=450 and abs(row['bias_hz'])<=3000 and abs(row['rate_hz_s'])<=2 and stats['noise']['noise_screen_pass'])
                row['gate_margins']=dict(rms_hz=450-stats['rms_hz'],bias_hz=3000-abs(row['bias_hz']),rate_hz_s=2-abs(row['rate_hz_s']))
                rows.append(row)
    return rows,coverage

def run(case):
    setup();out=ROOT/case;out.mkdir(parents=True,exist_ok=True);began=time.monotonic();d,z,replay=engine.load_case(case)
    meta,ranking=targets(d,z,case);ledger=read(out/'tle-ledger.json');target_rows=[];positions={a:x for a,(p,x) in d['problems'].items()}
    manifest=dict(case=case,replay=replay,input_sha256=hashlib.sha256((SOURCE/'inputs'/f'{case}.json').read_bytes()).hexdigest(),source_root=str(SOURCE),ranking=ranking,position_policy='actual ALGO06 saved endpoint for each c arm; no evaluation truth',positions=positions,models=MODELS,scope='per-track offsets/rates are diagnostic lower bounds, not shared calibration or acceptance',noise_hz=150,offset_prior_hz=300,phase_prior_s=5,phase_bounds_s=[-30,30],exact_phase_step_s=.1,coarse_native_points=20,candidate_policy='sum of matched-arm coarse costs: top3 per model plus incumbent, same exact candidates and budgets for both arms',independent_evidence='family transfer required; single-curve fits cannot establish identity',script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write(out/'run_manifest.json',manifest)
    for k,m in enumerate(meta):
        tr=d['scan'].tracks[m['track_index']];ix=m['indices'];t=np.asarray(tr['times'])[ix];raw=np.asarray(tr['values'])[ix];ys={};phases={}
        for a,(p,x) in d['problems'].items():
            state=p.state(x);cal=d['scan'].hardware(tr,state['beta'])+tr['rf_hz']/11.5e9*d['scan'].rx_basis[m['track_index']]@state['smooth'][tr['receiver']-1]
            ys[a]=(tr['values']-cal)[ix];n=m['assigned_norad'];phases[a]=float(state['phases'][list(d['scan'].norads).index(n)]) if n in d['scan'].norads else 0.
        target_rows.append(dict(index=k,meta=m,key=tr['key'],receiver=tr['receiver'],channel=tr['channel'],rf_hz=tr['rf_hz'],times_s=t,raw_unwrapped_hz=raw,corrected_hz=ys,observation_ids=[tr['observation_ids'][j] for j in ix],pieces=tr['pieces'],polynomial=legacy.polynomial(t,raw),phase0=phases,results=[]))
    for regime in ('causal','later'):
        nums,bank,failed=legacy.bank_for(ledger[regime],z['scan_receipt']['origin_utc_ns']);coverage=[]
        for target in target_rows:
            rows,cov=fit_matched(np.array(target['times_s']),target['corrected_hz'],target['rf_hz']/11.5e9,nums,bank,positions,target['meta']['assigned_norad'],target['phase0'])
            target['results'] += [dict(r,regime=regime) for r in rows];coverage.append(dict(target=target['index'],models=cov))
            write(out/f"target-{target['index']}.json",target);write(out/'targets.json',target_rows)
            print(case,regime,target['index'],'done',round(time.monotonic()-began,1),flush=True)
        write(out/f'{regime}-search-coverage.json',dict(catalogue_count=len(nums),failed_propagation=failed,targets=coverage,all_eligible_received_coarse=True))
        del bank
    inventory=[]
    for regime in ('causal','later'):
        for n,r in ledger[regime].items():inventory.append(dict(norad=n,regime=regime,epoch_utc_ns=r['element_epoch_utc_ns'],collection_utc_ns=r['collected_utc_ns'],sha256=hashlib.sha256(('\n'.join(r['lines'])+'\n').encode()).hexdigest(),paired=str(n) in ledger['causal'] and str(n) in ledger['later']))
    with (out/'tle_inventory.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=inventory[0]);w.writeheader();w.writerows(inventory)
    manifest.update(status='complete',seconds=time.monotonic()-began);write(out/'run_manifest.json',manifest)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case',nargs='?',choices=CASES);ap.add_argument('--archive',action='store_true');args=ap.parse_args()
    if args.archive:archive([args.case] if args.case else CASES)
    else:run(args.case)
