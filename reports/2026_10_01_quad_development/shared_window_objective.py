"""Shared-position objective using explicit full branch-score gradients."""
import numpy as np


class WindowObjective:
    def __init__(self,ports,columns,precision,radius_km=250.):
        self.ports=tuple(ports);self.columns=tuple(np.asarray(c) for c in columns)
        self.precision=np.asarray(precision,dtype=float);self.radius=radius_km
        if self.precision.ndim!=1 or len(self.precision)<2 or not np.all(np.isfinite(self.precision)) or np.any(self.precision<0):
            raise ValueError('invalid prior precision')
        if not self.ports or len(self.ports)!=len(self.columns):raise ValueError('aligned ports and column maps required')
        ids=[i for p in self.ports for i in p.observation_ids]
        if len(ids)!=len(set(ids)):raise ValueError('physical observations reused')
        for c in self.columns:
            if c.ndim!=1 or c.dtype.kind not in 'iu' or len(set(c.tolist()))!=len(c) or np.any(c<0) or np.any(c>=len(self.precision)):
                raise ValueError('invalid column map')
            if not np.array_equal(c[:2],[0,1]):raise ValueError('shared position must occupy first two columns')

    def evaluate(self,state,assigned=None,gradient=True):
        state=np.asarray(state,dtype=float)
        if state.shape!=self.precision.shape or not np.all(np.isfinite(state)):raise ValueError('invalid state')
        if np.linalg.norm(state[:2])>self.radius:raise ValueError('outside geographic prior')
        if assigned is not None and len(assigned)!=len(self.ports):raise ValueError('assignment length mismatch')
        value=float(.5*(self.precision*state)@state)
        g=self.precision*state if gradient else None;labels=[]
        for j,(p,c) in enumerate(zip(self.ports,self.columns,strict=True)):
            local=state[c]
            i=int(np.argmax(p.score_all(local))) if assigned is None else int(assigned[j])
            value-=p.score_selected(local,i);labels.append(i)
            if gradient:g[c]-=p.score_gradient(local,i)
        if not np.isfinite(value) or (gradient and not np.all(np.isfinite(g))):raise ValueError('nonfinite objective')
        return value,g,tuple(labels)
