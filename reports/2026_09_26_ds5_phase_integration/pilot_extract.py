"""Report-local disjoint-symbol pilot refinement with fractional timing."""
import numpy as np
from leo.analysis.starlink.templates import (OFDM_SYMBOL_DURATION_S, CYCLIC_PREFIX_DURATION_S,
    CONTROL_SYMBOL_ROLL, edge_frequencies_hz, qin_edge_pilot_frame, qin_edge_pilot_symbols)
from leo.analysis.starlink.adaptive_dual_rx_phase import pilot_symbol_reference_offsets_s
from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor

RATE=10_000_000.0
FRAME_RATE=750.0

def wrap(x): return np.angle(np.exp(1j*np.asarray(x)))

def fractional_shift(values, shift_samples):
    """Band-limited periodic shift; padding prevents frame-edge wrap entering support."""
    x=np.asarray(values,complex); pad=len(x); padded=np.pad(x,(pad,pad))
    frequency=np.fft.fftfreq(len(padded))
    shifted=np.fft.ifft(np.fft.fft(padded)*np.exp(-2j*np.pi*frequency*shift_samples))
    return shifted[pad:2*pad]

def _correlate(iq,templates,starts,cfo,midpoint,receiver,symbols):
    templates=np.asarray(templates)
    if templates.ndim==1: templates=np.broadcast_to(templates,(len(starts),len(templates)))
    begins=np.rint(symbols*RATE*OFDM_SYMBOL_DURATION_S).astype(int)
    ends=np.minimum(np.rint((symbols+1)*RATE*OFDM_SYMBOL_DURATION_S).astype(int),templates.shape[1])
    widths=ends-begins
    if np.any(widths<=0): raise ValueError('symbols must have nonempty template support')
    indices=begins[:,None]+np.arange(int(max(widths)))[None,:]
    mask=indices<ends[:,None]
    safe=np.minimum(indices,templates.shape[1]-1)
    absolute=starts[:,None,None]+safe[None,:,:]
    reference=templates[:,safe]*np.exp(2j*np.pi*cfo*(absolute-midpoint)/RATE)
    numerator=np.sum(np.conj(reference)*iq[absolute,receiver]*mask[None,:,:],axis=-1)
    denominator=np.sum(abs(templates[:,safe])**2*mask[None,:,:],axis=-1)
    return numerator/np.maximum(denominator,1e-30)

def _tone_channels(iq,edge,starts,cfo,midpoint,receiver,symbols,frame_fractions=None):
    begins=np.rint(symbols*RATE*OFDM_SYMBOL_DURATION_S).astype(int); ends=np.rint((symbols+1)*RATE*OFDM_SYMBOL_DURATION_S).astype(int)
    out=np.empty((len(starts),len(symbols),8),complex); frequencies=edge_frequencies_hz(edge); codes=qin_edge_pilot_symbols(edge)
    fractions=np.zeros(len(starts)) if frame_fractions is None else np.asarray(frame_fractions)
    for si,(begin,end) in enumerate(zip(begins,ends)):
      absolute=starts[:,None]+np.arange(begin,end)[None,:]
      corrected=iq[absolute,receiver]*np.exp(-2j*np.pi*cfo*(absolute-midpoint)/RATE)
      for fi,fraction in enumerate(fractions):
        local=(np.arange(begin,end)-fraction)/RATE-symbols[si]*OFDM_SYMBOL_DURATION_S-CYCLIC_PREFIX_DURATION_S
        design=np.exp(2j*np.pi*local[:,None]*frequencies[None,:])*codes[symbols[si]-2][None,:]/np.sqrt(8)
        out[fi,si]=np.linalg.lstsq(design,corrected[fi],rcond=None)[0]
    return out,frequencies

def _midpoint_phasors(coefficients,starts,offsets,frequency,midpoint):
    offsets=np.asarray(offsets);times=starts[:,None]+(offsets[None,:] if offsets.ndim==1 else offsets)*RATE
    rotated=coefficients*np.exp(-2j*np.pi*frequency*(times-midpoint)/RATE)
    return rotated

def extract_candidate(iq,edge,pair,start,stop,frequency_offsets_hz,train_symbols,eval_symbols):
    """Choose a common residual on training symbols and score held symbols unchanged."""
    receiver_ids=[int(r['receiver_id']) if 'receiver_id' in r else i for i,r in enumerate(pair)]
    if len(pair)!=2 or receiver_ids != [0,1]:
        raise ValueError('pair must be ordered receiver 0 then receiver 1')
    if set(map(int,train_symbols)) & set(map(int,eval_symbols)):
        raise ValueError('train and evaluation symbols must be disjoint')
    midpoint=.5*(start+stop); epoch=np.mean([float(r['integer_epoch_sample'])+float(r['fractional_epoch_offset_samples']) for r in pair])
    integer=round(epoch); fractional=epoch-integer
    exact_base=qin_edge_pilot_frame(RATE,edge);control_base=qin_edge_pilot_frame(RATE,edge,symbol_roll=CONTROL_SYMBOL_ROLL)
    nearest_index=round((midpoint-epoch)*FRAME_RATE/RATE)
    frame_float=np.array([epoch+(nearest_index+k)*RATE/FRAME_RATE for k in range(-2,3)])
    starts=np.rint(frame_float).astype(int);valid=(starts>=start)&(starts+len(exact_base)<=stop);frame_float=frame_float[valid];starts=starts[valid]
    frame_fractions=frame_float-starts
    templates=np.stack([fractional_shift(exact_base,value) for value in frame_fractions])
    controls_template=np.stack([fractional_shift(control_base,value) for value in frame_fractions])
    train=np.asarray(train_symbols,int); evaluation=np.asarray(eval_symbols,int)
    symbols=np.concatenate([train,evaluation]); offsets=np.stack([pilot_symbol_reference_offsets_s(RATE,OFDM_SYMBOL_DURATION_S,symbols,t) for t in templates])
    authority=float(pair[1]['tracking_absolute_baseband_cfo_hz'])-float(pair[0]['tracking_absolute_baseband_cfo_hz'])
    base=float(pair[0]['tracking_absolute_baseband_cfo_hz'])
    alternatives=[]
    for residual in map(float,frequency_offsets_hz):
      coefficients=np.stack([_correlate(iq,templates,starts,base+residual+rx*authority,midpoint,rx,symbols) for rx in range(2)])
      controls=np.stack([_correlate(iq,controls_template,starts,base+residual+rx*authority,midpoint,rx,symbols) for rx in range(2)])
      train_coeff=coefficients[:,:,:len(train)]
      train_control=controls[:,:,:len(train)]
      exact_rx=[float(np.sum(abs(np.sum(train_coeff[rx],axis=1))**2)) for rx in range(2)]
      control_rx=[float(np.sum(abs(np.sum(train_control[rx],axis=1))**2)) for rx in range(2)]
      exact_power=sum(exact_rx); control_power=sum(control_rx); ratios=[e/max(c,1e-30) for e,c in zip(exact_rx,control_rx)]
      # Exact power locates the frequency peak; the bounded ratio factor prevents
      # a nearly-zero control denominator from selecting a distant alternative.
      guarded_score=min(exact_rx)*min(r/(1+r) for r in ratios)
      rx_train=[complex(np.mean(coefficients[rx,:,:len(train)])) for rx in range(2)]
      rx_eval=[complex(np.mean(coefficients[rx,:,len(train):])) for rx in range(2)]
      alternatives.append(dict(residual_hz=residual,train_score=guarded_score,train_exact_power=exact_power,train_control_power=control_power,
                               train_ratio=min(ratios),train_ratio_per_rx=ratios,train_guarded_score=guarded_score,
                               receiver_train_complex_mean=[[float(z.real),float(z.imag)] for z in rx_train],
                               receiver_eval_complex_mean=[[float(z.real),float(z.imag)] for z in rx_eval],
                               coefficients=coefficients,controls=controls))
    selected=int(np.argmax([a['train_guarded_score'] for a in alternatives])); chosen=alternatives[selected]
    differential=chosen['coefficients'][1]*np.conj(chosen['coefficients'][0]); times=starts[:,None]+offsets*RATE
    train_values=differential[:,:len(train)].ravel();train_times=times[:,:len(train)].ravel();weights=np.maximum(abs(train_values),np.finfo(float).tiny)
    differential_hz,train_phase,_=fit_linear_phasor(train_values,train_times/RATE,weights,midpoint/RATE)
    corrected=_midpoint_phasors(differential,starts,offsets,differential_hz,midpoint)
    # Differential slope is fit on train only and propagated unchanged to held symbols.
    def summarize(part):
      z=np.mean(corrected[:,part]); return dict(phase_rad=float(np.angle(z)),resultant=float(abs(z)/max(np.mean(abs(corrected[:,part])),1e-30)))
    held_tones=[]; tone_bins=None
    for rx in range(2):
      tones,bins=_tone_channels(iq,edge,starts,base+chosen['residual_hz']+rx*authority,midpoint,rx,evaluation,frame_fractions)
      held_tones.append(tones); tone_bins=bins
    ranked=sorted([a['train_guarded_score'] for a in alternatives],reverse=True)
    receiver_train=[];receiver_eval=[]
    for rx in range(2):
      a=np.mean(chosen['coefficients'][rx,:,:len(train)]);b=np.mean(chosen['coefficients'][rx,:,len(train):])
      receiver_train.append([float(a.real),float(a.imag)]);receiver_eval.append([float(b.real),float(b.imag)])
    return dict(midpoint_sample=midpoint,fractional_epoch_samples=fractional,frame_starts=starts,
                frame_fractional_offsets_samples=frame_fractions,
                frame_symbol_offsets_samples=offsets*RATE,symbol_offsets_samples=np.mean(offsets,axis=0)*RATE,
                train_symbols=train,eval_symbols=evaluation,
                selected_index=selected,alternatives=alternatives,
                train_score_gap=float(ranked[0]-ranked[1]) if len(ranked)>1 else float('inf'),
                held_tone_channels=np.asarray(held_tones),tone_frequencies_hz=tone_bins,
                differential_frequency_hz=float(differential_hz),train_midpoint_phase_rad=float(wrap(train_phase)),
                receiver_train_complex_mean=receiver_train,receiver_eval_complex_mean=receiver_eval,
                train=summarize(slice(0,len(train))),eval=summarize(slice(len(train),len(symbols))))
