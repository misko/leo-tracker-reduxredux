"""Exact pure interpolation functions extracted from the recorded source authority."""
import numpy as np

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
