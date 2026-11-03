"""Residual-waveform coherence after deterministic pilot removal.

Permutations preserve each receiver's frame structure and repeat the same
frequency/alias search. Correlation is evidence of a shared residual waveform;
absence is not proof of different emitters (polarization and SNR may differ).
"""

import numpy as np


def derangements(frames, count=127, seed=2026102013):
    if frames < 4 or count < 1:
        raise ValueError('supported frames and positive control count required')
    rng=np.random.default_rng(seed)
    indices=np.arange(frames)
    selected=[]
    seen=set()
    for _ in range(count*1000):
        proposed=rng.permutation(frames)
        key=tuple(proposed)
        if np.any(proposed==indices) or key in seen:continue
        selected.append(proposed);seen.add(key)
        if len(selected)==count:break
    if len(selected)!=count:raise ValueError('not enough distinct shuffled-frame controls')
    return np.asarray(selected)


def remove_pilot(frames, templates):
    y=np.asarray(frames,complex)
    template=np.broadcast_to(np.asarray(templates,complex),y.shape)
    if y.ndim!=2 or len(y)<4 or not np.isfinite(y).all() or not np.isfinite(template).all():
        raise ValueError('finite matching frame/pilot matrices required')
    centered=y-y.mean(axis=1,keepdims=True)
    t=template-template.mean(axis=1,keepdims=True)
    energy=np.sum(abs(t)**2,axis=1)
    if np.any(energy<=1e-20):raise ValueError('nonzero pilot required')
    gain=np.sum(t.conj()*centered,axis=1)/energy
    if np.any(abs(gain)<=1e-20):raise ValueError('nonzero measured pilot gain required')
    residual=(centered-gain[:,None]*t)/gain[:,None]
    # Remove repeatable filter mismatch, linear timing/rate error and the
    # three-frame sampling cycle (2.5 MHz / 750 Hz = 10000/3 samples).
    # Otherwise two independent emitters carrying the same pilot could share
    # a receiver-clock/template distortion and appear spuriously coherent.
    k=np.arange(len(y))
    design=np.column_stack((np.ones(len(y)),(k-k.mean())/len(y),
                            np.sin(2*np.pi*k/3),np.cos(2*np.pi*k/3)))
    residual-=design@np.linalg.lstsq(design,residual,rcond=None)[0]
    scale=np.sqrt(np.mean(abs(residual)**2,axis=1))
    if np.any(scale<=1e-20):raise ValueError('residual waveform has no energy')
    residual/=scale[:,None]
    fraction=abs(gain)**2*energy/np.maximum(np.sum(abs(centered)**2,axis=1),1e-20)
    return residual,dict(pilot_energy_fraction=fraction,gain=gain,
                         removed_interframe_rank=int(np.linalg.matrix_rank(design)))


def coherence(first,second,permutations):
    a,b=np.asarray(first,complex),np.asarray(second,complex)
    orders=np.asarray(permutations)
    if a.ndim!=2 or a.shape!=b.shape or orders.ndim!=2 or orders.shape[1]!=len(a):
        raise ValueError('matching frame matrices and shuffled frame indices required')
    cross=a.conj()@b.T
    norm=float(np.sum(abs(a)**2)*np.sum(abs(b)**2))
    if norm<=0:raise ValueError('nonzero waveform energies required')
    diagonal=np.trace(cross)
    null=np.abs(cross[np.arange(len(a))[None,:],orders].sum(axis=1))**2/norm
    return float(abs(diagonal)**2/norm),null


def frame_positions(length,fs,epoch,*,delay_samples=0.):
    if fs<=0 or not np.isfinite([fs,epoch,delay_samples]).all():
        raise ValueError('finite sample clock and epoch required')
    period=fs/750.
    n=np.arange(16,int(np.floor(period))-16)
    frames=[]
    k=0
    while epoch+(k+1)*period+16+abs(delay_samples)<length:
        frames.append(epoch+k*period+n+delay_samples)
        k+=1
    result=np.asarray(frames)
    if len(result)<6 or result.min()<0 or result.max()>length-1:
        raise ValueError('at least six complete non-extrapolated frames required')
    return result


def carrier_spectrum(first,second,times):
    a,b,t=np.asarray(first,complex),np.asarray(second,complex),np.asarray(times,float)
    if a.ndim!=2 or a.shape!=b.shape or t.shape!=a.shape or not all(np.isfinite(x).all() for x in (a,b,t)):
        raise ValueError('finite matching frame waveforms and sample times required')
    product=a.conj()*b
    clock=t-t.mean()
    grid=np.arange(-750.,750.1,5.)
    amplitudes=np.empty((len(grid),len(a)),complex)
    for k,frequency in enumerate(grid):
        amplitudes[k]=np.sum(product*np.exp(-2j*np.pi*frequency*clock),axis=1)
    total=amplitudes.sum(axis=1)
    energy=float(np.sum(abs(a)**2)*np.sum(abs(b)**2))
    if energy<=0:raise ValueError('positive waveform energies required')
    scores=abs(total)**2/energy
    index=int(np.argmax(scores))
    deletions=np.argmax(abs(total[:,None]-amplitudes)**2,axis=0)
    return dict(additional_frequency_hz=float(grid[index]),coherence=float(scores[index]),
        leave_frame_out_frequency_hz=grid[deletions],leave_frame_out_range_hz=float(np.ptp(grid[deletions])),
        frequency_grid_hz=grid,coherence_grid=scores)
