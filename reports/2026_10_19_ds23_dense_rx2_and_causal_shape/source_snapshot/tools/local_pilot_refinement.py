"""Pure local known-pilot variable projection, with separate frame phases and DC."""

import numpy as np
from collections import OrderedDict
from functools import lru_cache
from probe_native_code_carrier import periodic_upsample,interpolate_periodic
from leo.analysis.starlink.templates import qin_edge_pilot_frame,CONTROL_SYMBOL_ROLL


@lru_cache(maxsize=8)
def pilot_wave(fs,edge,control=False):
    template=qin_edge_pilot_frame(fs,edge,symbol_roll=CONTROL_SYMBOL_ROLL if control else 0)
    period=fs/750;wave=np.zeros(round(fs/250),complex)
    for frame in range(3):
        start=round(frame*period);stop=min(start+len(template),len(wave));wave[start:stop]+=template[:stop-start]
    result=periodic_upsample(wave,32);result.flags.writeable=False
    return result


class PilotWorkspace:
    def __init__(self,samples,fs,edge,epoch,*,rotation_cache_bytes=32*1024*1024):
        if not isinstance(rotation_cache_bytes,int) or rotation_cache_bytes<0:raise ValueError('nonnegative integer rotation-cache budget required')
        self._rotation_budget=rotation_cache_bytes;self._rotation_cache=OrderedDict();self._rotation_cached_bytes=0
        self.y=np.asarray(samples,complex);self.fs=fs;self.epoch=float(epoch);self.period=fs/750
        self.n=np.arange(len(self.y));self.t=self.n/fs;self.mid=self.t.mean()
        self.frames=[];self.raw_energy=[];self.raw_sum=[]
        frame=0
        while epoch+(frame+1)*self.period+16<len(self.y):
            ix=np.flatnonzero((self.n>=epoch+frame*self.period+16)&(self.n<epoch+(frame+1)*self.period-16))
            y=self.y[ix];self.frames.append(ix);self.raw_sum.append(y.sum())
            self.raw_energy.append(float(np.sum(abs(y)**2)-abs(y.sum())**2/len(y)));frame+=1
        if len(self.frames)<4:raise ValueError('at least four complete pilot frames required')
        self.wave=pilot_wave(fs,edge);self.control=pilot_wave(fs,edge,True)

    def replica(self,offset=0.,ppm=0.,control=False):
        position=(self.n-self.epoch-offset)*(1+ppm*1e-6)*32
        return interpolate_periodic(self.control if control else self.wave,position)

    def evaluate(self,frequencies,offset=0.,ppm=0.,subset='all',control=False,details=False):
        f=np.atleast_1d(frequencies);r=self.replica(offset,ppm,control)
        key=(f.shape,f.dtype.str,f.tobytes());rotation=self._rotation_cache.get(key)
        if rotation is None:
            rotation=np.exp(-2j*np.pi*f[:,None]*(self.t-self.mid)[None])
            if rotation.nbytes<=self._rotation_budget:
                while self._rotation_cached_bytes+rotation.nbytes>self._rotation_budget:
                    _,evicted=self._rotation_cache.popitem(last=False);self._rotation_cached_bytes-=evicted.nbytes
                self._rotation_cache[key]=rotation;self._rotation_cached_bytes+=rotation.nbytes
        else:self._rotation_cache.move_to_end(key)
        explained=np.zeros(len(f));raw=0.;coefficient=[];energies=[];selected=[]
        for k,ix in enumerate(self.frames):
            if subset=='odd' and k%2==0 or subset=='even' and k%2==1:continue
            conjugate=r[ix].conj();mean=rotation[:,ix]@conjugate
            cross=rotation[:,ix]@(self.y[ix]*conjugate)-mean*self.raw_sum[k]/len(ix)
            energy=np.sum(abs(conjugate)**2)-abs(mean)**2/len(ix)
            explained+=abs(cross)**2/np.maximum(energy,1e-20);raw+=self.raw_energy[k]
            coefficient.append(cross/np.maximum(energy,1e-20));energies.append(energy);selected.append(k)
        score=explained/max(raw,1e-20)
        if not details:return score
        return dict(scores=score,coefficients=np.array(coefficient),energies=np.array(energies),frames=selected,
                    raw_energy=raw,explained=explained)

    def frequency_fit(self,center,offset=0.,ppm=0.,subset='all'):
        coarse=center+np.arange(-120,121,10);scores=self.evaluate(coarse,offset,ppm,subset)
        k=int(np.argmax(scores));fine=coarse[k]+np.arange(-10,11,1.);fine_scores=self.evaluate(fine,offset,ppm,subset)
        j=int(np.argmax(fine_scores));best=float(fine[j]);boundary=k in (0,len(coarse)-1) or j in (0,len(fine)-1)
        if 0<j<len(fine)-1:
            curve=fine_scores[j-1]-2*fine_scores[j]+fine_scores[j+1]
            if curve<0:best+=float(np.clip(.5*(fine_scores[j-1]-fine_scores[j+1])/curve,-.5,.5))
        score=float(self.evaluate([best],offset,ppm,subset)[0])
        return dict(CFO_hz=best,score=score,offset_samples=float(offset),modulation_ppm=float(ppm),
                    frequency_search_boundary=boundary,subset=subset)

    def joint_fit(self,center):
        best=None
        for ppm in np.arange(-40,41,10):
            for offset in (-.5,0.,.5):
                f=center+np.arange(-60,61,20);s=self.evaluate(f,offset,ppm);k=int(np.argmax(s))
                candidate=dict(CFO_hz=float(f[k]),score=float(s[k]),offset_samples=offset,modulation_ppm=float(ppm))
                if best is None or candidate['score']>best['score']:best=candidate
        seed=best.copy()
        for ppm in seed['modulation_ppm']+np.arange(-5,5.1,2.5):
            if abs(ppm)>40:continue
            for offset in seed['offset_samples']+np.arange(-.25,.251,.125):
                if abs(offset)>.75:continue
                f=seed['CFO_hz']+np.arange(-15,16,5);s=self.evaluate(f,offset,ppm);k=int(np.argmax(s))
                if float(s[k])>best['score']:best=dict(CFO_hz=float(f[k]),score=float(s[k]),offset_samples=float(offset),modulation_ppm=float(ppm))
        result=self.frequency_fit(best['CFO_hz'],best['offset_samples'],best['modulation_ppm'])
        result.update(code_rate_search_boundary=abs(result['modulation_ppm'])>=40,
            epoch_search_boundary=abs(result['offset_samples'])>=.75,
            control_score=float(self.evaluate([result['CFO_hz']],result['offset_samples'],result['modulation_ppm'],control=True)[0]))
        result['margin']=result['score']-result['control_score']
        return result

    def effective_time(self,result):
        r=self.replica(result['offset_samples'],result['modulation_ppm']);d=self.evaluate([result['CFO_hz']],result['offset_samples'],result['modulation_ppm'],subset=result.get('subset','all'),details=True)
        noise=max(0.,float(d['raw_energy']-d['explained'][0]))/sum(len(self.frames[k]) for k in d['frames'])
        cross=information=0.
        for number,k in enumerate(d['frames']):
            ix=self.frames[k];t=self.t[ix]-self.mid;w=abs(r[ix])**2;mu=np.sum(w*t)/w.sum()
            amplitude=max(0.,abs(d['coefficients'][number,0])**2-noise/max(d['energies'][number,0],1e-20))
            information+=amplitude*np.sum(w*(t-mu)**2)
            cross+=amplitude*np.sum(w*(t-mu)*.5*t*t)
        return float(self.mid+cross/information) if information>0 else None
