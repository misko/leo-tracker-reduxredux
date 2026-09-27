"""Rate-aware joint pilot regression with disjoint fit/quality/evaluation blocks."""
from functools import lru_cache
import numpy as np
from leo.analysis.starlink.templates import qin_edge_pilot_frame,CONTROL_SYMBOL_ROLL
from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor

SEED=20261003
def wrap(x):return np.angle(np.exp(1j*x))
def masks(n,rate):
    block=round(rate*20e-6);labels=np.arange((n+block-1)//block);order=np.random.default_rng(SEED).permutation(labels)
    assignment=np.empty(len(labels),int);assignment[order[:len(labels)//2]]=0;assignment[order[len(labels)//2:3*len(labels)//4]]=1;assignment[order[3*len(labels)//4:]]=2
    groups=np.arange(n)//block
    return [assignment[groups]==k for k in range(3)],groups

@lru_cache(maxsize=16)
def template(rate,edge,control):return qin_edge_pilot_frame(rate,edge,**({'symbol_roll':CONTROL_SYMBOL_ROLL} if control else {}))
def shift(x,fraction):
    pad=len(x);v=np.pad(x,(pad,pad));return np.fft.ifft(np.fft.fft(v)*np.exp(-2j*np.pi*np.fft.fftfreq(len(v))*fraction))[pad:2*pad]

@lru_cache(maxsize=256)
def shifted_template(rate,edge,control,fraction):
    value=shift(template(rate,edge,control),fraction);value.flags.writeable=False;return value

def design(rate,edge,epoch,cfo,start,n,offset=0.,control=False):
    midpoint=start+n/2;epoch+=offset;base=template(rate,edge,control);nearest=round((midpoint-epoch)*750/rate)
    frames=np.array([epoch+(nearest+k)*rate/750 for k in range(-3,4)]);integers=np.rint(frames).astype(int);valid=(integers>=start)&(integers+len(base)<=start+n)
    frames=frames[valid];integers=integers[valid]
    if len(frames)<3:raise ValueError('Insufficient complete pilot frames')
    mixer=np.exp(2j*np.pi*cfo*(np.arange(start,start+n)-midpoint)/rate);columns=[]
    for frame,s in zip(frames,integers):
        col=np.zeros(n,complex);col[s-start:s-start+len(base)]=shifted_template(rate,edge,control,float(frame-s));columns.append(col*mixer)
    return np.column_stack(columns)

def designs_for(visit,rate,start,n,offsets,include_controls=True):
    # A common differential acquisition seed gives simultaneous modes the same
    # receiver phase reference; retain raw GLRT offsets in the plan for audit.
    delta=float(np.median([m['seeds'][1]['cfo_hz']-m['seeds'][0]['cfo_hz'] for m in visit['modes']]))
    designs=[[],[]];controls=[[],[]]
    for m,offset in zip(visit['modes'],offsets):
        pair=m['seeds'];epochs=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair];epochs[1]+=round((epochs[0]-epochs[1])/(rate/750))*(rate/750);epoch=np.mean(epochs)
        for rx in (0,1):
            cfo=pair[0]['cfo_hz']+rx*delta
            designs[rx].append(design(rate,visit['edge'],epoch,cfo,start,n,offset))
            if include_controls:controls[rx].append(design(rate,visit['edge'],epoch,cfo,start,n,offset,True))
    return designs,controls

def fit_score(X,y,fit,quality,groups):
    coefficient=np.linalg.lstsq(X[fit],y[fit],rcond=None)[0];errors=abs(y[quality]-X[quality]@coefficient)**2
    return coefficient,np.array([errors[groups[quality]==g].sum() for g in np.unique(groups[quality])])
def contrast(a,b,energy):
    d=a-b;fraction=float(d.sum()/max(energy,1e-30));se=np.sqrt(len(d)*np.var(d,ddof=1));return dict(fraction=fraction,z=float(d.sum()/max(se,1e-30)) if abs(fraction)>1e-12 else 0.)

def extract(designs,controls,iq,rate):
    (fit,quality,evaluation),groups=masks(len(iq),rate);count=len(designs[0]);offset=np.cumsum([0]+[d.shape[1] for d in designs[0]]);coefficients=[];metrics=[];centers=[]
    for rx in (0,1):
        X=np.column_stack(designs[rx]);co,q=fit_score(X,iq[:,rx],fit,quality,groups);held=np.linalg.lstsq(X[evaluation],iq[evaluation,rx],rcond=None)[0];coefficients.append((co,held));energy=float(np.sum(abs(iq[quality,rx])**2))
        for mode in range(count):
            other=[d for j,d in enumerate(designs[rx]) if j!=mode];donor=np.column_stack(other) if other else np.empty((len(iq),0),complex)
            _,single=fit_score(donor,iq[:,rx],fit,quality,groups);_,control=fit_score(np.column_stack([donor,controls[rx][mode]]),iq[:,rx],fit,quality,groups)
            a=contrast(single,q,energy);b=contrast(control,q,energy);metrics.append(dict(receiver=rx,mode=mode,donor_improvement=a,control_improvement=b,qualified=bool(a['fraction']>1e-8 and a['z']>3 and b['z']>3)))
        if rx==0:
            power=abs(X)**2;times=np.arange(len(iq))/rate
            for mask in (fit,evaluation):centers.append((power[mask]*times[mask,None]).sum(axis=0)/np.maximum(power[mask].sum(axis=0),1e-30))
    modes=[];midpoint=len(iq)/(2*rate)
    for mode in range(count):
        take=slice(offset[mode],offset[mode+1]);tr=coefficients[1][0][take]*np.conj(coefficients[0][0][take]);he=coefficients[1][1][take]*np.conj(coefficients[0][1][take]);frequency,_,_=fit_linear_phasor(tr,centers[0][take],np.maximum(abs(tr),1e-30),midpoint)
        def stat(z,t):
            z=z*np.exp(-2j*np.pi*frequency*(t-midpoint));mean=np.mean(z);return dict(phase_rad=float(np.angle(mean)),R=float(abs(mean)/max(np.mean(abs(z)),1e-30)))
        modes.append(dict(mode=mode,qualified=all(r['qualified'] for r in metrics if r['mode']==mode),frequency_hz=float(frequency),train=stat(tr,centers[0][take]),evaluation=stat(he,centers[1][take])))
    return dict(modes=modes,metrics=metrics,both_qualified=count==2 and all(m['qualified'] for m in modes),sample_counts=[int(m.sum()) for m in (fit,quality,evaluation)])

def analyze(iq,visit,rate,start):
    offsets=[0.]*len(visit['modes']);fit=masks(len(iq),rate)[0][0]
    # One coordinate pass; every timing choice uses fit samples only.
    for mode in range(len(offsets)):
        trials=[]
        for trial in [-.5,-.25,0.,.25,.5]:
            current=offsets.copy();current[mode]=trial;d,_=designs_for(visit,rate,start,len(iq),current,include_controls=False);error=0.
            for rx in (0,1):
                X=np.column_stack(d[rx])[fit];y=iq[fit,rx];c=np.linalg.lstsq(X,y,rcond=None)[0];error+=float(np.sum(abs(y-X@c)**2))
            trials.append((error,trial))
        offsets[mode]=min(trials)[1]
    d,c=designs_for(visit,rate,start,len(iq),offsets);result=extract(d,c,iq,rate);result['timing_offsets_samples']=offsets;return result
