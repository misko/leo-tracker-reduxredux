"""Training-only phase-normalized response fit; existing held-band validation."""
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
from leo.analysis.starlink.broadband_alignment import BroadbandAlignmentModel
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from leo.storage import RecordingStore,PinnedLocalRoot

def normalize_response(left,right,frequency,initial_indexes,initial_transfer,eligible,iterations=3):
    """Fit H on training blocks after removing A-band block phase.

    No held-time IQ enters this routine. B groups never estimate block phase.
    The phase gauge is inherited from the initial response, not calibrated.
    """
    n=left.shape[1];kernel=np.ones(31)/31
    p0=np.convolve(np.sum(abs(left)**2,axis=0),kernel,'same')
    p1=np.convolve(np.sum(abs(right)**2,axis=0),kernel,'same')
    indexes=np.asarray(initial_indexes);h=np.asarray(initial_transfer);history=[]
    for iteration in range(iterations):
        guard=(indexes%64>=4)&(indexes%64<60);a=(indexes//64)%2==0;use=guard&a
        pred=left[:,indexes[use]]*h[use]
        phase=np.angle(np.sum(np.conj(pred)*right[:,indexes[use]],axis=1))
        corrected=right*np.exp(-1j*phase[:,None])
        cross=np.convolve(np.sum(np.conj(left)*corrected,axis=0),kernel,'same')
        rho=abs(cross)/np.sqrt(np.maximum(p0*p1,1e-30))
        null=np.convolve(np.sum(np.conj(left)*np.roll(corrected,7,axis=0),axis=0),kernel,'same')
        nullrho=abs(null)/np.sqrt(np.maximum(p0*p1,1e-30))
        threshold=max(.05,3*float(np.median(nullrho[eligible])))
        indexes=np.flatnonzero(eligible&(rho>=threshold))
        if len(indexes)<8:raise ValueError('No qualified shared response after phase normalization')
        h=cross[indexes]/np.maximum(p0[indexes],1e-30)
        history.append(dict(iteration=iteration,bin_count=len(indexes),null_gate=threshold,median_bin_coherence=float(np.median(rho[indexes]))))
    return indexes,h,history

def main():
    out=Path('/tmp/dynamic-channel-phase');out.mkdir(exist_ok=True)
    prior=json.loads((Path(__file__).parent.parent/'2026_09_22_postfix_phase_methods/results.json').read_text())
    d=prior['model'].copy();d['channel_transfer']=tuple(complex(v['real'],v['imag']) for v in d['channel_transfer']);d['frequency_hz']=tuple(d['frequency_hz']);m=BroadbandAlignmentModel(**d)
    fs=2500000;n=4096;store=RecordingStore.open_pinned(PinnedLocalRoot(Path('/srv/bulk/leo')))
    try:
        b=store.inspect(prior['selection']['session']);raw=store.reader(b,'stream-1',verify=True).read(round(31.8*fs),fs,receiver_ids=(0,1))
    finally:store.close()
    import hashlib
    assert hashlib.sha256(raw.tobytes()).hexdigest()==prior['selection']['raw_slice_sha256']
    iq=(raw[:,:,0].astype(float)+1j*raw[:,:,1].astype(float))/32768
    frequency=np.fft.fftshift(np.fft.fftfreq(n,1/fs));window=np.hanning(n);left=[];right=[]
    for start in range(0,len(iq)//2-n+1,n):
        t=(np.arange(start,start+n)-m.reference_sample)/fs
        rot=np.exp(-2j*np.pi*(m.relative_cfo_hz*t+.5*m.relative_cfo_rate_hz_s*t*t))
        left.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,0]*window)))
        right.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,1]*rot*window)))
    lo,hi=prior['common_filter_hz'];eligible=(frequency>lo+10000)&(frequency<hi-10000)
    idx=np.searchsorted(frequency,m.frequency_hz)
    indexes,h,history=normalize_response(np.array(left),np.array(right),frequency,idx,m.channel_transfer,eligible)
    updated=replace(m,frequency_hz=tuple(frequency[indexes]),channel_transfer=tuple(h))
    revised=frequency_held_out_tracking(iq,fs,updated)
    # Hold spectral support fixed to isolate response correction from mask expansion.
    original_indexes=idx;position=np.searchsorted(indexes,original_indexes);valid=position<len(indexes)
    valid[valid]&=indexes[position[valid]]==original_indexes[valid]
    common=original_indexes[valid];pos=position[valid]
    restricted=replace(m,frequency_hz=tuple(frequency[common]),channel_transfer=tuple(h[pos]))
    restricted_result=frequency_held_out_tracking(iq,fs,restricted)
    result=dict(history=history,original=prior['tracker'],revised=revised,restricted_support=restricted_result,
        original_bin_count=len(idx),revised_bin_count=len(indexes),common_bin_count=len(common),
        reference='Same frozen CFO/drift and phase gauge; only training response/mask updated',
        revised_frequency_hz=frequency[indexes].tolist(),revised_channel_transfer=[[float(z.real),float(z.imag)] for z in h])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['history','original_bin_count','revised_bin_count','common_bin_count']},indent=2))
    for label,value in [('old',prior['tracker']),('new',revised),('same_support',restricted_result)]:print(label,value['tracked'],value['wrong_time'],value['conditional_adjacent_pair_phase_error_95_rad'])

if __name__=='__main__':main()
