"""Bounded eight-coordinate RF pilot, retaining full carrier/rate covariance."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import copy
import signal
import time
import numpy as np

from audit_ds23_targeted_differential_rf import reconstruct
from ds23_chirped_component_workspace import ChirpedComponentWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha
from select_ds23_differential_information import OUT as PARENT

OUT=PARENT/'chirped_validation'


def one(record):
    started=time.monotonic();case,probe=record['case'],record['probe'];path=OUT/f'{case}_probe{probe:06d}.json'
    if path.exists():return read(path)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s chirped RF pilot cap')));signal.alarm(300)
    try:
        p=ChirpedComponentWorkspace.from_workspace(reconstruct(record))
        smooth=read(PARENT/'smooth_validation'/f'{case}_probe{probe:06d}.json')
        full=p.fit(np.r_[smooth['full']['parameters'],0.,0.]);folds=[]
        for parity in [0,1]:
            fitted=p.fit(np.asarray(full['parameters']),parity)
            held=p.statistics(fitted['parameters'],parity,derivatives=False,prediction=True)
            old=smooth['folds'][parity]['prediction']
            folds.append(dict(fit=fitted,prediction=held,
                held_gain_over_constant=float(2*held['heldout_samples']*np.log(old['heldout_squared_error']/held['heldout_squared_error']))))
        segments=list(p.segments);rng=np.random.default_rng(2026102200+probe);boot=[]
        for k in range(31):
            draw=rng.integers(0,len(segments),len(segments));v=copy.copy(p);v.segments=[segments[i] for i in draw]
            f=v.fit(full['parameters'],iterations=100)
            boot.append(dict(index=k,frames=draw,fit=f))
        covariance=np.cov(np.array([r['fit']['contrast'] for r in boot]).T,ddof=1)
        sigma=float(np.sqrt(covariance[0,0]));difference=abs(folds[0]['fit']['contrast'][0]-folds[1]['fit']['contrast'][0])
        checks=dict(full_and_folds_interior=not any(r['boundary'] for r in [full]+[r['fit'] for r in folds]),
            full_and_fold_stationarity=all(r['maximum_standardized_score']<=.01 for r in [full]+[r['fit'] for r in folds]),
            at_most_one_bootstrap_boundary=sum(r['fit']['boundary'] for r in boot)<=1,
            at_least28_bootstrap_stationary=sum(r['fit']['maximum_standardized_score']<=.01 for r in boot)>=28,
            fold_difference_agreement=difference<=20.,neither_fold_loses_more_than10=all(f['held_gain_over_constant']>=-10 for f in folds))
        result=dict(case=case,probe=probe,status='complete',job=record['job'],full=full,folds=folds,
            bootstrap_replicates=boot,bootstrap_contrast_covariance=covariance,
            conditional_CFO_sigma_hz=max(5.,sigma,difference/np.sqrt(2),record['declared_sigma_hz']),
            checks=checks,chirp_quality_checks_pass=all(checks.values()),
            carrier_alias_requalification_still_required=True,
            carrier_epoch_relative_to_GLRT_s=-.5/p.fs,
            no_position_or_GPS_or_TLE_or_new_RF=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,probe=probe,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(case,probe,result['status'],result.get('chirp_quality_checks_pass'),result.get('checks'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);source=read(PARENT/'RF_pilot.json');selected=[r for r in source['rows'] if r.get('RF_qualified')]
    protocol=dict(source_sha256=sha(PARENT/'RF_pilot.json'),
        selection='all three original RF-qualified probes; no geographic outcome',
        selected=[dict(case=r['case'],probe=r['probe']) for r in selected],
        original_CFO_code_epoch_code_rate_bounds=True,within_window_carrier_rate_bounds_hz_s=[-15000,15000],
        retained_original_frames_and_unique_transmitter_support=True,bootstrap_replicates=31,
        symbol_folds=[0,1],workers=3,per_probe_seconds=300,
        uncertainty_is_conditional_not_absolute_coverage=True,new_position_factors_not_qualified=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_chirped_component_workspace.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('chirped RF protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r) for r in selected])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,quality_checks_pass=sum(r.get('chirp_quality_checks_pass',False) for r in rows),
        new_position_evidence_not_yet_qualified=True))


if __name__=='__main__':main()
