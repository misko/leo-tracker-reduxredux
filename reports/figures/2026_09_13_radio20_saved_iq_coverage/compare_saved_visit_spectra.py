"""Descriptive spectral/repetition comparison of hash-verified saved IQ; no RF."""
import hashlib
import json
from pathlib import Path

import numpy as np

BASE=Path(__file__).parent
RATE=2500000
FFT=4096


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024**2),b''): h.update(chunk)
    return h.hexdigest()


def lag_power(x,lag):
    a=x[:-lag];b=x[lag:]
    denominator=np.vdot(a,a).real*np.vdot(b,b).real
    return float(abs(np.vdot(a,b))**2/denominator) if denominator else 0.


def describe(path):
    iq=np.memmap(path,mode='r',dtype='<i2').reshape(-1,2)
    window=np.hanning(FFT);normalizer=np.sum(window**2)
    total=np.zeros(FFT);segments=0;energy=0.;lags={lag:[] for lag in (9000,10000,11000)}
    for start in range(0,len(iq)-131072+1,131072):
        raw=iq[start:start+131072].astype(np.float64)
        x=raw[:,0]+1j*raw[:,1]
        block=x.reshape(-1,FFT)*window
        total+=np.sum(abs(np.fft.fft(block,axis=1))**2,axis=0)
        energy+=float(np.sum(abs(block)**2));segments+=len(block)
        for lag in lags: lags[lag].append(lag_power(x,lag))
    assert segments and energy>0
    np.testing.assert_allclose(total.sum()/FFT,energy,rtol=2e-13)
    psd=np.fft.fftshift(total)/(segments*RATE*normalizer)
    frequency=np.fft.fftshift(np.fft.fftfreq(FFT,1/RATE))
    result=dict(complex_samples=len(iq),analyzed_samples=segments*FFT,
        omitted_tail_samples=len(iq)-segments*FFT,iq_sha256=digest(path),
        windowed_complex_power=float(psd.sum()*RATE/FFT),
        central_power_fraction={str(hz):float(psd[abs(frequency)<hz].sum()/psd.sum()) for hz in (250000,500000,1000000)},
        lag_power_quantiles={str(lag):np.quantile(values,[0,.5,.9,1]).tolist() for lag,values in lags.items()},
        lag_seconds={str(lag):lag/RATE for lag in lags},
        spectral_flatness=float(np.exp(np.mean(np.log(np.maximum(psd,np.finfo(float).tiny))))/np.mean(psd)))
    return result,frequency,psd


def main():
    # Check known invariants separately from the radio corpus.
    tone=np.exp(2j*np.pi*.03125*np.arange(131072))
    assert abs(lag_power(tone,10000)-1)<1e-12
    assert lag_power(np.zeros(131072,dtype=complex),10000)==0
    paths={
        '30_CH1':BASE/'two-frequency-visits30-v3/visit-0',
        '30_CH2':BASE/'two-frequency-visits30-v3/visit-1',
        '30_CH3':BASE/'two-frequency-visits30-clean-loss-v1/visit-0',
        '30_CH4':BASE/'two-frequency-visits30-clean-loss-v1/visit-1',
        '60_CH3':BASE/'two-frequency-visits60-v3/visit-0',
        '60_CH4':BASE/'two-frequency-visits60-v3/visit-1'}
    result=dict(scope='saved_IQ_descriptive_spectra_and_lag_power',new_rf_samples=0,
        sample_rate=RATE,fft_samples=FFT,frequency_bin_hz=RATE/FFT,
        calibrated_rf_power=False,ground_truth_signal_labels=False,acceptance_gates_changed=False,cases={})
    curves={}
    for label in [*paths,'positive','control']:
        if label in paths:
            root=paths[label];path=root/'iq.ci16'
            op=json.loads((root.parent/'operator.json').read_text())
            expected=op['artifacts'][root.name+'/iq.ci16']['sha256']
        else:
            path=BASE/f'paced-original-seed-input-v1/{label}.ci16'
            expected={'positive':'af991e03e69271c253d2fe6b5aeff110c9da5d5bd6ddda8c6850584f9e97b1c4',
                      'control':'5b945b575fbff519de733ded2418b2f82110458ff52237e2a3126d8d7a53d5b9'}[label]
        row,frequency,psd=describe(path);assert row['iq_sha256']==expected
        result['cases'][label]=row;curves[label]=psd
    result['source_sha256']=digest(Path(__file__))
    with (BASE/'saved-visit-spectra-v2.json').open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,7),constrained_layout=True)
    for label,psd in curves.items():
        axes[0].plot(frequency/1e6,10*np.log10(psd/psd.mean()),label=label,lw=1,alpha=.75)
    axes[0].set(xlabel='Frequency relative to tuned center (MHz)',ylabel='PSD / mean PSD (dB)',
                title='Saved 2.5 MS/s IQ: normalized spectral shape')
    axes[0].legend(ncol=4,fontsize=8);axes[0].grid(alpha=.2)
    for label,row in result['cases'].items():
        axes[1].plot([3.6,4,4.4],[row['lag_power_quantiles'][str(l)][1] for l in (9000,10000,11000)],'o-',label=label)
    axes[1].set(xlabel='Lag (ms); 4 ms is three nominal frames',ylabel='Median squared normalized lag correlation',yscale='log')
    axes[1].grid(alpha=.2)
    fig.savefig(BASE/'saved-visit-spectra-v2.svg')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
