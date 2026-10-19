"""Measure native CFO effective time using matched opposite known chirps."""

from pathlib import Path
import numpy as np
from probe_native_code_carrier import periodic_upsample,interpolate_periodic
from probe_native_dynamic_timing import BUILD,quantize
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.analysis.starlink.templates import qin_edge_pilot_frame,CONTROL_SYMBOL_ROLL

OUT=ROOT/'reports/2026_10_19_native_cfo_time_reference'


def run():
    OUT.mkdir(parents=True,exist_ok=True);library=BUILD/'libleo-adaptive-detector.so'
    assert sha(library)==read(BUILD/'build-receipt.json')['outputs'][library.name]
    rows=[];summaries=[];upsample=32;rate=2000.
    for fs in (2500000,10000000):
        times=np.arange(fs//50)/fs;mid=times.mean();period=fs/750
        for edge in ('lower','upper'):
            template=np.asarray(qin_edge_pilot_frame(fs,edge),dtype='<c16')
            control=np.asarray(qin_edge_pilot_frame(fs,edge,symbol_roll=CONTROL_SYMBOL_ROLL),dtype='<c16')
            wave=np.zeros(round(fs/250),complex)
            for frame in range(3):
                start=round(frame*period);stop=min(start+len(template),len(wave));wave[start:stop]+=template[:stop-start]
            fine=periodic_upsample(wave,upsample)
            with NativeShortWindow(str(library),template,control,sample_rate_hz=fs,receiver_count=1,fractional_epoch=True) as native:
                for f0 in (-300000.,-150000.,0.,150000.,300000.,-300123.,-150057.,-53.,150031.,300087.):
                    for phase_fraction in np.arange(8)/8:
                        delay=(phase_fraction*period+.37)/fs
                        base=interpolate_periodic(fine,(times-delay)*fs*upsample)
                        result=[]
                        for slope in (-rate,0.,rate):
                            signal=base*np.exp(2j*np.pi*(f0*times+.5*slope*(times-mid)**2))
                            candidates=[c for c in native.analyze(quantize(signal))['rows'][0]['candidates'] if c['fractional_epoch']['status']=='complete']
                            winner=max(candidates,key=lambda c:c['fractional_epoch']['margin']) if candidates else None
                            record=dict(sample_rate_hz=fs,edge=edge,injected_midpoint_CFO_hz=f0,chirp_rate_hz_s=slope,
                                epoch_fraction=float(phase_fraction),detected=winner is not None)
                            if winner is not None:record.update(CFO_hz=winner['fractional_epoch']['tracking_cfo_hz'],
                                epoch_samples=winner['refined_epoch']+winner['fractional_epoch']['offset_samples'],
                                margin=winner['fractional_epoch']['margin'])
                            rows.append(record);result.append(record)
                        if all(r['detected'] for r in result):
                            negative,zero,positive=result
                            delta=(positive['CFO_hz']-negative['CFO_hz'])/(2*rate)
                            summaries.append(dict(sample_rate_hz=fs,edge=edge,CFO_hz=f0,epoch_fraction=float(phase_fraction),
                                effective_time_minus_midpoint_s=float(delta),effective_time_from_probe_start_s=float(mid+delta),
                                zero_chirp_error_hz=float(zero['CFO_hz']-f0),
                                even_chirp_error_hz=float((positive['CFO_hz']+negative['CFO_hz'])/2-zero['CFO_hz']),
                                positive_CFO_error_hz=float(positive['CFO_hz']-f0),negative_CFO_error_hz=float(negative['CFO_hz']-f0)))
            write(OUT/'partial.json',dict(rows=rows,summaries=summaries,source_sha256=sha(Path(__file__))))
            local=[r for r in summaries if r['sample_rate_hz']==fs and r['edge']==edge]
            print(fs,edge,'pairs',len(local),'effective delta ms median/range',np.median([r['effective_time_minus_midpoint_s'] for r in local])*1000,
                np.min([r['effective_time_minus_midpoint_s'] for r in local])*1000,np.max([r['effective_time_minus_midpoint_s'] for r in local])*1000,flush=True)
    write(OUT/'result.json',dict(rows=rows,summaries=summaries,source_sha256=sha(Path(__file__)),
        library_sha256=sha(library),build_receipt_sha256=sha(BUILD/'build-receipt.json'),
        midpoint_definition='mean of sample times 0..(N-1)/Fs',opposite_chirps_cancel_static_CFO_bias_to_first_order=True,
        same_envelope_and_epoch_for_both_chirps=True,no_GPS_TLE_or_recorded_IQ=True,
        timing_result_is_local_sensitivity_not_unconditionally_valid_measurement_timestamp=True))


if __name__=='__main__':run()
