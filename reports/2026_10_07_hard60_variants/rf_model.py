"""Report-only constrained RF residuals and an augmented physical-vector fitter."""
from dataclasses import asdict
import time
import numpy as np
from scipy.linalg import null_space
from scipy.optimize import minimize, nnls
from bounded_fit import PositionFit


class RFObjective:
    def __init__(self, base, *, gauge=None, sigma_hz=50., limit_hz=150.):
        self.base = base
        self.base_size = base.size
        self.sigma_hz, self.limit_hz = float(sigma_hz), float(limit_hz)
        if self.sigma_hz <= 0 or self.limit_hz <= 0:
            raise ValueError('positive RF prior scale and bound required')
        if gauge is None:
            keys = np.column_stack([base.observations.receiver,
                                    np.rint(base.observations.rf_hz / 1e6).astype(int)])
            groups, inverse = np.unique(keys, axis=0, return_inverse=True)
            incidence = np.eye(len(groups))[inverse]
            # Remove both receiver means and the shared linear RF direction.
            constraints = base.design[:, [0, 2, 4]].T @ incidence
            q = null_space(constraints)
            self.groups, self.group_basis, self.incidence = groups, q, incidence
        else:
            self.groups, self.group_basis, self.incidence = gauge
        self.extra_design = self.incidence @ self.group_basis
        self.frozen_baseline = base.baseline.copy()

    def __getattr__(self, name):
        return getattr(self.base, name)

    @property
    def size(self):
        return self.base_size + self.group_basis.shape[1]

    def augment(self, vector):
        v = np.asarray(vector, float)
        if v.shape == (self.size,):
            return v.copy()
        assert v.shape == (self.base_size,)
        return np.r_[v, np.zeros(self.size-self.base_size)]

    def offsets(self, vector):
        return self.group_basis @ np.asarray(vector)[self.base_size:]

    def penalty(self, vector):
        z = np.asarray(vector)[self.base_size:]
        return float(.5 * (z @ z) / self.sigma_hz**2)

    def evaluate(self, vector):
        v = np.asarray(vector, float)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError('invalid augmented vector')
        z = v[self.base_size:]
        self.base.baseline = self.frozen_baseline + self.extra_design @ z
        value, gradient, terms = self.base.evaluate(v[:self.base_size])
        extra = self.extra_design.T @ terms.prediction_gradient.sum(axis=1) + z/self.sigma_hz**2
        return value + self.penalty(v), np.r_[gradient, extra], terms


class Domain:
    """Physical constraints with independent scaled first-order certification."""
    def __init__(self, objective, start, arm, center, radius, fixed_position=False):
        self.obj = objective
        self.start = objective.augment(start)
        self.n, self.p = objective.size, objective.base_size
        n, p = self.n, self.p
        self.scales = np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(p-7),
                            np.full(n-p,50.)]
        self.lo, self.hi = np.full(n,-np.inf), np.full(n,np.inf)
        self.lo[:2], self.hi[:2] = -objective.prior.radius_km, objective.prior.radius_km
        self.lo[[3,5]], self.hi[[3,5]] = -60.,60.
        self.lo[6:8], self.hi[6:8] = [-5000.,-10.],[5000.,10.]
        self.start[[3,5]] = np.clip(self.start[[3,5]],-60.,60.)
        self.start[6:8] = np.clip(self.start[6:8], self.lo[6:8], self.hi[6:8])
        if arm == 'zero-c':
            self.start[6] = self.lo[6] = self.hi[6] = 0.
        elif arm != 'fitted-c':
            raise ValueError('invalid c arm')
        if fixed_position:
            self.lo[:2] = self.hi[:2] = self.start[:2]
        self.disks = [(np.zeros(2),objective.prior.radius_km)]
        if center is not None:
            self.disks.append((np.asarray(center),radius))
        for origin,r in self.disks:
            delta=self.start[:2]-origin
            dist=np.linalg.norm(delta)
            if dist>r:
                if dist-r>1e-6:
                    raise ValueError('start outside disk')
                self.start[:2]=origin+delta*((r-1e-8)/dist)
        self.timing = np.zeros((len(objective.bank.numbers),n))
        self.timing[:,7],self.timing[:,8:p]=1.,objective.basis
        self.tmin = max(-20., objective.bank.nodes_s[0]-objective.observations.times_s.min())
        self.tmax = min(20., objective.bank.nodes_s[-1]-objective.observations.times_s.max())
        shifts = self.timing@self.start
        margin=min(1e-9,-self.tmin*1e-6,self.tmax*1e-6)
        factor=min(1.,(self.tmax-margin)/max(self.tmax-margin,float(shifts.max())),
                      (self.tmin+margin)/min(self.tmin+margin,float(shifts.min())))
        self.start[7:p]*=factor
        self.rf = np.zeros((len(objective.groups),n))
        self.rf[:,p:]=objective.group_basis
        self.free=np.flatnonzero(self.lo!=self.hi)

    def slacks_jac(self,v):
        shifts=self.timing@v
        offsets=self.rf@v
        rows=[]
        spatial=[]
        for origin,r in self.disks:
            delta=v[:2]-origin
            rows.append(r*r-delta@delta)
            row=np.zeros(self.n);row[:2]=-2*delta;spatial.append(row)
        slacks=np.r_[shifts-self.tmin,self.tmax-shifts,self.obj.limit_hz-offsets,
                     self.obj.limit_hz+offsets,rows]
        jac=np.vstack([self.timing,-self.timing,-self.rf,self.rf,*spatial])
        return slacks,jac

    def audit(self,v,gradient):
        slacks,jac=self.slacks_jac(v)
        f,s=self.free,self.scales
        normals=list((jac[slacks<=1e-6]*s)[:,f])
        for i in f:
            if (v[i]-self.lo[i])/s[i]<=1e-7:
                normals.append(np.eye(self.n)[i,f])
            if (self.hi[i]-v[i])/s[i]<=1e-7:
                normals.append(-np.eye(self.n)[i,f])
        residual=(gradient*s)[f]
        if normals:
            a=np.asarray(normals).T
            multipliers,_=nnls(a,residual,maxiter=100*max(1,a.shape[1]))
            residual=residual-a@multipliers
        stationarity=float(np.max(abs(residual),initial=0))
        feasible=bool(min(slacks)>=-1e-6 and np.all(v>=self.lo-1e-6) and np.all(v<=self.hi+1e-6))
        return dict(feasible=feasible,converged=feasible and stationarity<=.001,
                    stationarity=stationarity,
                    boundary=any(np.linalg.norm(v[:2]-o)>=r-1e-4 for o,r in self.disks),
                    slope_active_bounds=[i for i in (3,5) if abs(v[i])>=60.-2e-7],
                    rf_active_bounds=np.flatnonzero(abs(self.rf@v)>=self.obj.limit_hz-1e-6).tolist())


def fit_rf(objective,start,*,rf_arm='fitted-c',local_center=None,local_radius_km=None,
           maximum_seconds=20.,maximum_iterations=600,fixed_position=False):
    domain=Domain(objective,start,rf_arm,local_center,local_radius_km,fixed_position)
    free,scales=domain.free,domain.scales
    fixed=domain.start/scales
    low,high=(domain.lo/scales)[free],(domain.hi/scales)[free]
    def expand(z):
        v=fixed.copy();v[free]=z
        return v*scales
    def constraints(z):
        return domain.slacks_jac(expand(z))[0]
    def jacobian(z):
        return (domain.slacks_jac(expand(z))[1]*scales)[:,free]
    begun=time.monotonic();best=None;evaluations=0
    class Deadline(Exception):pass
    def evaluate(z):
        nonlocal best,evaluations
        if time.monotonic()-begun>=maximum_seconds:raise Deadline()
        v=expand(z);shifts=domain.timing@v
        violation=np.minimum(shifts-domain.tmin,0)+np.maximum(shifts-domain.tmax,0)
        if np.any(violation):
            return 1e12+1e8*float(violation@violation),2e8*(domain.timing*scales)[:,free].T@violation
        value,gradient,terms=objective.evaluate(v)
        evaluations+=1
        g=(gradient*scales)[free]
        if min(constraints(z))>=-1e-7 and np.all(z>=low-1e-9) and np.all(z<=high+1e-9):
            if best is None or value<best[0]-1e-9 or (abs(value-best[0])<=1e-9 and np.linalg.norm(g)<best[4]):
                best=(value,v.copy(),gradient.copy(),terms,float(np.linalg.norm(g)))
        return value,g
    reason='iteration-limit'
    try:
        r=minimize(evaluate,fixed[free],method='SLSQP',jac=True,bounds=list(zip(low,high)),
            constraints=dict(type='ineq',fun=constraints,jac=jacobian),
            options=dict(maxiter=maximum_iterations,ftol=1e-11))
        reason='optimizer-success' if r.success else f'optimizer-status-{r.status}'
    except Deadline:
        reason='time-budget'
    if best is None:raise TimeoutError('no feasible objective evaluation')
    value,v,g,terms,_=best
    audit=domain.audit(v,g)
    mass=float(terms.responsibilities.sum())
    rms=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)) if mass>1e-12 else None
    return PositionFit(v,float(value),rms,mass,audit['stationarity'],audit['converged'],
                       audit['boundary'],reason,evaluations,time.monotonic()-begun)
