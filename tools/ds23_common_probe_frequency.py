"""Two carrier differences with a shared three-part receiver perturbation.

The reference part fixes a coordinate gauge, not the physical receiver LO.
Carrier differences are invariant to it. Channel gains and phases remain free
per original frame intersection. Timing/code parameters are conditioned inputs.
"""

import numpy as np


def part_design(part, reference=2):
    if part not in (0,1,2) or reference not in (0,1,2):
        raise ValueError('three temporal parts and one reference part required')
    design=np.zeros((2,4));design[:,:2]=np.eye(2)
    if part!=reference:design[:,2+[p for p in range(3) if p!=reference].index(part)]=1.
    return design


def rebase_parameters(parameters, old_reference, new_reference):
    x=np.asarray(parameters,float)
    if x.shape!=(4,) or not np.isfinite(x).all():raise ValueError('four finite carrier/common-frequency coordinates required')
    values=np.array([part_design(k,old_reference)@x for k in range(3)])
    base=values[new_reference];offsets=[float(np.mean(values[k]-base)) for k in range(3) if k!=new_reference]
    return np.r_[base,offsets]


class CommonProbeFrequency:
    def __init__(self, workspace, initial, reference=2):
        self.p=workspace;self.initial=np.asarray(initial,float).copy();self.reference=reference
        if self.initial.shape!=(6,) or not np.isfinite(self.initial).all():raise ValueError('six conditioned RF seed parameters required')
        self.all_segments=list(workspace.segments)
        self.parts=[[self.all_segments[k] for k in ix] for ix in np.array_split(np.arange(len(self.all_segments)),3)]
        self.designs=[part_design(k,reference) for k in range(3)]
        counts=np.array([sum(map(len,segments)) for segments in self.parts],float)
        self.support_mean_design=sum(w*d for w,d in zip(counts/counts.sum(),self.designs,strict=True))
        self.start=np.r_[self.initial[[0,3]],0.,0.]

    def statistics(self,parameters,parity=None,*,derivatives=True,prediction=False):
        x=np.asarray(parameters,float)
        if x.shape!=(4,) or not np.isfinite(x).all():raise ValueError('finite two-carrier/two-common-offset coordinates required')
        normal,rhs=np.zeros((4,4)),np.zeros(4);error=raw=0.;count=0;parts=[]
        held_error=held_raw=0.;held_count=0;original=self.p.segments
        try:
            for segments,design in zip(self.parts,self.designs,strict=True):
                local=self.initial.copy();local[[0,3]]=design@x;self.p.segments=segments
                result=self.p.statistics(local,parity,derivatives=derivatives,prediction=prediction)
                error+=result['squared_error'];raw+=result['raw_energy'];count+=result['samples']
                if derivatives:
                    selected=np.array([0,3]);normal+=design.T@result['normal'][np.ix_(selected,selected)]@design
                    rhs+=design.T@result['rhs'][selected]
                held_error+=result['heldout_squared_error'];held_raw+=result['heldout_raw_energy'];held_count+=result['heldout_samples']
                parts.append(dict(CFO_hz=local[[0,3]],squared_error=result['squared_error'],samples=result['samples']))
        finally:self.p.segments=original
        return dict(score=1-error/raw,squared_error=error,raw_energy=raw,samples=count,normal=normal,rhs=rhs,
            gradient_score=2*rhs/raw,parts=parts,heldout_squared_error=held_error,heldout_raw_energy=held_raw,heldout_samples=held_count)

    def optimize(self,parity=None,*,iterations=16,start=None):
        x=self.start.copy() if start is None else np.asarray(start,float).copy()
        lower=self.start-np.array([800.,800.,1000.,1000.]);upper=self.start+np.array([800.,800.,1000.,1000.])
        x=np.clip(x,lower,upper);current=self.statistics(x,parity);history=[dict(parameters=x.copy(),score=current['score'])];damping=1e-3
        for _ in range(iterations):
            normal=current['normal'];diagonal=np.maximum(np.diag(normal),current['raw_energy']*1e-14);improved=False
            for _ in range(5):
                step=np.linalg.solve(normal+damping*np.diag(diagonal),current['rhs'])
                step/=max(1.,float(np.max(abs(step)/.8)));proposed=np.clip(x+100*step,lower,upper)
                if np.max(abs(proposed-x))<.05:break
                candidate=self.statistics(proposed,parity)
                if candidate['score']>current['score']+1e-12:
                    x,current=proposed,candidate;damping=max(1e-8,damping/3);improved=True
                    history.append(dict(parameters=x.copy(),score=current['score']));break
                damping*=10
            if not improved:break
        noise=current['squared_error']/(current['samples']-17*len(self.all_segments)-2)
        covariance=noise/2*np.linalg.inv(current['normal'])*100**2;contrast=np.array([1.,-1.,0.,0.])
        return dict(parameters=x,reference_part=self.reference,history=history,score=current['score'],
            squared_error=current['squared_error'],samples=current['samples'],covariance_hz2=covariance,
            component_CFO_difference_hz=float(contrast@x),difference_sigma_proxy_hz=float(np.sqrt(contrast@covariance@contrast)),
            part_CFO_hz=np.array([d@x for d in self.designs]),
            uniform_support_mean_CFO_hz=self.support_mean_design@x,
            uniform_support_mean_covariance_hz2=self.support_mean_design@covariance@self.support_mean_design.T,
            uniform_support_mean_design=self.support_mean_design,
            boundary=bool(np.any(x<=lower+.5) or np.any(x>=upper-.5)),
            absolute_carrier_frequency_gauge_not_a_receiver_settling_assumption=True)
