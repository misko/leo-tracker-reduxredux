"""Independent modulation-time warp and carrier injection, synthetic only."""
import numpy as np
from leo.analysis.starlink.fast_scan_fractional import fractional_take
from leo.analysis.starlink.templates import qin_edge_pilot_frame

FS=2500000
SAMPLES=50000
TRUE_EPOCH=500.25


def waveform(carrier_hz,warp_ppm):
    """Warp template time about frame epoch, then rotate carrier separately.

    This is not an ADC/propagation model. The nominal frame lattice is fixed;
    modulation alone stretches within each frame. No RF/Fs equality is imposed.
    """
    positions=np.arange(SAMPLES,dtype=float);period=FS/750.
    frame=np.floor((positions-TRUE_EPOCH)/period).astype(int)
    local=positions-TRUE_EPOCH-np.rint(frame*period)
    query=local/(1+warp_ppm*1e-6)
    template=np.asarray(qin_edge_pilot_frame(FS,'lower'),complex)
    valid=(frame>=0)&(query>=8)&(query<len(template)-9)
    baseband=np.zeros(SAMPLES,complex);baseband[valid]=fractional_take(template,query[valid])
    return baseband*np.exp(2j*np.pi*carrier_hz*positions/FS)


def cases():
    result=[dict(name=f'carrier{carrier:+d}_warp{warp:+d}',carrier_hz=carrier,warp_ppm=warp,conditioning_cfo_hz=float(carrier))
        for carrier in [-100000,0,100000] for warp in [-2000,0,2000]]
    result += [dict(name=f'conditioning{delta:+d}',carrier_hz=100000,warp_ppm=0,conditioning_cfo_hz=100000.+delta)
        for delta in [-2000,2000]]
    return result
