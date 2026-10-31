"""Bounded native metadata and conditional residual-mechanism diagnostics."""
import json
import signal
import time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from diagnose_all_large_tracks import context
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

OUT=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/ds26-longest-residual-20261030/orbit-diagnostics-v3')
VALID=Path('/srv/bulk/leo/research/ds26-recovery-validation-20261031')


def read(p):return json.loads(Path(p).read_text())
def encode(z):
    if isinstance(z,np.ndarray):return z.tolist()
    if isinstance(z,np.generic):return z.item()
    raise TypeError(type(z).__name__)


def train_feature(y,feature,train,held):
    """Fixed 150 Hz coefficient/noise priors; preprocessing uses training only."""
    y=np.asarray(y);v=np.asarray(feature,float)
    mean=float(v[train].mean());sd=max(float(v[train].std()),1e-12)
    z=(v-mean)/sd;h=np.column_stack((np.ones(len(z)),z))
    # 300 Hz intercept and 150 Hz feature coefficient, 150 Hz fixed noise.
    a=h[train]/150;precision=np.diag([1/300**2,1/150**2])+a.T@a
    coef=np.linalg.solve(precision,a.T@(y[train]/150))
    base=float(y[train].sum()/(train.sum()+150**2/300**2))
    return dict(before_held_rms_hz=float(np.sqrt(np.mean((y[held]-base)**2))),
        after_held_rms_hz=float(np.sqrt(np.mean((y[held]-h[held]@coef)**2))),
        coefficient_hz=coef,training_feature_mean=mean,training_feature_sd=sd)


def run():
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s audit cap')));signal.alarm(240)
    result=dict(scope='Conditional residual diagnosis; inherited geometry and graph; no acceptance or causal attribution',
        GPS_used=False,new_RF=False,future_TLE=False,maximum_seconds=240,cases=[])
    old_witness=read(OLD/'witnesses-unique.json')
    for case in ('DS26-0265','DS26-0223'):
        diag=read(next(OLD.glob('*'+case+'/result.json')));row=diag['row'];tracks=read(row['tracks_path']);track=tracks[row['track_index']]
        obs={o['observation_id']:o for o in read(row['observations_path'])};native=[obs[oid] for oid in row['residual_observation_ids']]
        tracking=read(row['tracking_path']);probes=tracking['source']['probes'];sr=tracking['source']['sample_rate_hz'];anchor=tracking['clock_anchor']['sample_counter']
        lookup={}
        for probe in probes:
            if probe['receiver_id']!=0 or probe['channel']!=row['channel']:continue
            for candidate in probe['candidates']:
                key=round(candidate['fractional_tracking_cfo_hz'],6)
                lookup.setdefault(key,[]).append((probe,candidate))
        metadata=[]
        for o in native:
            matches=[(p,c) for p,c in lookup.get(round(o['measured_cfo_hz'],6),[]) if abs(c['fractional_margin']-o['fractional_margin'])<1e-10]
            p,c=min(matches,key=lambda z:z[1]['candidate_rank'])
            metadata.append(dict(c,visit_index=p['visit_index'],valid_start_counter=p['valid_start_counter'],edge=p['edge'],
                window_center_error_s=o['time_s']-(p['valid_start_counter']-anchor)/sr-.01,
                deduplicated_matches=len(matches)))
        times=np.array([o['time_s'] for o in native]);native_cfo=np.array([o['measured_cfo_hz'] for o in native]);lift=np.asarray(track['values'])-native_cfo
        c=dict(case=case,component=row['component'],times_s=times,native_cfo_hz=native_cfo,metadata=metadata,
            graph_pieces=track['pieces'],alias_lift_hz=lift,alias_transitions=int((abs(np.diff(lift))>1e5).sum()),
            fractional_margin_range=[min(o['fractional_margin'] for o in native),max(o['fractional_margin'] for o in native)],
            candidate_ranks=sorted(set(z['candidate_rank'] for z in metadata)),
            source_edges=sorted(set(z['edge'] for z in metadata)),
            maximum_window_center_error_s=max(abs(z['window_center_error_s']) for z in metadata),arms={},
            prior_segment_winners=[dict(start_s=s['start_s'],points=s['points'],norad={arm:min(v,key=lambda q:q['cost'])['norad'] for arm,v in s['trials'].items()}) for s in diag['segments']])
        if case.endswith('0265'):
            source=read(VALID/'phase0265/shared-run01/reference30/inclusion/target_0.json')
            d=context(read(row['inventory_path']));witnesses={}
            for arm,(p,x) in d['problems'].items():
                calc=p.calculate(x);ws=[]
                for rr,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                    t=d['scan'].tracks[i];use=p.keep[sl]&(t['times']>=times.min())&(t['times']<=times.max())
                    if t['receiver']!=1 or use.sum()<8:continue
                    ws.append(dict(component=t['key'],norad=rr['candidate_norad'],receiver=t['receiver'],channel=t['channel'],times_s=t['times'][use],residual_hz=calc['conditional_residual_hz'][sl][use]))
                witnesses[arm]=ws
            residuals={arm:np.array(z['target_diagnostics'][0]['residual_hz']) for arm,z in source['arms'].items()}
            predicted={arm:np.array(z['target_diagnostics'][0]['predicted_CFO_hz']) for arm,z in source['arms'].items()}
            c['residual_model']='30s-reference full-inclusion trial, target physical orbit uncertainty, original receiver model'
        else:
            saved=read(VALID/'receiver/results-v3/DS26-0223.json');residuals={};predicted={};witnesses={}
            old=next(z for z in old_witness['records'] if z['case']==case)
            for arm in ('c0','fitted_c'):
                z=next(q for q in saved['rows'] if q['arm']==arm and q['role']=='addition' and q['model']=='joint')['evaluations'][0]
                residuals[arm]=np.array(z['corrected']['residual_hz']);predicted[arm]=np.asarray(track['values'])-residuals[arm]
                witnesses[arm]=old['arms'][arm]['witnesses']
            c['residual_model']='Saved joint receiver+satellite correction, addition endpoint; target excluded from correction training; inherited geometry'
        annotation=read(Path(row['terminal_path']).parent/'recovery'/row['track_id']/'annotation/result.json')
        join=track['pieces'][0].get('join_time_s')
        for arm,r in residuals.items():
            sigma=max(float(r.std(ddof=1)),75);cuts=np.arange(4,len(r)-3);cs=np.cumsum(r)
            jumps=cs[cuts-1]/cuts-(r.sum()-cs[cuts-1])/(len(r)-cuts)
            zz=abs(jumps)/(sigma*np.sqrt(1/cuts+1/(len(r)-cuts)));ix=int(zz.argmax());cut=int(cuts[ix])
            slope=np.gradient(predicted[arm],times)
            epoch=np.array([(z['integer_epoch_sample']+z['fractional_epoch_offset_samples'])/sr for z in metadata])
            timing=slope*(epoch-epoch.mean())
            rr=dict(residual_hz=r,noise={k:v[0] for k,v in batch_noise_screen(r[None,:],times).items()},
                largest_step=dict(before_s=float(times[cut-1]),after_s=float(times[cut]),z=float(zz[ix]),mean_jump_hz=float(jumps[ix])),
                metadata_correlations={key:float(np.corrcoef(r,[z[key] for z in metadata])[0,1]) for key in ('fractional_margin','fractional_epoch_offset_samples','integer_epoch_sample','candidate_rank') if np.std([z[key] for z in metadata])>0},
                variable_detected_epoch_timing_correction_rms_hz=float(np.sqrt(np.mean(timing**2))),
                matches=[],grouped_mechanisms=[])
            for fold in annotation['folds']:
                train,held=replay_split(times,fold['split'])
                if train.sum()<4 or held.sum()<4:continue
                features={'fractional_margin':np.array([z['fractional_margin'] for z in metadata]),
                    'fractional_epoch_offset':np.array([z['fractional_epoch_offset_samples'] for z in metadata])}
                if join is not None:features['fixed_graph_join_offset']=(times>=join).astype(float)
                rr['grouped_mechanisms'].append(dict(seed=fold['seed'],split=fold['split'],training_points=int(train.sum()),held_points=int(held.sum()),
                    models={name:train_feature(r,feat,train,held) for name,feat in features.items()}))
            for w in witnesses[arm]:
                wt=np.asarray(w['times_s']);wr=np.asarray(w['residual_hz']);dist=abs(wt[:,None]-times[None,:]);edges=np.argwhere(dist<=.5)
                edges=sorted((dist[i,j],int(i),int(j)) for i,j in edges);wi=set();ti=set();pairs=[]
                for dd,i,j in edges:
                    if i in wi or j in ti:continue
                    wi.add(i);ti.add(j);pairs.append((i,j))
                if len(pairs)<8:continue
                ii,jj=np.array(pairs).T
                rr['matches'].append(dict(component=w['component'],norad=w['norad'],receiver=w['receiver'],channel=w['channel'],
                    points=len(pairs),correlation=float(np.corrcoef(wr[ii],r[jj])[0,1]),times_s=wt,residual_hz=wr,
                    same_family=w['norad']==(66102 if case.endswith('0265') else 63595),
                    caveat='Witness inherited baseline/trial geometry; descriptive pair correlation, not causal attribution or independent residual gate calibration'))
            rr['matches'].sort(key=lambda w:-w['points']);c['arms'][arm]=rr
        result['cases'].append(c)
        print(case,'pieces',len(track['pieces']),'join',join,'aliases',c['alias_transitions'],'ranks',c['candidate_ranks'],'timingerror',c['maximum_window_center_error_s'],flush=True)
        render(c)
    result['seconds']=time.monotonic()-began;(OUT/'audit.json').write_text(json.dumps(result,default=encode,indent=2,allow_nan=False)+'\n')


def render(c):
    t=np.array(c['times_s']);fig,axs=plt.subplots(4,1,figsize=(13,12),sharex=True)
    axs[0].plot(t,c['native_cfo_hz'],'.',label='Native CFO, every target point');axs[0].set_ylabel('CFO (Hz)');axs[0].legend()
    for arm,r in c['arms'].items():axs[1].plot(t,r['residual_hz'],'.',label=arm)
    axs[1].set_ylabel('Best tested residual (Hz)');axs[1].legend()
    r=c['arms']['fitted_c'];axs[2].plot(t,r['residual_hz'],'k.',label='Target residual')
    selected=sorted(r['matches'],key=lambda w:(not w['same_family'],-w['points']))[:4]
    for w in selected:axs[2].plot(w['times_s'],w['residual_hz'],'.',label=f"{w['norad']} RX{w['receiver']} CH{w['channel']} r={w['correlation']:.2f} n={w['points']}")
    axs[2].set_ylabel('Independent-ID witnesses (Hz)');axs[2].legend(fontsize=8)
    axs[3].plot(t,[m['fractional_margin'] for m in c['metadata']],'.-',label='GLRT fractional margin')
    axs[3].plot(t,[m['fractional_epoch_offset_samples'] for m in c['metadata']],'.',label='Fractional epoch (samples)');axs[3].legend();axs[3].set_ylabel('Native metadata');axs[3].set_xlabel('Scan time (s)')
    for ax in axs:
        ax.grid(alpha=.2)
        for p in c['graph_pieces']:
            if 'join_time_s' in p:ax.axvline(p['join_time_s'],color='red',linestyle='--',alpha=.5)
    fig.suptitle(c['case']+' — native target, remaining residual, independent observation IDs and GLRT metadata\n'+c['residual_model'],fontsize=10)
    fig.tight_layout();fig.savefig(OUT/(c['case']+'.png'),dpi=150);fig.savefig(OUT/(c['case']+'.pdf'));plt.close(fig)


if __name__=='__main__':run()
