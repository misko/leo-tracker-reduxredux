"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import hashlib
from pathlib import Path
import numpy as np
from . import experiment as ex
from . import previous
from algo06_science.common import read, write, reconstruct, ARMS
from .diagnose import build, derivatives, objective, refit
from .track import bank_for
from .predictive import fit_predict
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from prototype_dsx01_continuous_position import latlon

CATALOGUES=Path('.')
SEED=20261103


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def masks(times,groups,unique=False):
    blocks=np.floor(times/5).astype(int);available=np.unique(blocks);rng=np.random.default_rng(SEED);result=[]
    seen=set()
    for fold in range(5):
        for retry in range(2000):
            held=np.sort(rng.choice(available,max(1,round(.2*len(available))),replace=False))
            if unique and tuple(held) in seen:continue
            test=np.isin(blocks,held);train=~np.isin(blocks,np.r_[held-1,held,held+1])
            if all(sum(train&(groups==g))>=5 and sum(test&(groups==g))>=2 for g in np.unique(groups)):break
        else:return []
        seen.add(tuple(held))
        result.append(dict(fold=fold,train=train,test=test,held_blocks=held,retries=retry))
    return result

def causal_records(case,z):
    ledger=read(CATALOGUES/(case+'.json'))['elements'];cutoff=z['scan_receipt']['cutoff_utc_ns']
    for r in ledger.values():
        age=(cutoff-r['element_epoch_utc_ns'])/3.6e12
        if not (0<=age<=72 and r['collected_utc_ns']<=cutoff):raise ValueError('noncausal or too old catalogue')
    return ledger

def screen(d,z,n,nums,bank,out):
    base=d['problems']['fitted_c'][0]
    tracks=[(i,base.keep[s]) for r,i,s in zip(base.rows,base.members,base.slices) if r['candidate_norad']==n and base.keep[s].any()]
    ts=np.concatenate([d['scan'].tracks[i]['times'][use] for i,use in tracks])
    q=np.concatenate([np.full(sum(use),d['scan'].tracks[i]['rf_hz']/11.5e9) for i,use in tracks])
    groups=np.concatenate([np.full(sum(use),k) for k,(i,use) in enumerate(tracks)])
    parts=masks(ts,groups); pp=np.linspace(-30,30,151);cavity={};values={};nominees={n};coarse=[]
    longest=sorted(range(len(tracks)),key=lambda k:-sum(tracks[k][1]))[:2]
    for a in ARMS:
        cav=refit(d,z,a,d['problems']['fitted_c'][1],omit=n,rounds=15);cavity[a]=cav
        p,_=build(d,z,a,np.array(cav['reference']),omit=n);x=np.array(cav['x']);state=p.state(x)
        values[a]=np.concatenate([(tr['values']-p.scan.hardware(tr,state['beta'])-tr['rf_hz']/11.5e9*p.scan.rx_basis[i]@state['smooth'][tr['receiver']-1])[use] for i,use in tracks for tr in [p.scan.tracks[i]]])
        for k in longest:
            ii=np.flatnonzero(groups==k);ii=ii[np.unique(np.linspace(0,len(ii)-1,min(16,len(ii))).astype(int))]
            best=np.full(len(nums),np.inf)
            for phi in np.arange(-30,31,2):
                f,e=phase_frequency_grid(bank,ts[ii],*latlon(x),phase_seconds=phi)
                cost=profile_rate(values[a][ii],f*q[ii],ts[ii],rate_sigma_hz_s=.5,bias_sigma_hz=300)['cost']+(phi/5)**2
                best=np.minimum(best,np.where(e.min(axis=1)>=0,cost,np.inf))
            finalists=[int(j) for j in np.argsort(best)[:2] if np.isfinite(best[j])];nominees.update(int(nums[j]) for j in finalists)
            coarse.append(dict(arm=a,track=d['scan'].tracks[tracks[k][0]]['key'],nominees=[dict(norad=int(nums[j]),score=float(best[j])) for j in finalists]))
    raw={};whole={};folds=[]
    for a in ARMS:
        raw[a]={};whole[a]={}
        for v in sorted(nominees):
            j=int(np.flatnonzero(nums==v)[0]);bb=dict(time_s=bank['time_s'],position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
            f,e=paired_phase_frequency(bb,np.tile(ts,len(pp)),np.repeat(np.arange(len(pp)),len(ts)),pp,*latlon(np.array(cavity[a]['x'])))
            # All shortlisted family hypotheses must be visible over every source
            # at every phase in this reduced predictive check; conservative scope.
            if np.min(e)<0:continue
            raw[a][v]=values[a][None,:]-f.reshape(len(pp),-1)*q
            whole[a][v]=fit_predict(raw[a][v],ts,q,groups,np.ones(len(ts),bool),np.ones(len(ts),bool),pp)
    common=sorted(set(raw['c0'])&set(raw['fitted_c']))
    if n not in common:return dict(status='incumbent_not_visible_over_complete_phase_grid',cavity=cavity,coarse=coarse,nominees=common)
    for part in parts:
        for a in ARMS:
            fitted={v:fit_predict(raw[a][v],ts,q,groups,part['train'],part['test'],pp) for v in common}
            folds.append(dict(arm=a,fold=part['fold'],fits=fitted))
    ranked=sorted([v for v in common if v!=n],key=lambda v:sum(whole[a][v]['training_score'] for a in ARMS))[:2]
    proposals=[]
    def predictive_ok(v):
        results={}
        for a in ARMS:
            gains=[r['fits'][n]['predictive_score']-r['fits'][v]['predictive_score'] for r in folds if r['arm']==a]
            results[a]=dict(gains=gains,mean=float(np.mean(gains)) if gains else None,wins=sum(g>0 for g in gains),pass_check=len(gains)==5 and np.mean(gains)>0 and sum(g>0 for g in gains)>=4)
        return results
    keys=[d['scan'].tracks[i]['key'] for i,u in tracks]
    for v in ranked:
        proposals.append(dict(name=f'{n}_to_{v}',norad=v,mapping=dict.fromkeys(keys,v),aliases={key:whole['fitted_c'][v]['alias_by_group'][k] for k,key in enumerate(keys)},
            phases={str(v):whole['fitted_c'][v]['phase_map_s']},allowed_families=[n,v],predictive=predictive_ok(v),penalty=float(2*np.log(max(2,len(common))))))
    # Partial partition proposal keeps unstable whole tracks on their incumbent.
    mapping={};stability=[]
    for k,key in enumerate(keys):
        winners=[min(common,key=lambda v:r['fits'][v]['training_track_cost'][k]) for r in folds]
        counts={v:winners.count(v) for v in common};win=max(common,key=lambda v:counts[v])
        stable=bool(len(winners)==10 and all(sum(min(common,key=lambda v:r['fits'][v]['training_track_cost'][k])==win for r in folds if r['arm']==a)>=4 for a in ARMS))
        mapping[key]=win if stable else n;stability.append(dict(component=key,counts=counts,stable=stable,label=mapping[key]))
    if len(set(mapping.values()))>1:
        predictive={};phases={};aliases={};partition_results=[]
        for a in ARMS:
            gains=[]
            for part in parts:
                score=0.
                for v in set(mapping.values()):
                    mask=np.isin(groups,[k for k,key in enumerate(keys) if mapping[key]==v])
                    r=fit_predict(raw[a][v][:,mask],ts[mask],q[mask],groups[mask],part['train'][mask],part['test'][mask],pp);score+=r['predictive_score']
                original=next(r for r in folds if r['arm']==a and r['fold']==part['fold'])['fits'][n]['predictive_score'];gains.append(original-score)
            predictive[a]=dict(gains=gains,mean=float(np.mean(gains)) if gains else None,wins=sum(g>0 for g in gains),pass_check=len(gains)==5 and np.mean(gains)>0 and sum(g>0 for g in gains)>=4)
        for v in set(mapping.values()):
            mask=np.isin(groups,[k for k,key in enumerate(keys) if mapping[key]==v]);r=fit_predict(raw['fitted_c'][v][:,mask],ts[mask],q[mask],groups[mask],np.ones(sum(mask),bool),np.ones(sum(mask),bool),pp)
            phases[str(v)]=r['phase_map_s'];aliases.update({keys[k]:alias for k,alias in r['alias_by_group'].items()})
        proposals.append(dict(name=f'{n}_stable_partition',norad=n,mapping=mapping,aliases=aliases,phases=phases,allowed_families=sorted(set(mapping.values())|{n}),predictive=predictive,
            penalty=float(2*np.log(max(2,len(common)))+2*(len(set(mapping.values()))-1)*np.log(len(ts))),
            prediction_limit='mapping selected across these same folds; development diagnostic, cannot meet independent predictive acceptance'))
    result=dict(status='screened',cavity=cavity,coarse=coarse,nominees=common,whole=whole,folds=folds,partitions=parts,proposals=proposals,stability=stability,
        points=len(ts),tracks=keys,scope='conditional prediction with family-omitted position/calibration; discovery uses full family data')
    write(out/'screen.json',result);return result
