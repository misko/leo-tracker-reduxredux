"""Bounded causal orbit diagnostics for exact published residual graph IDs.

Research only. Receiver calibration is frozen at each baseline c-arm endpoint.
No GPS, new RF, future elements, association changes, or localization claims.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context, exact, ARMS, PHASES
from leo.analysis.research.track_recovery_diagnostics import shortlist
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.graph_position_membership import native_polynomial
from prototype_dsx01_continuous_position import latlon
from inventory_ds26 import published_ids

MODELS = ('constant', 'small_rate')
AUDITED_NOMINEES = {'DS26-0265':[66102], 'DS26-0223':[63595],
                    'DS26-0050':[63468], 'DS26-0251':[67352],
                    'DS26-0094':[66365,58722]}


def residual_track(track, ids):
    """Never fit associated points hidden inside a partial residual track."""
    wanted = set(ids)
    mask = np.array([oid in wanted for oid in track['observation_ids']])
    assert set(np.array(track['observation_ids'])[mask]) == wanted
    result = copy.copy(track)
    for key in ('times', 'values', 'observation_ids'):
        result[key] = np.asarray(track[key])[mask]
    return result, mask


def raw_prediction(track, native, corrected, fit):
    """Undo alias lift and receiver correction by the residual identity."""
    return np.asarray(native) - np.asarray(fit['residual_hz'])


def break_alias_connections(values, graph_lifted, native):
    """Break rendered lines at native alias transitions; keep points intact."""
    lifts=np.asarray(graph_lifted)-np.asarray(native)
    breaks=np.r_[False,abs(np.diff(lifts))>100000.]
    rendered=np.array(values,dtype=float,copy=True)
    rendered[breaks]=np.nan
    return rendered,breaks


def minimal(fit):
    arrays = {'times_s', 'residual_hz', 'corrected_observation_hz', 'orbit_prediction_hz'}
    return {k: v for k, v in fit.items() if k not in arrays}


def one(args):
    began = time.monotonic()
    row = read(args.ranking)[args.rank-1]
    out = args.output / f"{row['rank']:02d}-{row['case']}"
    out.mkdir(parents=True, exist_ok=False)
    inv = read(row['inventory_path'])
    d = context(inv)
    scan = d['scan']
    original = scan.tracks[row['track_index']]
    assert original['key'] == row['component']
    track, mask = residual_track(original, row['residual_observation_ids'])
    t = np.asarray(track['times'])
    terminal = read(row['terminal_path'])
    associated = published_ids(terminal, terminal['selected_arm'])
    assert not set(track['observation_ids']) & associated
    obs = read(row['observations_path'])
    byid = {o['observation_id']: o for o in obs}
    native = np.array([byid[oid]['measured_cfo_hz'] for oid in track['observation_ids']])
    observed, initial, calibration = {}, {}, {}
    for arm, (p, x) in d['problems'].items():
        state = p.state(x)
        correction = scan.hardware(original, state['beta']) + original['rf_hz']/11.5e9 * scan.rx_basis[row['track_index']] @ state['smooth'][original['receiver']-1]
        observed[arm] = np.asarray(original['values'])[mask] - correction[mask]
        initial[arm] = x
        calibration[arm] = dict(endpoint_east_north_km=x, beta=state['beta'],
                                receiver_correction_hz=correction[mask], objective_replay=d['replay'][arm])
    positions = {'current_'+a: x for a, x in initial.items()}
    positions.update({f'regional_{e:g}_{n:g}': np.array([e,n])
                      for e in (-10.,0.,10.) for n in (-10.,0.,10.)})
    knots = np.linspace(t.min(), t.max(), max(2, int(np.ceil(np.ptp(t)/2))+1))
    pick = np.unique(np.linspace(0,len(t)-1,min(20,len(t))).astype(int))
    offers = {}
    coarse = []
    for name, position in positions.items():
        ff, ee = [], []
        for phase in PHASES:
            f,e = phase_frequency_grid(scan.sky,knots,*latlon(position),phase_seconds=phase)
            ff.append(f.astype(np.float32)); ee.append(e.astype(np.float32))
        for arm in ARMS:
            for model in MODELS:
                found = shortlist(observed[arm][pick],t[pick],track['rf_hz']/11.5e9,
                    np.array(ff),np.array(ee),knots,PHASES,top=5,
                    rate_sigma_hz_s=0. if model=='constant' else .5,bias_sigma_hz=1000.)
                offers[arm,model,name] = found
                coarse.append(dict(arm=arm,model=model,position=name,candidates=found))
        print(row['case'], 'grid', name, flush=True)
    write(out/'coarse.json',coarse)
    trials = {a:{model:[] for model in MODELS} for a in ARMS}
    budgets = {}
    for model in MODELS:
        # Both arms get identical identities, positions, phase windows and count.
        guesses = []
        for arm in ARMS:
            for g in offers[arm,model,'current_'+arm]:
                guesses.append(dict(g, position_name='endpoint', search='current'))
            ranked = [dict(g,position_name=name,search='regional') for name in positions
                      for g in offers[arm,model,name]]
            ranked.sort(key=lambda g:g['cost'])
            seen = set()
            for g in ranked:
                if g['candidate_index'] in seen: continue
                seen.add(g['candidate_index']); guesses.append(g)
                if len(seen)==5: break
        guesses = list({(g['candidate_index'],g['phase_s'],g['position_name']):g for g in guesses}.values())
        for norad in AUDITED_NOMINEES[row['case']]:
            idx=np.flatnonzero(scan.norads==norad)
            if len(idx):
                guesses += [dict(candidate_index=int(idx[0]),phase_s=phase,position_name='endpoint',search='audited_nominee')
                            for phase in (-12.,-6.,0.,6.,12.)]
        budgets[model] = guesses
        for arm in ARMS:
            for g in guesses:
                position = initial[arm] if g['position_name']=='endpoint' else positions[g['position_name']]
                fit = exact(scan,track,observed[arm],g,position,model)
                provenance = scan.elements[str(fit['norad'])]['provenance']
                fit.update(search=g['search'],position_name=g['position_name'],satellite_name=provenance['name'],
                    element_age_at_origin_s=(scan.receipt['origin_utc_ns']-provenance['element_epoch_utc_ns'])/1e9,
                    element_epoch_utc_ns=provenance['element_epoch_utc_ns'],
                    element_collected_utc_ns=provenance['collected_utc_ns'])
                fit['failed_gates'] = ([g for g, fail in (
                    ('RMS',fit['rms_hz']>450),('offset',abs(fit['offset_hz'])>3000),
                    ('rate',abs(fit['rate_hz_s'])>2),('visibility',fit['minimum_elevation_deg']<0),
                    ('residual_structure',not fit['noise']['noise_screen_pass'])) if fail])
                trials[arm][model].append(fit)
            trials[arm][model].sort(key=lambda f:f['cost'])
    # Twenty-second local catalogue checks expose gross joins without claiming
    # independent validation or splitting; no temporal holdout is performed.
    segments = []
    for start in np.arange(t.min(),t.max(),20.):
        sm = (t>=start)&(t<start+20.)
        if sm.sum()<8: continue
        sub = copy.copy(track)
        for key in ('times','values','observation_ids'): sub[key]=np.asarray(track[key])[sm]
        guesses = []
        for arm in ARMS:
            ff,ee = [],[]
            for phase in PHASES:
                f,e=phase_frequency_grid(scan.sky,sub['times'],*latlon(initial[arm]),phase_seconds=phase)
                ff.append(f);ee.append(e)
            found=shortlist(observed[arm][sm],sub['times'],track['rf_hz']/11.5e9,np.array(ff),np.array(ee),sub['times'],PHASES,top=3)
            guesses+=found
            best=trials[arm]['constant'][0]
            guesses.append(dict(candidate_index=best['candidate_index'],phase_s=best['phase_s']))
        guesses=list({(g['candidate_index'],g['phase_s']):g for g in guesses}.values())
        fits = {a:[exact(scan,sub,observed[a][sm],g,initial[a],'constant') for g in guesses] for a in ARMS}
        segments.append(dict(start_s=float(start),end_s=float(start+20),points=int(sm.sum()),
            trials=fits,independent_phase_offset=True,diagnostic_only=True))
    p,_ = d['problems']['c0']
    engine_row=next((r for r in p.rows if r['component']==original['key']),None)
    top = {a:{} for a in ARMS}
    for arm in ARMS:
        for model in MODELS:
            seen=set();top[arm][model]=[]
            for fit in trials[arm][model]:
                if fit['norad'] in seen:continue
                seen.add(fit['norad']);top[arm][model].append(minimal(fit))
                if len(seen)==5:break
    result = dict(row=row,calibration=calibration,top_competitors=top,trials=trials,segments=segments,
        engine_nominee=engine_row,engine_curved=row['track_index'] in scan.curved,
        causal_bank_size=len(scan.norads),cutoff_utc_ns=scan.receipt['cutoff_utc_ns'],origin_utc_ns=scan.receipt['origin_utc_ns'],
        matched_exact_offers=budgets,source_inventory=str(row['inventory_path']),
        seconds=time.monotonic()-began,diagnostic_only=True,no_new_associations=True,
        no_localization_claim=True,frozen_receiver_calibration=True)
    trial_path=Path(row['terminal_path']).parent/'recovery'/row['track_id']/'trial/target_0.json'
    if trial_path.exists():
        inclusion=read(trial_path)
        result['actual_pipeline_trial']=dict(path=str(trial_path),
            sha256=hashlib.sha256(trial_path.read_bytes()).hexdigest(),
            arms={a:inclusion['arms'][a]['target_diagnostics'][0] for a in ARMS},
            note='Actual joint inclusion residual; includes pipeline orbital priors. Separate from frozen diagnostic gates.')
    write(out/'result.json',result)
    with (out/'points.csv').open('x',newline='') as stream:
        cols=['observation_id','time_s','raw_cfo_hz','graph_lifted_hz']
        for arm in ARMS:
            for model in MODELS:cols += [arm+'_'+model+'_residual_hz',arm+'_'+model+'_raw_prediction_hz']
        writer=csv.DictWriter(stream,fieldnames=cols);writer.writeheader()
        for k, oid in enumerate(track['observation_ids']):
            rec=dict(observation_id=oid,time_s=t[k],raw_cfo_hz=native[k],graph_lifted_hz=track['values'][k])
            for arm in ARMS:
                for model in MODELS:
                    fit=trials[arm][model][0]
                    rec[arm+'_'+model+'_residual_hz']=fit['residual_hz'][k]
                    rec[arm+'_'+model+'_raw_prediction_hz']=native[k]-fit['residual_hz'][k]
            writer.writerow(rec)
    plot(out,result,track,original,obs,associated,byid,native)
    print(row['case'],'COMPLETE',[(a,m,top[a][m][0]['norad'],top[a][m][0]['rms_hz']) for a in ARMS for m in MODELS],flush=True)


def plot(out,result,track,original,obs,associated,byid,native):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    row=result['row'];trials=result['trials'];t=track['times']
    fig,axes=plt.subplots(4,1,figsize=(14,13),layout='constrained',height_ratios=(1.7,1.2,1.2,1.2))
    lane=[o for o in obs if (o['receiver'],o['channel'])==(row['receiver'],row['channel'])
          and t.min()-7<=o['time_s']<=t.max()+7]
    target=set(track['observation_ids'])
    for color,label,choose,size in [('.72','Published satellite-associated',lambda oid:oid in associated,13),
        ('darkorange','Other unassociated GLRT winners',lambda oid:oid not in associated and oid not in target,18),
        ('crimson','Target residual IDs',lambda oid:oid in target,23)]:
        q=[o for o in lane if choose(o['observation_id'])]
        axes[0].scatter([o['time_s'] for o in q],[o['measured_cfo_hz']/1000 for o in q],s=size,c=color,label=label)
    for k,y in enumerate(native_polynomial(original,byid)):
        full_native=np.array([byid[o]['measured_cfo_hz'] for o in original['observation_ids']])
        rendered,_=break_alias_connections(y,original['values'],full_native)
        axes[0].plot(original['times'],rendered/1000,c='black',lw=1.3,label='Original graph polynomial' if k==0 else None)
    for arm,color,style in [('c0','#0072b2','--'),('fitted_c','#009e73','-')]:
        fit=trials[arm]['constant'][0]
        rendered,breaks=break_alias_connections(raw_prediction(track,native,fit['corrected_observation_hz'],fit),track['values'],native)
        axes[0].plot(t,rendered/1000,c=color,ls=style,lw=1.5,
                     label=f"Orbit diagnostic {arm}: {fit['satellite_name']} ({fit['norad']})")
    actual=result.get('actual_pipeline_trial')
    if actual:
        z=actual['arms']['fitted_c']
        assert np.allclose(z['times_s'],t)
        rendered,_=break_alias_connections(native-np.asarray(z['residual_hz']),track['values'],native)
        axes[0].plot(t,rendered/1000,c='#cc79a7',lw=1.4,ls=':',label='Actual pipeline inclusion trial, fitted_c')
    if breaks.any():
        axes[0].plot([],[],c='none',label='Lines break at native alias wraps')
    axes[0].set_ylabel('Native GLRT CFO (kHz)');axes[0].legend(fontsize=8,ncol=2)
    for ax,model in zip(axes[1:3],MODELS):
        for arm,color in [('c0','#0072b2'),('fitted_c','#009e73')]:
            fit=trials[arm][model][0]
            ax.plot(t,fit['residual_hz'],'.-',ms=3,c=color,label=f"{arm} best {fit['norad']}: {fit['rms_hz']:.1f} Hz RMS")
            competitor=next((q for q in trials[arm][model] if q['norad']!=fit['norad']),None)
            if competitor:
                ax.plot(t,competitor['residual_hz'],ls='--',c=color,alpha=.5,
                    label=f"{arm} runner-up {competitor['norad']}: {competitor['rms_hz']:.1f} Hz")
        ax.axhline(0,c='.5',lw=.6);ax.axhline(450,c='.5',lw=.6,ls=':');ax.axhline(-450,c='.5',lw=.6,ls=':')
        if actual and model=='constant':
            for arm,style in [('c0','--'),('fitted_c',':')]:
                z=actual['arms'][arm]
                ax.plot(z['times_s'],z['residual_hz'],c='#cc79a7',ls=style,lw=1.2,
                        label=f"Actual pipeline trial {arm}: {z['RMS_hz']:.1f} Hz")
        ax.set_ylabel('Residual (Hz)');ax.set_title(model.replace('_',' ')+' profile; matched c arms, frozen baseline receiver calibration')
        ax.legend(fontsize=8,ncol=2)
    for arm,color in [('c0','#0072b2'),('fitted_c','#009e73')]:
        for k,seg in enumerate(result['segments']):
            fit=min(seg['trials'][arm],key=lambda f:f['cost'])
            axes[3].plot(fit['times_s'],fit['residual_hz'],'.-',ms=3,c=color,label=arm if k==0 else None)
            if arm=='fitted_c':axes[3].annotate(str(fit['norad']),(np.mean(fit['times_s']),np.mean(fit['residual_hz'])),fontsize=8)
    axes[3].set_ylabel('Segment residual (Hz)');axes[3].set_title('Independent 20 s constant-profile fits (diagnostic only; labelled NORAD winners)');axes[3].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2);ax.set_xlabel('Device time (s)')
    fig.suptitle(f"#{row['rank']} {row['case']} RX{row['receiver']} CH{row['channel']} T{row['component'].split('-T')[1].split('-')[0]} — {row['span_s']:.2f} s / {row['residual_points']} residual IDs\nCausal orbit hypotheses; ±15 s phase, current c-arm endpoints + shared ±10 km regional grid; no identity acceptance",fontsize=12)
    fig.savefig(out/'diagnostic.png',dpi=155);fig.savefig(out/'diagnostic.pdf');plt.close(fig)


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(ranking=str(args.ranking),ranks=[1,2,3,4,5],workers=4,seconds_per_case=420,
        thread_limits=1,phase_grid_s=PHASES,regional_east_north_grid_km=[-10,0,10],models=MODELS,
        nominees='all causal bank satellites coarse ranked; union top5 endpoint and top5 regional distinct identities from each c arm',
        audited_nominees=AUDITED_NOMINEES,audited_nominee_extra_phase_starts_s=[-12,-6,0,6,12],
        matched_c_offers=True,exact_all_residual_points=True,baseline_receiver_calibration_frozen=True,
        no_GPS=True,no_future_TLE=True,no_new_RF=True,no_production_changes=True,
        segment_note='20s diagnostic fits only, never treated as holdout or splitting validation',
        source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    def work(rank):
        log=args.output/f'{rank:02d}.log'
        cmd=[sys.executable,__file__,'one','--ranking',str(args.ranking),'--output',str(args.output),'--rank',str(rank)]
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
        began=time.monotonic()
        with log.open('x') as f:
            try:
                p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=420,check=False)
                return dict(rank=rank,returncode=p.returncode,seconds=time.monotonic()-began)
            except subprocess.TimeoutExpired:return dict(rank=rank,status='timeout',seconds=time.monotonic()-began)
    executions=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(work,r) for r in range(1,6)]):
            executions.append(future.result());print(executions[-1],flush=True)
    write(args.output/'execution.json',executions)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['run','one'])
    p.add_argument('--ranking',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rank',type=int)
    a=p.parse_args();run(a) if a.mode=='run' else one(a)
