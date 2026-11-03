"""Conditional identity audit of N12 62866/62868 against the archived sky bank.

Known roof and saved full-model roof RX/RF nuisance are fixed. Every candidate
gets one absolute orbit-time shift within +/-20 s; no offset/line/quadratic can
be fitted per track. Rank using a reproducible stratified random training split,
then evaluate untouched test windows. Calibration and the original memberships
were learned using this scan: this is NOT independent end-to-end validation.
Both RF variants use identical windows, bank, split and timing-search procedure.
"""
import copy
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from leave_one_satellite_out import load,digest,OUT as OLD
from subset_positions import enable_research_model
enable_research_model()
from prediction_jacobian import paired_prediction_jacobian
from track_diagnostics import residual_statistics

HERE=Path(__file__).resolve().parent
OUT=HERE/'N12-62866-62868-identity-audit'
BANK=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2/N12/seed-timing-v6/orbit-bank')
POSITIONS=OLD.with_name(OLD.name+'-4km')/'N12'
TARGETS=(62866,62868)
ARMS=('fitted-c','zero-c')
GRID=np.linspace(-20.,20.,81)
ALIAS=2500000./11.


def circular(value):return (np.asarray(value)+ALIAS/2)%ALIAS-ALIAS/2


def split_windows(receiver,channel,seed):
    rng=np.random.default_rng(seed);train=np.zeros(len(receiver),bool)
    strata=np.asarray(receiver)*10+np.asarray(channel)
    for k in np.unique(strata):
        ix=rng.permutation(np.flatnonzero(strata==k))
        count=max(1,min(len(ix)-1,int(np.floor(.7*len(ix))))) if len(ix)>1 else 1
        train[ix[:count]]=True
    assert train.any() and (~train).any()
    return train


def predict(data,index,timing,parameters):
    p=parameters.copy();p[6+index]=timing
    pred,visible,jac=paired_prediction_jacobian(data,p,np.arange(len(data.times)),np.full(len(data.times),index))
    return pred,visible


def fit_candidate(data,index,observed,train,parameters,coarse,visibility):
    loss=np.mean(circular(observed[None,train]-coarse[:,train,index])**2,axis=1)
    visible=np.all(visibility[:,train,index],axis=1)
    loss=np.where(visible,loss,np.inf)
    if not np.any(visible):return None
    minima=[i for i in range(len(GRID)) if np.isfinite(loss[i]) and
            (i==0 or loss[i]<=loss[i-1]) and (i==len(GRID)-1 or loss[i]<=loss[i+1])]
    starts=sorted(minima,key=lambda i:loss[i])[:3]
    def score(t):
        pred,vis=predict(data,index,t,parameters)
        return float(np.mean(circular(observed[train]-pred[train])**2)+1e12*np.mean(~vis[train]))
    candidates=[]
    for i in starts:
        lo=max(-20.,GRID[i]-.5);hi=min(20.,GRID[i]+.5)
        fit=minimize_scalar(score,bounds=(lo,hi),method='bounded',options=dict(xatol=1e-7,maxiter=60))
        candidates.extend([(score(fit.x),float(fit.x)),(score(GRID[i]),float(GRID[i]))])
    value,timing=min(candidates)
    pred,vis=predict(data,index,timing,parameters);error=circular(observed-pred)
    return dict(satellite=int(data.numbers[index]),timing_s=timing,at_timing_bound=abs(timing)>19.999,
                train_rms_hz=float(np.sqrt(np.mean(error[train]**2))),test_rms_hz=float(np.sqrt(np.mean(error[~train]**2))),
                all_rms_hz=float(np.sqrt(np.mean(error**2))),train_visible_fraction=float(np.mean(vis[train])),
                test_visible_fraction=float(np.mean(vis[~train])),within_200=int(sum(vis&(abs(error)<=200))),
                within_600=int(sum(vis&(abs(error)<=600))),test_within_600=int(sum(vis[~train]&(abs(error[~train])<=600))))


def write_csv(name,rows):
    with (OUT/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main(leave_track_out=False):
    global OUT
    if leave_track_out:OUT=OUT/'leave-track-out-calibration'
    OUT.mkdir(exist_ok=True)
    full,meta,_=load('N12');baseline=json.loads((POSITIONS/'baseline.json').read_text())
    receipt=json.loads((BANK/'receipt.json').read_text());assert digest(BANK/'states.npz')==receipt['arrays_sha256']
    with np.load(BANK/'states.npz') as z:
        bank={k:z[k].copy() for k in z.files}
    summary={};allrows=[];rxrows=[];plotdata={};calibration_sources={}
    for target in TARGETS:
        calpath=POSITIONS/f'drop-{target}.json' if leave_track_out else POSITIONS/'baseline.json'
        calibration=json.loads(calpath.read_text());calibration_sources[str(calpath)]=digest(calpath)
        mask=full.owners==target;data=copy.copy(full)
        for k in ('times','measured','receiver','channel','rf','group','margin','original_rows','owners','fixed_receiver_hz'):
            setattr(data,k,getattr(full,k)[mask].copy())
        data.numbers=bank['numbers'];data.nodes=bank['nodes_s'];data.position=bank['position_km'];data.velocity=bank['velocity_km_s']
        for j,n in enumerate(full.numbers):
            bj=int(np.flatnonzero(data.numbers==n)[0])
            assert np.array_equal(full.position[j],data.position[bj])
        parameters=np.zeros(6+len(data.numbers));parameters[:2]=baseline['arms']['fitted-c']['roof']['parameters'][:2]
        train=split_windows(data.receiver,data.channel,20261005+target)
        n=len(data.times);s=len(data.numbers);rows=np.repeat(np.arange(n),s);ids=np.tile(np.arange(s),n)
        coarse=np.empty((len(GRID),n,s));visibility=np.empty(coarse.shape,bool)
        for j,t in enumerate(GRID):
            trial=parameters.copy();trial[6:]=t
            pred,vis,_=paired_prediction_jacobian(data,trial,rows,ids)
            coarse[j]=pred.reshape(n,s);visibility[j]=vis.reshape(n,s)
        summary[target]=dict(windows=n,train_windows=int(sum(train)),test_windows=int(sum(~train)),
                             train_original_rows=data.original_rows[train].tolist(),test_original_rows=data.original_rows[~train].tolist(),arms={})
        for arm in ARMS:
            roof=calibration['arms'][arm]['roof'];p=np.array(roof['parameters'])
            correction=p[2+2*data.receiver]+p[3+2*data.receiver]*(data.times-150.)+roof['coefficient']*(data.rf-meta['rf_center_hz'])/1e9
            observed=data.measured-correction
            ranked=[]
            for index in range(s):
                candidate=fit_candidate(data,index,observed,train,parameters,coarse,visibility)
                if candidate is not None:ranked.append(candidate)
            ranked.sort(key=lambda d:d['train_rms_hz'])
            for rank,r in enumerate(ranked,1):
                r.update(target=target,arm=arm,training_rank=rank)
                allrows.append(r)
            incumbent=next(r for r in ranked if r['satellite']==target)
            shortlisted=ranked[:8]
            summary[target]['arms'][arm]=dict(incumbent=incumbent,top_eight=shortlisted,
                                             bank_count=s,fully_visible_training_candidates=len(ranked))
            ix=int(np.flatnonzero(data.numbers==target)[0]);pred,_=predict(data,ix,incumbent['timing_s'],parameters)
            err=circular(observed-pred)
            perrx={}
            for rx in (0,1):
                select=data.receiver==rx
                if min(sum(select),sum(~select))<3:continue
                r=fit_candidate(data,ix,observed,select,parameters,coarse,visibility)
                r.update(fit_receiver=rx,predict_receiver=1-rx)
                rxrows.append(dict(target=target,arm=arm,**r));perrx[rx]=r
            stats=residual_statistics(data.times,err,data.receiver*10+data.channel)
            summary[target]['arms'][arm].update(per_receiver_fit=perrx,refitted_residual_statistics=stats)
            plotdata[(target,arm)]=dict(times=data.times,receiver=data.receiver,channel=data.channel,train=train,error=err)
            print(target,arm,'incumbent',incumbent,'best alternatives',ranked[:3],flush=True)
    write_csv('all-candidate-rankings.csv',allrows);write_csv('cross-receiver-timing.csv',rxrows)
    result=dict(scope=__doc__,scan='N12',targets=summary,alias_hz=ALIAS,timing_bound_s=20.,coarse_step_s=.5,
                timing_objective='Training squared circular residual, no timing prior; up to three grid-local minima continuously refined; no row clipping.',
                candidate_bank=receipt,bank_sha256=digest(BANK/'states.npz'),input_sha256=meta['input_sha256'],
                baseline_sha256=digest(POSITIONS/'baseline.json'),implementation_sha256=digest(Path(__file__)),
                extra_roof_nuisance_excludes_target_windows=leave_track_out,calibration_sources=calibration_sources)
    (OUT/'identity-audit.json').write_text(json.dumps(result,indent=2));render(summary,plotdata)


def render(summary,plotdata):
    fig,axes=plt.subplots(2,2,figsize=(14,9))
    for i,target in enumerate(TARGETS):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j];d=plotdata[(target,arm)];r=summary[target]['arms'][arm]['incumbent']
            for rx,color,marker in [(0,'#0072B2','o'),(1,'#D55E00','^')]:
                m=d['receiver']==rx
                ax.scatter(d['times'][m],d['error'][m],color=color,marker=marker,s=26,label=f'RX{rx}')
                test=m&~d['train'];ax.scatter(d['times'][test],d['error'][test],s=65,facecolors='none',edgecolors='black',lw=.8)
            ax.axhline(0,color='.4',lw=.8);ax.grid(alpha=.2)
            ax.set_title(f'N12 · {target} · {arm}\nTraining rank {r["training_rank"]}; test RMS {r["test_rms_hz"]:.1f} Hz; timing {r["timing_s"]:+.3f} s')
            ax.set_xlabel('Receive time (s)');ax.set_ylabel('GLRT − candidate prediction (Hz)');ax.legend()
    fig.suptitle('Identity check: current satellites, timing fitted only on random training windows',fontsize=16)
    fig.text(.5,.018,'Black rings: held-out windows. Known roof and saved RX/RF calibration fixed; one timing parameter per candidate, within ±20 s.\nAll 824 archived near-visible candidates searched. Frozen memberships and calibration use this scan: conditional identity evidence, not independent validation.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.065,1,.95));fig.savefig(OUT/'incumbent-residuals.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(14,9))
    for i,target in enumerate(TARGETS):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j];rs=summary[target]['arms'][arm]['top_eight']
            x=np.arange(len(rs));ax.bar(x-.18,[r['train_rms_hz'] for r in rs],width=.35,color='#0072B2',label='Training RMS')
            ax.bar(x+.18,[r['test_rms_hz'] for r in rs],width=.35,color='#D55E00',label='Held-out RMS')
            ax.set_yscale('log');ax.set_xticks(x,[str(r['satellite']) for r in rs],rotation=45)
            ax.set_ylabel('Circular residual RMS (Hz, log scale)');ax.set_title(f'Windows assigned to {target} · {arm}')
            ax.grid(axis='y',alpha=.2);ax.legend(fontsize=9)
    fig.suptitle('Eight best candidate identities, ranked using training windows only',fontsize=16)
    fig.text(.5,.018,'Same observations, same calibration, same ±20 s timing freedom for every candidate. No per-satellite frequency offset or drift fitted.\nTest windows do not set timing or ranking; calibration and original track selection were not independently held out.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.065,1,.95));fig.savefig(OUT/'alternative-identities.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--leave-track-out-calibration',action='store_true')
    main(parser.parse_args().leave_track_out_calibration)
