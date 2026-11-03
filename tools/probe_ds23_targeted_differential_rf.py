"""Bounded saved-IQ validation of information-selected carrier contrasts.

No position is fitted here. Native acquisition is conditioned; carrier, code
epoch and modulation rate are refitted on training symbols. Whole paired
transmitter frames are resampled together for a conditional uncertainty check.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import argparse
import copy
import json
import os
import signal
import subprocess
import sys
import time
import numpy as np

from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_differential_frame_phase import unique_frame_intersections
from ds23_fractional_differential_phase import fractional_geometry
from ds23_common_probe_frequency import CommonProbeFrequency
from select_ds23_differential_information import OUT,BULK
from run_algo01_ds23_sample import ROOT,DATASET,read,write,sha


def prepare():
    selection=read(OUT/'target_selection.json');eligible=[r for r in selection['rows'] if r.get('selected')]
    # RF-information engineering pilots, selected without position errors.
    pilots=sorted(eligible,key=lambda r:(-sum(s['expected_position_variance_gain_km2'] for s in r['selected']),r['case']))[:3]
    cases=[r['case'] for r in pilots];jobs=[s for r in pilots for s in r['selected']]
    protocol=dict(cases=cases,jobs=jobs,pilot_selection='three largest predicted RF variance reductions; no geographic error',
        target_selection_sha256=sha(OUT/'target_selection.json'),dataset_manifest_sha256=sha(DATASET/'manifest.json'),
        maximum_raw_windows_per_case=8192,maximum_export_seconds=120,workers=8,per_probe_seconds=180,
        bootstrap_replicates=31,minimum_unique_transmitter_frames=10,
        jointly_refit_CFO_epoch_and_code_rate=True,training_symbol_folds=[0,1],
        contrast_sigma='max5Hz,whole-paired-frame bootstrap SD,fold disagreement/sqrt2,common-model contrast change',
        competing_differential_carrier_branches_hz=[-750,750],
        acquisition_and_RF_support_conditioned=True,bootstrap_not_absolute_frequency_truth=True,
        no_new_RF_collection_or_GPS_or_TLE_or_position_fit=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_joint_component_refinement.py',
            ROOT/'tools/ds23_common_probe_frequency.py',ROOT/'tools/ds23_differential_frame_phase.py']})
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);(BULK/'panels').mkdir(exist_ok=True)
    p=BULK/'protocol.json'
    if p.exists() and read(p)!=protocol:raise ValueError('targeted differential RF protocol changed')
    if not p.exists():write(p,protocol)
    write(OUT/'RF_pilot_protocol.json',protocol);return protocol


def export(case):
    target=BULK/'panels'/(case+'.npz')
    if target.exists():return dict(case=case,status='cached',sha256=sha(target))
    log=BULK/(case+'_export.log');partial=target.with_suffix('.partial.npz')
    code=('import probe_ds23_all_lane_components as e; from pathlib import Path; '
          f'e.BULK=Path({str(BULK)!r}); e.export({case!r})')
    with partial.open('wb') as stream,log.open('w') as errors:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),'-c',code],cwd=ROOT,
            env=dict(os.environ,PYTHONPATH='/tmp/algo03-feasible-deps:src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=stream,stderr=errors,timeout=145)
    if result.returncode:raise RuntimeError(f'{case} bounded read-only IQ export failed; see{log}')
    with np.load(partial,allow_pickle=False) as panel:
        meta=json.loads(str(panel['metadata_json']));assert meta['case']==case
    partial.replace(target);return dict(case=case,status='complete',sha256=sha(target))


def fit(workspace,start,parity=None,iterations=32):
    p=copy.copy(workspace);p.start=np.asarray(start,float).copy()
    fitted=p.optimize(parity=parity,iterations=iterations)
    stats=p.statistics(fitted['parameters'],parity,derivatives=True)
    noise=stats['squared_error']/max(1,stats['samples']-17*len(p.segments)-6)
    score=float(np.max(abs(stats['rhs'])/np.sqrt(np.maximum(np.diag(stats['normal'])*noise/2,1e-20))))
    covariance=np.diag(p.scale)@np.linalg.inv(stats['normal'])@np.diag(p.scale)*noise/2
    contrast=np.array([1.,0.,0.,-1.,0.,0.])
    return dict(fitted,maximum_standardized_score=score,
        difference_hz=float(contrast@fitted['parameters']),difference_sigma_proxy_hz=float(np.sqrt(contrast@covariance@contrast)),
        full_covariance=covariance,noise_variance=noise)


def one(job):
    case,probe=job['case'],job['probe'];target=BULK/f'{case}_probe{probe:06d}_RF.json'
    if target.exists():return read(target)
    began=time.monotonic();protocol=read(BULK/'protocol.json')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180second targeted differential RF cap')));signal.alarm(180)
    try:
        with np.load(BULK/'panels'/(case+'.npz'),allow_pickle=False) as panel:
            metadata=json.loads(str(panel['metadata_json']));point=next(p for p in metadata['points'] if p['probe']==probe)
            value=panel[point['window_key']][:,point['receiver_offset']]
        y=value[:,0].astype(float)+1j*value[:,1].astype(float);fs=metadata['sample_rate_hz']
        initial=[dict(CFO_hz=job[k]['cfo_hz'],offset_samples=0.,modulation_ppm=0.) for k in ['first','second']]
        epochs=[job[k]['epoch'] for k in ['first','second']]
        p=JointComponentWorkspace(y,fs,job['edge'],epochs,initial)
        geometries=[fractional_geometry(y,fs,job['edge'],e,f) for e,f in zip(epochs,initial,strict=True)]
        p.segments=unique_frame_intersections(*geometries,p.segments)
        if len(p.segments)<10:raise ValueError('fewer than ten unique paired transmitter frames')
        full=fit(p,p.start);folds=[]
        for parity in [0,1]:
            f=fit(p,p.start,parity)
            prediction=p.statistics(f['parameters'],parity,derivatives=False,prediction=True)
            common=CommonProbeFrequency(p,np.array(f['parameters']));shared=common.optimize(parity,iterations=24)
            held=common.statistics(shared['parameters'],parity,derivatives=False,prediction=True)
            alternative=[]
            for shift in [-750.,750.]:
                start=np.array(p.start);start[0]+=shift
                other=fit(p,start,parity,iterations=24)
                test=p.statistics(other['parameters'],parity,derivatives=False,prediction=True)
                gain=2*prediction['heldout_samples']*np.log(test['heldout_squared_error']/prediction['heldout_squared_error'])
                alternative.append(dict(shift_hz=shift,fit=other,held_gain_favoring_nominal=float(gain)))
            folds.append(dict(fit=f,prediction=prediction,common=shared,common_prediction=held,
                common_held_gain=float(2*prediction['heldout_samples']*np.log(prediction['heldout_squared_error']/held['heldout_squared_error'])),
                alternative_carriers=alternative))
        common_full=CommonProbeFrequency(p,np.array(full['parameters'])).optimize(iterations=24)
        rng=np.random.default_rng(2026102200+probe);replicates=[];segments=list(p.segments)
        for k in range(protocol['bootstrap_replicates']):
            draw=rng.integers(0,len(segments),len(segments))
            b=copy.copy(p);b.segments=[segments[i] for i in draw]
            f=fit(b,full['parameters'],iterations=24)
            replicates.append(dict(index=k,frames=draw,difference_hz=f['difference_hz'],
                parameters=f['parameters'],boundary=f['boundary'],maximum_standardized_score=f['maximum_standardized_score']))
        measured=full['difference_hz'];boot=float(np.std([r['difference_hz'] for r in replicates],ddof=1))
        disagreement=abs(folds[0]['fit']['difference_hz']-folds[1]['fit']['difference_hz'])
        common_change=abs(common_full['component_CFO_difference_hz']-measured)
        sigma=max(5.,boot,disagreement/np.sqrt(2),common_change)
        checks=dict(full_and_folds_interior=not any(f['boundary'] for f in [full]+[r['fit'] for r in folds]),
            fold_difference_agreement=disagreement<=20.,
            shared_receiver_profile_contrast_stability=common_change<=20.,
            both_folds_resolve750Hz_relative_carrier=all(a['held_gain_favoring_nominal']>10 for f in folds for a in f['alternative_carriers']),
            at_most_one_bootstrap_boundary=sum(r['boundary'] for r in replicates)<=1,
            at_least28_bootstrap_stationary=sum(r['maximum_standardized_score']<=.25 for r in replicates)>=28,
            full_and_fold_stationarity=all(f['maximum_standardized_score']<=.25 for f in [full]+[r['fit'] for r in folds]))
        record=dict(case=case,probe=probe,status='complete',job=job,full=full,folds=folds,common_full=common_full,
            frames=len(segments),segments=segments,bootstrap_replicates=replicates,
            measured_difference_hz=measured,bootstrap_sigma_hz=boot,fold_difference_hz=disagreement,
            common_model_difference_change_hz=common_change,declared_sigma_hz=sigma,checks=checks,
            RF_qualified=all(checks.values()),panel_sha256=sha(BULK/'panels'/(case+'.npz')),
            uncertainty_is_conditional_not_validated_absolute_coverage=True,
            no_new_RF_or_GPS_TLE_or_position_fit=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();record=dict(case=case,probe=probe,status='failed',error=repr(exc),job=job)
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-began;write(target,record)
    print(case,probe,record['status'],record.get('RF_qualified'),record.get('checks'),record.get('error'),flush=True);return record


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','export','RF'],required=True)
    args=parser.parse_args();protocol=prepare()
    if args.stage=='prepare':print(protocol['cases'],len(protocol['jobs']));return
    if args.stage=='export':
        with ProcessPoolExecutor(max_workers=3) as pool:
            receipts=[f.result() for f in as_completed([pool.submit(export,c) for c in protocol['cases']])]
        write(OUT/'RF_export.json',dict(receipts=receipts,all_terminal=True));return
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,j) for j in protocol['jobs']])]
    write(OUT/'RF_pilot.json',dict(rows=rows,all_terminal=True,RF_qualified=sum(r.get('RF_qualified',False) for r in rows),
        no_real_position_change=True))


if __name__=='__main__':main()
