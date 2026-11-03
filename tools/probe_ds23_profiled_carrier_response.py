"""Bounded diagnosis of RF rate response on the three qualified pilot probes."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import copy
from pathlib import Path
import signal
import time
import numpy as np

from audit_ds23_targeted_differential_rf import reconstruct
from ds23_differential_rf_epoch import frequency_rate_response,inject_component_rates
from ds23_profiled_carrier_response import tight_fit,observed_rate_response
from ds23_smooth_component_workspace import SmoothComponentWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha
from select_ds23_differential_information import OUT as PARENT


OUT=PARENT/'profile_response_fine'


def one(record,interpolation='linear',maximum_rate=1000.):
    started=time.monotonic();case,probe=record['case'],record['probe']
    target=OUT/f'{case}_probe{probe:06d}.json'
    if target.exists():return read(target)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s RF response cap')))
    signal.alarm(300)
    try:
        p=reconstruct(record)
        if interpolation=='cubic':p=SmoothComponentWorkspace.from_workspace(p)
        fit=tight_fit(p,record['full']['parameters'])
        parameters=np.asarray(fit['parameters']);gn=frequency_rate_response(p,parameters)
        observed=observed_rate_response(p,parameters)
        finer=observed_rate_response(p,parameters,coordinate_step=5e-8,rate_step=25.)
        injected=[]
        for component in [0,1]:
            for magnitude in [100.,float(maximum_rate)]:
                fits=[]
                for sign in [-1,1]:
                    rates=np.zeros(2);rates[component]=sign*magnitude
                    view=copy.copy(p);view.y=inject_component_rates(p,parameters,rates)
                    fits.append(tight_fit(view,parameters))
                measured=(fits[1]['difference_hz']-fits[0]['difference_hz'])/2
                injected.append(dict(component=component,magnitude_hz_s=magnitude,fits=fits,
                    measured_shift_hz=measured,Gauss_Newton_expected_shift_hz=float(gn[component]*magnitude),
                    observed_expected_shift_hz=float(observed['response_s'][component]*magnitude),
                    observed_discrepancy_hz=float(measured-observed['response_s'][component]*magnitude)))
        result=dict(case=case,probe=probe,status='complete',source_RF_qualified=True,
            original_full=record['full'],tight_full=fit,Gauss_Newton_response_s=gn,
            observed_response=observed,finer_observed_response=finer,injected_fits=injected,
            maximum_observed_response_discrepancy_hz=max(abs(r['observed_discrepancy_hz']) for r in injected),
            maximum_fit_stationarity=max(f['maximum_standardized_score'] for r in injected for f in r['fits']),
            response_step_difference_s=float(np.max(abs(observed['response_s']-finer['response_s']))),
            no_position_or_GPS_TLE_or_new_RF=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,probe=probe,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result)
    print(case,probe,result['status'],result.get('maximum_observed_response_discrepancy_hz'),
        result.get('maximum_fit_stationarity'),result.get('error'),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpolation',choices=['linear','cubic'],default='linear')
    parser.add_argument('--maximum-rate',type=float,default=1000.)
    args=parser.parse_args()
    global OUT
    if args.interpolation=='cubic':OUT=PARENT/'profile_response_smooth'
    if args.maximum_rate!=1000.:OUT=OUT.with_name(OUT.name+f'_rate{args.maximum_rate:g}')
    OUT.mkdir(exist_ok=True)
    selected=[r for r in read(PARENT/'RF_pilot.json')['rows'] if r.get('RF_qualified')]
    protocol=dict(source_sha256=sha(PARENT/'RF_pilot.json'),
        probes=[dict(case=r['case'],probe=r['probe']) for r in selected],
        selection='all three original RF-qualified probes; no geographic outcomes',
        original_RF_bounds_retained=True,new_orbital_or_position_parameters=False,
        interpolation=args.interpolation,
        original_0p3Hz_response_check_retained=True,finite_difference_steps=[1e-7,5e-8],
        injected_component_rates_hz_s=[-args.maximum_rate,-100,100,args.maximum_rate],
        maximum_seconds_per_probe=300,workers=3,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_profiled_carrier_response.py',
            ROOT/'tools/ds23_smooth_component_workspace.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('RF response protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r,args.interpolation,args.maximum_rate) for r in selected])]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,no_real_position_result_changed=True))


if __name__=='__main__':main()
