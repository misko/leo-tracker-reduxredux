"""Direct same-window receiver coherence, independent of orbital models.

The frequency of y1*conj(y0) measures a differential carrier only if the two
streams share signal content. Coherence itself is not satellite identity or
direction of arrival; shared templates, interference and leakage need controls.
"""

import numpy as np


def circular_delta(value,reference,period):
    return (value-reference+period/2)%period-period/2


def cross_carrier(first,second,fs,lag_radius=2):
    x,y=np.asarray(first,complex),np.asarray(second,complex)
    if x.ndim!=1 or x.shape!=y.shape or len(x)<100 or not np.isfinite(x).all() or not np.isfinite(y).all() or fs<=0:
        raise ValueError("matching finite complex windows and positive rate required")
    if lag_radius<0 or lag_radius>8:raise ValueError("small bounded integer lag search required")
    best=None
    for lag in range(-lag_radius,lag_radius+1):
        a=x[max(0,-lag):len(x)-max(0,lag)].copy()
        b=y[max(0,lag):len(y)-max(0,-lag)].copy()
        a-=a.mean();b-=b.mean();n=len(a);window=np.hanning(n)
        denominator=float(np.sum(window*abs(a)**2)*np.sum(window*abs(b)**2))
        if denominator<=1e-30:continue
        product=window*b*a.conj();nfft=1<<int(np.ceil(np.log2(4*n)))
        transformed=np.fft.fft(product,n=nfft);power=abs(transformed)**2;k=int(np.argmax(power))
        left,right=power[(k-1)%nfft],power[(k+1)%nfft];curve=left-2*power[k]+right
        offset=float(np.clip(.5*(left-right)/curve,-.5,.5)) if curve<0 else 0.
        frequency=(k+offset)*fs/nfft
        if frequency>=fs/2:frequency-=fs
        coefficient=np.sum(product*np.exp(-2j*np.pi*frequency*np.arange(n)/fs))
        fraction=float(abs(coefficient)**2/denominator)
        result=dict(differential_CFO_hz=float(frequency),coherent_fraction=fraction,
            lag_samples=lag,relative_phase_rad=float(np.angle(coefficient)),samples=n)
        if best is None or fraction>best["coherent_fraction"]:best=result
    if best is None:raise ValueError("nonzero receiver energies required")
    return best
