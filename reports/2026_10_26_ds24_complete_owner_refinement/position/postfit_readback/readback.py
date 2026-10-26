"""Canonical gates at sealed endpoints only; no fit, nomination or data change."""
import time
STARTED=time.monotonic()
import argparse
import json
from pathlib import Path
import signal
import sys
import numpy as np

HERE=Path(__file__).resolve().parent;POSITION=HERE.parent;ROOT=POSITION.parent
sys.path.insert(0,str(POSITION))
import run as engine
from replacement import inject
from evaluate_ds23_phase_refreshed import extend_associations
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from prototype_dsx01_continuous_position import latlon
r=engine.r
TARGETS=('DS24-0011-RX1-CH4-T007-RF11690312500.000000','DS24-0011-RX2-CH5-T000-RF11940312500.000000')
ORDER=(('c0','original'),('c0','corrected'),('fitted_c','original'),('fitted_c','corrected'))


def write(name,value):r.write_new(HERE/name,value)


def freeze():
    protocol=r.read(POSITION/'protocol.json')
    paths=[Path(__file__),POSITION/'RF_seal.json',POSITION/'run.py',POSITION/'replacement.py',
           ROOT/'measurement/corrections.json',engine.REPO/'tools/evaluate_ds23_phase_refreshed.py',
           engine.REPO/'src/leo/analysis/research/polynomial_satellite_diagnostics.py',
           engine.REPO/'src/leo/analysis/research/retained_track_likelihood.py']
    for path,h in protocol['files'].items():
        if r.sha(path)!=h:raise ValueError('frozen position source changed')
    write('protocol.json',dict(files={str(p):r.sha(p) for p in paths},targets=TARGETS,order=ORDER,
        cap_seconds=30,workers=1,BLAS_threads=1,original_saved_RMS_bias_tolerance_hz=1e-6,
        objective_absolute_replay_tolerance=1e-8,root_authorization='bounded fixed-endpoint readback; no optimizer/remeasurement/gate change',
        all_original_active_calibration_families_compete=True,new_candidate_nomination=False))


def diagnose(d,arm,method):
    raw=r.read(POSITION/'DS24-0011'/method/arm/'raw_endpoint.json');record=raw['summary']
    p=r.build(d,arm,record['phase_reference']);x=np.asarray(record['endpoint_east_north_km']);c=p.calculate(x)
    if abs(c['negative_twice_elbo']-raw['full_objective'])>1e-8:raise ValueError('frozen endpoint objective replay failed')
    state=p.state(x);metrics=r.retained_metrics(p,x);accepted={t['component']:t for t in metrics['tracks'] if t['compatible']}
    labels=sorted({t['candidate_index'] for t in accepted.values()})
    supported_groups={(p.scan.tracks[i]['receiver'],int(p.scan.tracks[i]['channel']>4)) for i in p.members if p.scan.tracks[i]['key'] in accepted}
    begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels);predictions=[];elevations=[];available=[];excluded=[]
    for j in labels:
        phase=np.array([state['phases'][j]])
        if abs(phase[0])>15:excluded.append(dict(candidate_index=j,norad=int(p.scan.norads[j]),phase_s=float(phase[0])));continue
        bank=dict(time_s=p.scan.sky['time_s'],position_km=p.scan.sky['position_km'][[j]],velocity_km_s=p.scan.sky['velocity_km_s'][[j]])
        f,e=paired_phase_frequency(bank,p.scan.times,np.zeros(len(p.scan.times),int),phase,*latlon(x))
        if j in p.supported:
            k=p.supported.index(j);local=p.labels.index(j)
            modes=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*local:3*local+3],velocity_km_s=p.mode_bank['velocity_km_s'][3*local:3*local+3])
            derivative=paired_frequency_modes(bank,modes,p.scan.times,np.zeros(len(p.scan.times),int),phase,*latlon(x))
            f+=derivative@c['coefficient'][begin+3*k:begin+3*k+3]
        predictions.append(f);elevations.append(e);available.append(j)
    frequency=np.array(predictions);elevation=np.array(elevations);out=[]
    saved=r.read(POSITION/'DS24-0011'/method/arm/'gates.json')['membership']['associations']
    for key in TARGETS:
        i=next(i for i,t in enumerate(p.scan.tracks) if t['key']==key);t=p.scan.tracks[i];ix=p.scan.index[i]
        y=t['values']-p.scan.hardware(t,state['beta'])-t['rf_hz']/11.5e9*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y,t['rf_hz']/11.5e9*frequency[:,ix],*p.scan.white[i]);noise=batch_noise_screen(terms['innovations'],t['times'])
        good=(terms['rms']<=450)&(abs(terms['bias'])<=3000)&noise['noise_screen_pass']&(elevation[:,ix].min(axis=1)>=0)
        group=(t['receiver'],int(t['channel']>4));group_pass=group in supported_groups
        chosen=int(np.argmin(np.where(good,terms['cost'],np.inf))) if good.any() and group_pass else None
        expected=next((v for v in saved if v['component']==key and v['compatible']),None)
        if bool(chosen is not None)!=bool(expected):raise ValueError('canonical accepted status differs from sealed result')
        if expected:
            if int(p.scan.norads[available[chosen]])!=expected['norad']:raise ValueError('canonical family differs')
            if abs(terms['rms'][chosen]-expected['native_rms_hz'])>1e-6 or abs(terms['bias'][chosen]-expected['bias_hz'])>1e-6:raise ValueError('saved original RMS/bias does not replay')
        candidates=[];n=len(t['times'])
        for k,j in enumerate(available):
            diagnostics={name:float(np.asarray(value)[k]) for name,value in noise.items() if name!='noise_screen_pass'}
            predicates=dict(profile_RMS=bool(terms['rms'][k]<=450),profile_bias=bool(abs(terms['bias'][k])<=3000),
                noise_mean=diagnostics['mean_z']<=3,noise_slope=diagnostics['slope_z']<=3,
                noise_quadratic=diagnostics['quadratic_bic_gain']<=10,noise_step=diagnostics['maximum_step_z']<=4,
                noise_ACF=abs(diagnostics['lag1_acf'])<=4/np.sqrt(n),line_of_sight=bool(elevation[k,ix].min()>=0),
                supported_receiver_band=group_pass,phase_in_operational_domain=True)
            candidates.append(dict(candidate_index=j,norad=int(p.scan.norads[j]),phase_s=float(state['phases'][j]),
                original_supported_mode_slot=j in p.supported,profile_RMS_hz=float(terms['rms'][k]),bias_hz=float(terms['bias'][k]),
                profiled_alias=int(terms['alias'][k]),minimum_elevation=float(elevation[k,ix].min()),cost=float(terms['cost'][k]),
                noise=diagnostics,predicates=predicates,passing=bool(good[k] and group_pass),
                failed_predicates=[name for name,on in predicates.items() if not on]))
        out.append(dict(owner=key,points=n,arm=arm,method=method,group=list(group),supported_group=group_pass,
            chosen_norad=int(p.scan.norads[available[chosen]]) if chosen is not None else None,
            saved_status_reproduced=True,candidates=candidates,phase_excluded_candidates=excluded))
    return out


def run():
    protocol=r.read(HERE/'protocol.json')
    for path,h in protocol['files'].items():
        if r.sha(path)!=h:raise ValueError('bound readback input/source changed')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('fixed30-second readback cap')))
    signal.setitimer(signal.ITIMER_REAL,max(.001,30-(time.monotonic()-STARTED)))
    rows=[];failure=None
    try:
        d=r.context('DS24-0011');corrections=[x for x in r.read(ROOT/'measurement/corrections.json')['rows'] if x['case']=='DS24-0011']
        changed,_=inject(d,corrections,engine.selected()['DS24-0011']['native_IDs'])
        for arm,method in ORDER:
            rows+=diagnose(d if method=='original' else changed,arm,method)
            write(arm+'_'+method+'.json',rows[-2:])
    except Exception as exc:failure=repr(exc)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    write('result.json',dict(rows=rows,failure=failure,all8_owner_contexts_complete=len(rows)==8,
        cumulative_seconds=time.monotonic()-STARTED,position_fits=0,detector_calls=0,gates_changed=False))
    paths=[p for p in HERE.iterdir() if p.is_file() and p.name!='seal.json']
    write('seal.json',dict(protocol_sha256=r.sha(HERE/'protocol.json'),files={str(p):r.sha(p) for p in paths}))
    print('TERMINAL',len(rows),failure,time.monotonic()-STARTED,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));a=parser.parse_args()
    {'freeze':freeze,'run':run}[a.action]()
