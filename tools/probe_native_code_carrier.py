"""Native CFO sensitivity to independently warped modulation time, not RF time."""

from pathlib import Path
import numpy as np
from probe_dynamic_pilot_timing import FS,PERIOD,geometry,detrend
from probe_native_dynamic_timing import BUILD,quantize
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.analysis.starlink.templates import qin_edge_pilot_frame,CONTROL_SYMBOL_ROLL

OUT=ROOT/'reports/2026_10_19_native_code_carrier'


def periodic_upsample(waveform,factor):
    y=np.asarray(waveform,complex);n=len(y)
    if y.ndim!=1 or n<2 or not isinstance(factor,int) or factor<1:raise ValueError('vector and positive integer interpolation factor required')
    if factor==1:return y.copy()
    frequency=np.fft.fft(y);padded=np.zeros(n*factor,complex);half=n//2
    padded[:(n+1)//2]=frequency[:(n+1)//2]
    if n%2:padded[-half:]=frequency[-half:]
    else:
        if half>1:padded[-half+1:]=frequency[-half+1:]
        padded[half]=padded[-half]=frequency[half]/2
    return np.fft.ifft(padded)*factor


def interpolate_periodic(waveform,positions):
    ix=np.floor(positions).astype(np.int64);fraction=positions-ix
    return (1-fraction)*waveform[ix%len(waveform)]+fraction*waveform[(ix+1)%len(waveform)]


def run():
    OUT.mkdir(parents=True,exist_ok=True);library=BUILD/'libleo-adaptive-detector.so';receipt=read(BUILD/'build-receipt.json')
    assert sha(library)==receipt['outputs'][library.name]
    times=np.arange(-120,121,20);ppms=(-40,-20,0,20,40);upsample=32;rows=[]
    local=np.arange(FS//50)/FS
    for edge in ('lower','upper'):
        template=np.asarray(qin_edge_pilot_frame(FS,edge),dtype='<c16')
        control=np.asarray(qin_edge_pilot_frame(FS,edge,symbol_roll=CONTROL_SYMBOL_ROLL),dtype='<c16')
        wave=np.zeros(10000,complex)
        for frame in range(3):
            start=round(frame*PERIOD);stop=min(start+len(template),len(wave));wave[start:stop]+=template[:stop-start]
        fine=periodic_upsample(wave,upsample)
        with NativeShortWindow(str(library),template,control,sample_rate_hz=FS,receiver_count=1,fractional_epoch=True) as native:
            for ppm in ppms:
                for t in times:
                    delay,rate=geometry(t+local)
                    argument=(t+local-delay+ppm*1e-6*local)*FS*upsample
                    signal=interpolate_periodic(fine,argument)*np.exp(2j*np.pi*(100000*local-11.5e9*(delay-delay[0])))
                    document=native.analyze(quantize(signal));candidates=[c for c in document['rows'][0]['candidates'] if c['fractional_epoch']['status']=='complete']
                    c=max(candidates,key=lambda v:v['fractional_epoch']['margin']) if candidates else None
                    row=dict(edge=edge,code_clock_ppm=ppm,scene_time_s=int(t),injected_CFO_hz=float(100000-11.5e9*np.mean(rate)),detected=c is not None)
                    if c is not None:row.update(CFO_hz=c['fractional_epoch']['tracking_cfo_hz'],margin=c['fractional_epoch']['margin'],
                        epoch_samples=c['refined_epoch']+c['fractional_epoch']['offset_samples'])
                    if ppm==0:
                        midpoint=t+local.mean();_,midrate=geometry(midpoint);clock_rate=float(1-midrate)
                        physical=midpoint+(local-local.mean())/clock_rate
                        oracle_delay,_=geometry(physical)
                        oracle_signal=interpolate_periodic(fine,(physical-oracle_delay)*FS*upsample)
                        oracle_signal*=np.exp(2j*np.pi*(100000*(physical-physical[0])-11.5e9*(oracle_delay-oracle_delay[0])))
                        oc=[v for v in native.analyze(quantize(oracle_signal))['rows'][0]['candidates'] if v['fractional_epoch']['status']=='complete']
                        if oc:
                            best=max(oc,key=lambda v:v['fractional_epoch']['margin'])
                            row.update(oracle_modulation_rate=clock_rate,oracle_physical_CFO_hz=best['fractional_epoch']['tracking_cfo_hz']*clock_rate,
                                oracle_CFO_error_hz=float(best['fractional_epoch']['tracking_cfo_hz']*clock_rate-row['injected_CFO_hz']))
                    rows.append(row)
                print(edge,'code ppm',ppm,'done',flush=True)
    summaries=[]
    for edge in ('lower','upper'):
        nominal=[r for r in rows if r['edge']==edge and r['code_clock_ppm']==0 and r['detected']]
        baseline={r['scene_time_s']:r for r in nominal}
        for ppm in ppms:
            local_rows=[r for r in rows if r['edge']==edge and r['code_clock_ppm']==ppm and r['detected']]
            errors=np.array([r['CFO_hz']-r['injected_CFO_hz'] for r in local_rows])
            differences=np.array([r['CFO_hz']-baseline[r['scene_time_s']]['CFO_hz'] for r in local_rows if r['scene_time_s'] in baseline])
            summaries.append(dict(edge=edge,code_clock_ppm=ppm,detected=len(local_rows),trials=len(times),
                CFO_error_RMS_hz=float(np.sqrt(np.mean(errors**2))),CFO_error_mean_hz=float(errors.mean()),
                max_abs_CFO_error_hz=float(np.max(abs(errors))),
                difference_from_matched_zero_ppm_RMS_hz=float(np.sqrt(np.mean(differences**2))),
                mean_margin=float(np.mean([r['margin'] for r in local_rows]))))
    write(OUT/'result.json',dict(rows=rows,summaries=summaries,source_sha256=sha(Path(__file__)),
        library_sha256=sha(library),build_receipt_sha256=sha(BUILD/'build-receipt.json'),
        modulation_time_rate_is_independent_of_carrier_phase=True,RF_CFO_truth_unchanged_across_ppm_controls=True,
        noise='none; CI16 quantization',upsampling=upsample,interpolation='periodic Fourier upsampling then fine-grid linear sampling',
        frozen_reference='three-frame discrete pilot template; not full actual transmitted data or analog filtering',
        oracle_resampling_uses_injected_modulation_rate_not_available_from_real_data=True,
        simulation_not_proof_of_actual_DS23_clock_or_estimator_bias=True))
    print('CFO sensitivity',summaries,flush=True)


if __name__=='__main__':run()
