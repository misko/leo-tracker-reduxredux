"""Audit phase wrapping and window artifacts using the same verified raw IQ."""
import json
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve, firwin, savgol_filter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from leo.storage import RecordingStore,PinnedLocalRoot

OUT=Path('/tmp/postfix-phase-diagnosis')
def wrap(x):return np.angle(np.exp(1j*x))
def main():
    OUT.mkdir(exist_ok=True)
    src=Path(__file__).parent.parent/'2026_09_22_postfix_phase_methods/results.json'
    doc=json.loads(src.read_text());m=doc['model'];fs=2500000;start=31.8
    store=RecordingStore.open_pinned(PinnedLocalRoot(Path('/srv/bulk/leo')))
    try:
        b=store.inspect(doc['selection']['session']);raw=store.reader(b,'stream-1',verify=True).read(round(start*fs),fs,receiver_ids=(0,1))
    finally:store.close()
    import hashlib
    assert hashlib.sha256(raw.tobytes()).hexdigest()==doc['selection']['raw_slice_sha256']
    iq=(raw[:,:,0].astype(float)+1j*raw[:,:,1].astype(float))/32768
    dt=(np.arange(fs)-m['reference_sample'])/fs
    iq[:,1]*=np.exp(-2j*np.pi*(m['relative_cfo_hz']*dt+.5*m['relative_cfo_rate_hz_s']*dt**2))
    taps=np.sinc(np.arange(-32,33)+m['fractional_delay_samples'])*np.hanning(65);taps/=taps.sum()
    iq[:,1]=fftconvolve(iq[:,1],taps,mode='same')
    lo,hi=doc['common_filter_hz'];filt=firwin(513,(hi-lo)/2,fs=fs)*np.exp(2j*np.pi*(hi+lo)/2*(np.arange(513)-256)/fs)
    iq=np.column_stack([fftconvolve(iq[:,rx],filt,mode='same') for rx in (0,1)])
    product=np.conj(iq[:,0])*iq[:,1]
    sums=np.r_[0,np.cumsum(product)];pows=[np.r_[0,np.cumsum(abs(iq[:,rx])**2)] for rx in (0,1)]
    series={}
    for width in [500,1250,2500,5000]:
        centers=np.arange(10000,fs-10000,500);left=centers-width//2;right=left+width
        z=sums[right]-sums[left];rho=abs(z)/np.sqrt((pows[0][right]-pows[0][left])*(pows[1][right]-pows[1][left]))
        phase=np.angle(z);unwrapped=np.unwrap(phase);rate=savgol_filter(unwrapped,51,2,deriv=1,delta=500/fs)/(2*np.pi)
        series[str(width)]=dict(time_s=(start+(left+(width-1)/2)/fs).tolist(),phase_rad=phase.tolist(),unwrapped_rad=unwrapped.tolist(),frequency_hz=rate.tolist(),coherence=rho.tolist())
    fine=series['1250'];t=np.array(fine['time_s']);u=np.array(fine['unwrapped_rad']);rate=np.array(fine['frequency_hz'])
    stats=[]
    for lo,hi in [(31.804,32.3),(32.3,32.45),(32.48,32.65),(32.65,32.796)]:
        q=(t>=lo)&(t<hi);idx=np.flatnonzero(q)
        stats.append(dict(interval_s=[lo,hi],median_residual_frequency_hz=float(np.median(rate[q])),frequency_p05_p95_hz=np.percentile(rate[q],[5,95]).tolist(),phase_turns=float((u[idx[-1]]-u[idx[0]])/(2*np.pi)),median_coherence=float(np.median(np.array(fine['coherence'])[q]))))
    comparisons=[]
    for width in ['500','2500','5000']:
        s=series[width];delta=wrap(np.array(s['phase_rad'])-np.interp(s['time_s'],t,u));q=(t>=32.48)&(t<32.65)
        comparisons.append(dict(samples=int(width),late_circular_rms_difference_deg=float(np.degrees(np.sqrt(np.mean(delta[q]**2))))))
    old=doc['windows'];old_t=np.array([r['time_s'] for r in old]);old_p=np.radians([r['phase_deg'] for r in old]);delta=wrap(old_p-np.interp(old_t,t,u))
    tracking=doc['tracker']['rows'];tt=np.array([start+r['center_sample']/fs for r in tracking]);bd=np.array([r['held_band_residual_phase_rad'] for r in tracking])
    agreement=[]
    for lo,hi in [(32.3,32.45),(32.48,32.65),(32.65,32.8)]:
        q=(tt>=lo)&(tt<hi);z=np.mean(np.exp(1j*bd[q]));agreement.append(dict(interval_s=[lo,hi],a_b_residual_mean_deg=float(np.degrees(np.angle(z))),a_b_residual_resultant=float(abs(z)),a_b_residual_circular_rms_deg=float(np.degrees(np.sqrt(np.mean(wrap(bd[q])**2))))))
    result=dict(source_raw_sha256=doc['selection']['raw_slice_sha256'],series=series,interval_statistics=stats,window_comparison=comparisons,original_vs_fine_circular_rms_deg=float(np.degrees(np.sqrt(np.mean(delta**2)))),frequency_band_agreement=agreement,frequency_method='0.5 ms complex cross-product windows every 0.2 ms; unwrap then descriptive 10.2 ms local quadratic derivative; no claim of absolute cycle ambiguity resolution')
    (OUT/'diagnosis.json').write_text(json.dumps(result,indent=2)+'\n')
    fig,ax=plt.subplots(4,1,figsize=(13,12),sharex=True,constrained_layout=True)
    ax[0].scatter(old_t,np.degrees(old_p),s=3,c='gray',label='Original: 2 ms windows / 1 ms stride')
    ax[0].plot(t,np.degrees(np.array(fine['phase_rad'])),'.',ms=1,color='tab:blue',label='Check: 0.5 ms windows / 0.2 ms stride')
    ax[0].set_ylabel('Wrapped residual phase (°)')
    ax[1].plot(t,(u-u[0])/(2*np.pi),label='Locally unwrapped, relative to first point');ax[1].set_ylabel('Accumulated residual turns')
    ax[2].plot(t,rate,label='Local residual frequency (10.2 ms smoothing)');ax[2].axhline(0,c='gray',lw=.6);ax[2].set_ylabel('Residual frequency (Hz)')
    for width in ['500','1250','5000']:
        s=series[width];ax[3].plot(s['time_s'],s['coherence'],lw=.5,alpha=.6,label=f'{int(width)/fs*1000:g} ms windows')
    ax[3].set_ylabel('Amplitude coherence');ax[3].set_xlabel('Elapsed device sample time (s)')
    for a in ax:
        a.axvline(32.3,c='gray',ls='--',label='Training split');a.axvspan(32.48,32.65,color='orange',alpha=.12);a.grid(alpha=.2);a.legend(fontsize=8,loc='upper left');a.set_xlim(31.8,32.8)
    fig.suptitle('The right-hand pattern is rapid coherent phase winding, not a cloud of random phase\nSame post-fix .21 IQ; shorter-window and faster-stride check')
    fig.savefig(OUT/'wrapped-unwrapped-frequency.png',dpi=160)
    for a in ax:a.set_xlim(32.5,32.54)
    fig.savefig(OUT/'rapid-phase-40ms-zoom.png',dpi=160)
    print(json.dumps({k:v for k,v in result.items() if k!='series'},indent=2))
if __name__=='__main__':main()
