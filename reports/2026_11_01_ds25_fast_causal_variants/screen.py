"""Whole-cohort, training-only shortlist nomination for causal recovery variants.

The search model integrates a shared offset, rate and orbital phase. It is a
candidate screen, not the production orbital-uncertainty likelihood. Native
target points never calibrate the frozen incumbent receiver model.
"""
import sys,time,traceback,copy,argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import subprocess,os
import numpy as np
from sgp4.api import Satrec
from common import *
sys.path.insert(0,str(ROOT.parent/'2026_10_31_causal72_age_prior'))
from evidence import components,marginal,age_penalty
from run import split
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
SEEDS=(20261031,94721,4081)

def preflight(case):
    began=time.monotonic();z=read(ROOT/'inputs'/(case+'.json'));d=reconstruct(z)
    targets=[]
    for r in z['targets']:
        tr=d['scan'].tracks[r['track_index']];ix=np.asarray(r['source_local_indices'])
        if [tr['observation_ids'][k] for k in ix]!=r['observation_ids']:raise ValueError('Native source index mismatch')
        y={}
        for arm,(p,x) in d['problems'].items():
            state=p.state(x)
            whole=tr['values']-d['scan'].hardware(tr,state['beta'])-tr['rf_hz']/11.5e9*d['scan'].rx_basis[r['track_index']]@state['smooth'][tr['receiver']-1]
            y[arm]=whole[ix]
        targets.append(dict(source=r,times_s=tr['times'][ix],values_hz=tr['values'][ix],corrected_hz=y))
    write(ROOT/'preflight'/(case+'.json'),dict(case=case,checks=d['replay_checks'],targets=targets,
        positions={a:x for a,(_,x) in d['problems'].items()},scan_receipt=d['scan'].receipt,
        bank_domain_s=[float(min(d['scan'].sky['time_s'])),float(max(d['scan'].sky['time_s']))],
        seconds=time.monotonic()-began))
    print(case,'replayed',len(targets),flush=True)

def top_indices(cost,age,limit,penalty=False):
    values=np.where(age<=limit,cost,np.inf)
    if penalty:values=values+2*np.log(2)*np.maximum(0,age-48)/24
    return [int(k) for k in np.argsort(values)[:3] if np.isfinite(values[k])]

def one(case):
    began=time.monotonic();packet=read(ROOT/'preflight'/(case+'.json'))
    records=read(ROOT/'catalogues'/(case+'.json'))['elements'];meta=packet['scan_receipt']
    nums=np.array(sorted(map(int,records)));age=np.array([(meta['cutoff_utc_ns']-records[str(n)]['element_epoch_utc_ns'])/3.6e12 for n in nums])
    collection=np.array([(meta['cutoff_utc_ns']-records[str(n)]['collected_utc_ns'])/3.6e12 for n in nums])
    if not ((age>=0)&(age<=72)&(collection>=0)&(collection<=72)).all():raise ValueError('Causal catalogue violation')
    epoch=age.copy();age=np.maximum(age,collection)
    grid=np.arange(-40.,341.);cat=ElementSetCatalogue(tuple(map(str,nums)),tuple(map(int,nums)),tuple(Satrec.twoline2rv(*records[str(n)]['lines']) for n in nums))
    pos,vel,good=ecef_states(cat,meta['origin_utc_ns'],grid)
    failures=nums[~good].tolist();nums=nums[good];age=age[good];epoch=epoch[good];collection=collection[good]
    bank=dict(time_s=grid,position_km=pos[good],velocity_km_s=vel[good]);outputs=[]
    phases=np.sort(np.unique(np.r_[np.arange(-30,31,2),-15,15]))
    for target in packet['targets']:
        source=target['source'];t=np.asarray(target['times_s']);q=source['rf_hz']/11.5e9
        folds=[('full',np.ones(len(t),bool),np.zeros(len(t),bool))]
        for seed in SEEDS:
            train,held,groups=split(t,seed)
            if train.sum()>=8 and held.sum()>=4:folds.append((str(seed),train,held))
        # Coarse nomination is repeated on training points separately. The
        # target's full-data winner is never injected into a training shortlist.
        offers={};finalists=set()
        for arm in ARMS:
            y=np.asarray(target['corrected_hz'][arm]);x=packet['positions'][arm]
            best={(bound,name):np.full(len(nums),np.inf) for bound in (15,30) for name,_,_ in folds}
            for phi in phases:
                f,e=phase_frequency_grid(bank,t,*latlon(x),phase_seconds=phi);f*=q
                for name,mask,held in folds:
                    # Uniform thinning solely for nomination, identical per policy.
                    ix=np.flatnonzero(mask);ix=ix[np.unique(np.linspace(0,len(ix)-1,min(16,len(ix))).astype(int))]
                    cost=profile_rate(y[ix],f[:,ix],t[ix],rate_sigma_hz_s=.5,bias_sigma_hz=300)['cost']+(phi/5)**2
                    cost=np.where(e[:,ix].min(axis=1)>=0,cost,np.inf)
                    for bound in (15,30):
                        if abs(phi)<=bound:best[bound,name]=np.minimum(best[bound,name],cost)
            for policy,(limit,bound,penalty) in POLICIES.items():
                for name,_,_ in folds:
                    ks=top_indices(best[bound,name],age,limit,penalty)
                    offers[policy,arm,name]=set(int(nums[k]) for k in ks);finalists.update(offers[policy,arm,name])
        # Match candidate sets across c arms, but never across training folds.
        for policy in POLICIES:
            for name,_,_ in folds:
                union=offers[policy,'c0',name]|offers[policy,'fitted_c',name]
                for arm in ARMS:offers[policy,arm,name]=union
        rows=[]
        for n in sorted(finalists):
            j=int(np.flatnonzero(nums==n)[0])
            for bound in (15,30):
                pp=np.linspace(-bound,bound,int(2*bound/.1)+1)
                bb=dict(time_s=grid,position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),
                    velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
                for arm in ARMS:
                    relevant=[(policy,penalty) for policy,(limit,b,penalty) in POLICIES.items() if b==bound and age[j]<=limit]
                    if not relevant:continue
                    f,e=paired_phase_frequency(bb,np.tile(t,len(pp)),np.repeat(np.arange(len(pp)),len(t)),pp,*latlon(packet['positions'][arm]))
                    f=f.reshape(len(pp),-1)*q;e=e.reshape(len(pp),-1)
                    y=np.asarray(target['corrected_hz'][arm])
                    for name,train,held in folds:
                        policies=[(policy,penalty) for policy,penalty in relevant if n in offers[policy,arm,name]]
                        if not policies:continue
                        comp=components(y,f,e[:,train].min(axis=1)>=0,t,np.arange(-4,5),PERIOD,mask=train)
                        m=marginal(comp,pp,5.)
                        if not np.isfinite(m['score']):continue
                        noise=batch_noise_screen(m['residual'][None],t)
                        row=dict(arm=arm,fold=name,norad=n,phase_limit_s=bound,age_h=float(epoch[j]),collection_age_h=float(collection[j]),
                            score=m['score'],phase_s=m['phase_s'],alias=int(m['alias_index']-4),
                            rms_hz=m['rms_hz'],bias_hz=float(m['beta'][0]),rate_hz_s=float(m['beta'][1]),
                            phase_boundary_mass=m['phase_boundary_mass'],noise={k:v[0].item() for k,v in noise.items()},
                            held_rms_hz=float(np.sqrt(np.mean(m['residual'][held]**2))) if held.any() else None,
                            held_visible=bool(e[m['phase_index'],held].min()>=0) if held.any() else True)
                        for policy,penalty in policies:rows.append(dict(row,policy=policy,score=row['score']+(age_penalty(epoch[j]) if penalty else 0.)))
        summaries=[]
        for policy in POLICIES:
            pair={}
            for arm in ARMS:
                ff={}
                for name,train,held in folds:
                    rr=sorted([r for r in rows if r['policy']==policy and r['arm']==arm and r['fold']==name],key=lambda r:r['score'])
                    if rr:ff[name]=dict(winner=rr[0],runner_up=rr[1] if len(rr)>1 else None,
                                       margin=rr[1]['score']-rr[0]['score'] if len(rr)>1 else 0.)
                qualified=len(ff)==4 and all(v['margin']>=10 for v in ff.values()) and len({v['winner']['norad'] for v in ff.values()})==1
                if qualified:
                    w=ff['full']['winner'];qualified=(w['noise']['noise_screen_pass'] and w['rms_hz']<=450 and abs(w['bias_hz'])<=3000 and abs(w['rate_hz_s'])<=2 and w['phase_boundary_mass']<.01 and
                        all(v['winner']['held_rms_hz']<=450 and v['winner']['held_visible'] for k,v in ff.items() if k!='full'))
                pair[arm]=dict(folds=ff,qualified=bool(qualified))
            accepted=all(pair[a]['qualified'] for a in ARMS)
            if accepted:accepted=len({pair[a]['folds']['full']['winner']['norad'] for a in ARMS})==1 and len({pair[a]['folds']['full']['winner']['alias'] for a in ARMS})==1
            summaries.append(dict(policy=policy,arms=pair,screen_pass=bool(accepted)))
        outputs.append(dict(source=source,rows=rows,summaries=summaries,finalists=sorted(finalists),
            folds=[dict(name=name,train_indices=np.flatnonzero(train),held_indices=np.flatnonzero(held)) for name,train,held in folds]))
        write(ROOT/'screen'/case/(source['fragment_id']+'.json'),outputs[-1])
        print(case,source['fragment_id'],'screen',len(finalists),[s['policy'] for s in summaries if s['screen_pass']],flush=True)
    write(ROOT/'screen'/case/'result.json',dict(case=case,targets=outputs,catalogue_count=len(nums),
          eligible48=int((age<=48).sum()),propagation_failures=failures,seconds=time.monotonic()-began))

def batch(stage,workers,reverse=False):
    roster=read(ROOT/'protocol.json')['cohort'];suffix='-reverse' if reverse else '';out=ROOT/(stage+suffix+'-execution.json');results=[]
    if reverse:roster=roster[::-1]
    def work(z):
        case=z['case'];log=ROOT/'logs'/(stage+suffix+'-'+case+'.log');log.parent.mkdir(exist_ok=True)
        result=ROOT/'preflight'/(case+'.json') if stage=='preflight' else ROOT/'screen'/case/'result.json'
        if result.exists():return dict(case=case,status='cached')
        with log.open('w') as f:
            try:
                r=subprocess.run([sys.executable,__file__,stage,'--case',case],stdout=f,stderr=subprocess.STDOUT,timeout=900,
                                 env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
                return dict(case=case,status='complete' if r.returncode==0 else 'failed',returncode=r.returncode,log=str(log))
            except subprocess.TimeoutExpired:return dict(case=case,status='timeout',log=str(log))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(work,z) for z in roster]):
            r=future.result();results.append(r);write(out,results);print(stage,len(results),r['case'],r['status'],flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['preflight','screen']);a.add_argument('--case');a.add_argument('--workers',type=int,default=16);a.add_argument('--reverse',action='store_true');args=a.parse_args()
    if args.case:
        if args.stage=='screen':
            import fcntl
            path=ROOT/'locks';path.mkdir(exist_ok=True)
            with (path/(args.case+'.lock')).open('w') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX)
                if not (ROOT/'screen'/args.case/'result.json').exists():one(args.case)
        else:preflight(args.case)
    else:batch(args.stage,args.workers,args.reverse)
