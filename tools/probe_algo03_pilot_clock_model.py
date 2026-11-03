"""Same saved-IQ comparison of rounded, fractional and decoupled frame models."""

from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

from decoupled_pilot_clocks import ContinuousCoupledWorkspace,ContinuousFrameWorkspace,isolated_pilot_wave
from fast_local_pilot_refinement import FastPilotWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_algo03_cross_receiver_carrier'
OUT=ROOT/'reports/2026_10_19_algo03_pilot_clock_model'


def main():
    if OUT.exists():
        raise FileExistsError('preserve waveform-model comparison')
    OUT.mkdir();source=read(SOURCE/'results.json');protocol=read(SOURCE/'protocol.json')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/decoupled_pilot_clocks.py'),
        frozen_RF_selection_sha256=sha(SOURCE/'protocol.json'),
        frozen_coupled_fit_sha256=sha(SOURCE/'results.json'),
        models=['legacy rounded-frame three-parameter fit','fractional-frame three-parameter fit',
                'fractional-frame four-parameter fit with separate intra-frame rate'],
        same_IQ_support_frame_gains_and_DC=True,no_GPS_TLE_satellite_or_position_used=True,
        no_IQ_or_frequency_observations_modified=True,workers=8,
        extra_parameter_BIC_penalty='log(2 * complex_sample_count)',
        RF_likelihood_assumes_white_complex_noise_and_is_not_calibrated=True))
    panels={}
    for path,digest in protocol['panel_sha256'].items():
        if sha(ROOT/path)!=digest:
            raise ValueError('saved IQ panel changed')
        panels[path]=np.load(ROOT/path,allow_pickle=False)
    for edge in ('lower','upper'):
        isolated_pilot_wave(2500000,edge);isolated_pilot_wave(2500000,edge,True)
    def one(index,rx,row):
        e=row['entry'];values=panels[e['panel']][e['window_key']]
        samples=values[:,rx,0].astype(float)+1j*values[:,rx,1]
        fs=e['sample_rate_hz'];epoch=e['epochs'][rx];old=row['fits'][rx]
        coupled=FastPilotWorkspace(samples,fs,e['edge'],epoch)
        params=np.array([old['CFO_hz'],old['offset_samples'],old['modulation_ppm']])
        base=coupled.statistics(params);points=sum(len(ix) for ix in coupled.frames)
        old_residual=base['raw_energy']*(1-base['score'])
        fractional=ContinuousCoupledWorkspace(samples,fs,e['edge'],epoch)
        fit=fractional.fast_joint_fit(old['CFO_hz'])
        parameters=[fit['CFO_hz'],fit['offset_samples'],fit['modulation_ppm']]
        single=fractional.statistics(parameters);fractional_residual=single['raw_energy']*(1-single['score'])
        independent=ContinuousFrameWorkspace(samples,fs,e['edge'],epoch)
        trials=[independent.clock_fit([fit['CFO_hz'],fit['offset_samples'],fit['modulation_ppm'],ppm])
                for ppm in (-30.,fit['modulation_ppm'],30.)]
        decoupled=max(trials,key=lambda r:r['score'])
        start=[decoupled['CFO_hz'],decoupled['offset_samples'],decoupled['frame_ppm'],decoupled['intra_ppm']]
        subsets={key:independent.clock_fit(start,subset=key) for key in ('odd','even')}
        return dict(index=index,receiver=rx+1,entry=e,legacy_fit=old,fractional_fit=fit,
            decoupled_fit=decoupled,odd_even_decoupled_fits=subsets,
            legacy_score=base['score'],legacy_residual_energy=old_residual,
            fractional_score=single['score'],fractional_residual_energy=fractional_residual,
            fractional_placement_BIC_gain=float(2*points*np.log(old_residual/fractional_residual)),
            decoupled_extra_parameter_BIC_gain=float(2*points*np.log(fractional_residual/decoupled['residual_energy'])-np.log(2*points)),
            fractional_minus_legacy_CFO_hz=fit['CFO_hz']-old['CFO_hz'],
            decoupled_minus_fractional_CFO_hz=decoupled['CFO_hz']-fit['CFO_hz'])
    rows=[];started=time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for future in as_completed([executor.submit(one,k,rx,row)
                                       for k,row in enumerate(source['rows']) for rx in (0,1)]):
                result=future.result();rows.append(result)
                print(result['entry']['case'],result['entry']['channel'],'RX',result['receiver'],
                    'fractional gain',round(result['fractional_placement_BIC_gain'],2),
                    'intra clock gain',round(result['decoupled_extra_parameter_BIC_gain'],2),
                    'CFO shifts',round(result['fractional_minus_legacy_CFO_hz'],2),
                    round(result['decoupled_minus_fractional_CFO_hz'],2),flush=True)
        write(OUT/'results.json',dict(rows=sorted(rows,key=lambda r:(r['index'],r['receiver'])),
            seconds=time.monotonic()-started,protocol_sha256=sha(OUT/'protocol.json'),
            no_GPS_TLE_position_or_calibration_updated=True,
            all_likelihood_and_covariance_statistics_are_RF_model_diagnostics_only=True))
    finally:
        for panel in panels.values():
            panel.close()


if __name__=='__main__':
    main()
