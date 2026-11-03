"""RF-only carrier refinement with a complex channel per tone and frame.

Channel and DC are eliminated by variable projection. This research prototype
has no satellite, geographic or cross-scan input. Each frame keeps its own
phase; coherence across frames is not assumed.
"""

from collections import OrderedDict
from functools import lru_cache
import numpy as np

from local_pilot_refinement import PilotWorkspace
from probe_native_code_carrier import interpolate_periodic,periodic_upsample
from leo.analysis.starlink.templates import (OFDM_SYMBOL_DURATION_S,CYCLIC_PREFIX_DURATION_S,
    CONTROL_SYMBOL_ROLL,edge_frequencies_hz,qin_edge_pilot_symbols)


@lru_cache(maxsize=4)
def channel_waves(fs,edge,control=False):
    count=round(fs/750);t=np.arange(count)/fs
    index=np.floor(t/OFDM_SYMBOL_DURATION_S).astype(int)
    selected=(index>=2)&(index<302)
    local=t[selected]-index[selected]*OFDM_SYMBOL_DURATION_S
    symbols=qin_edge_pilot_symbols(edge,symbol_roll=CONTROL_SYMBOL_ROLL if control else 0)
    frame=np.zeros((count,8),complex)
    frame[selected]=symbols[index[selected]-2]*np.exp(2j*np.pi*(local[:,None]-CYCLIC_PREFIX_DURATION_S)*edge_frequencies_hz(edge)[None])/np.sqrt(8)
    wave=np.zeros((round(fs/250),8),complex)
    for k in range(3):
        start=round(k*fs/750);stop=min(start+count,len(wave));wave[start:stop]+=frame[:stop-start]
    result=tuple(periodic_upsample(wave[:,k],32) for k in range(8))
    for array in result: array.flags.writeable=False
    return result


class ChannelPilotWorkspace(PilotWorkspace):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._channel_cache=OrderedDict()
        # PilotWorkspace does not persist edge separately.
        self.edge=args[2] if len(args)>2 else kwargs['edge']

    def columns(self,offset=0.,ppm=0.,control=False):
        key=(float(offset),float(ppm),bool(control))
        if key not in self._channel_cache:
            position=(self.n-self.epoch-offset)*(1+ppm*1e-6)*32
            self._channel_cache[key]=np.column_stack([interpolate_periodic(w,position) for w in channel_waves(self.fs,self.edge,control)])
            while len(self._channel_cache)>2:self._channel_cache.popitem(last=False)
        self._channel_cache.move_to_end(key)
        return self._channel_cache[key]

    def indices(self,k,offset,ppm,subset):
        ix=self.frames[k]
        if subset=='odd' and k%2==0 or subset=='even' and k%2==1:return ix[:0]
        if subset in ('symbol_even','symbol_odd'):
            local=((self.n[ix]-self.epoch-offset)*(1+ppm*1e-6)/self.fs)%(1/750)
            symbols=np.floor(local/OFDM_SYMBOL_DURATION_S).astype(int)
            ix=ix[(symbols%2)==int(subset=='symbol_odd')]
        return ix

    def evaluate(self,frequencies,offset=0.,ppm=0.,subset='all',control=False,details=False,*,flat=False):
        if details:raise ValueError('channel prototype exposes profile scores only')
        f=np.atleast_1d(frequencies)
        if not np.isfinite(f).all():raise ValueError('finite carrier frequencies required')
        columns=self.columns(offset,ppm,control)
        if flat:columns=columns.sum(axis=1,keepdims=True)
        explained=np.zeros(len(f));raw=0.
        for k in range(len(self.frames)):
            ix=self.indices(k,offset,ppm,subset)
            if len(ix)<20:continue
            basis=columns[ix];y=self.y[ix];rotation=np.exp(-2j*np.pi*f[:,None]*(self.t[ix]-self.mid)[None])
            conjugate=basis.conj();mean=rotation@conjugate
            cross=rotation@(y[:,None]*conjugate)-mean*y.sum()/len(ix)
            gram=basis.conj().T@basis
            normals=gram[None]-mean[:,:,None]*mean[:,None,:].conj()/len(ix)
            # Numerical ridge only; <=1e-10 of the average column energy.
            ridge=max(1e-12,float(np.trace(gram).real/gram.shape[0])*1e-10)
            normals+=np.eye(gram.shape[0])[None]*ridge
            coefficient=np.linalg.solve(normals,cross[:,:,None])[:,:,0]
            explained+=np.sum(cross.conj()*coefficient,axis=1).real
            raw+=float(np.vdot(y,y).real-abs(y.sum())**2/len(ix))
        return explained/max(raw,1e-20)

    def frequency_fit(self,center,offset=0.,ppm=0.,subset='all',*,flat=False):
        coarse=center+np.arange(-120,121,10.)
        score=self.evaluate(coarse,offset,ppm,subset,flat=flat);k=int(np.argmax(score))
        fine=coarse[k]+np.arange(-10,11,1.)
        score=self.evaluate(fine,offset,ppm,subset,flat=flat);j=int(np.argmax(score));best=float(fine[j])
        if 0<j<len(fine)-1:
            curve=score[j-1]-2*score[j]+score[j+1]
            if curve<0:best+=float(np.clip(.5*(score[j-1]-score[j+1])/curve,-.5,.5))
        return dict(CFO_hz=best,score=float(self.evaluate([best],offset,ppm,subset,flat=flat)[0]),
            frequency_search_boundary=bool(k in (0,len(coarse)-1) or j in (0,len(fine)-1)),
            offset_samples=float(offset),modulation_ppm=float(ppm),subset=subset,flat=flat)

    def prediction_error(self,fit,train_subset,*,flat=False):
        if train_subset not in ('symbol_even','symbol_odd'):raise ValueError('disjoint symbol split required')
        other='symbol_odd' if train_subset=='symbol_even' else 'symbol_even'
        offset,ppm=fit['offset_samples'],fit['modulation_ppm']
        columns=self.columns(offset,ppm)
        if flat:columns=columns.sum(axis=1,keepdims=True)
        design=np.column_stack((columns*np.exp(2j*np.pi*fit['CFO_hz']*(self.t-self.mid))[:,None],np.ones(len(self.y))))
        error=energy=0.;counts=0
        for k in range(len(self.frames)):
            train=self.indices(k,offset,ppm,train_subset);test=self.indices(k,offset,ppm,other)
            coefficient=np.linalg.lstsq(design[train],self.y[train],rcond=1e-8)[0]
            residual=self.y[test]-design[test]@coefficient
            error+=float(np.vdot(residual,residual).real)
            y=self.y[test];energy+=float(np.vdot(y,y).real);counts+=len(test)
        return dict(heldout_squared_error=error,heldout_raw_energy=energy,heldout_samples=counts,
            heldout_normalized_error=error/max(energy,1e-20),channel_coefficients_fitted_on_other_symbols=True)
