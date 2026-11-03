"""Report-only: double original nuisance bounds and timing prior widths.

No new individual timing cap. RX offsets remain unbounded. Position search,
200 Hz likelihood width, observations and candidate probabilities are unchanged.
"""
import time
import numpy as np
from curvature_position_profile import ROOT
from timing_model import DeadlineReached

COMMON_SIGMA=20.
INDIVIDUAL_SIGMA=2.
COMMON_BOUND=20.
INDIVIDUAL_BOUND=float('inf')


def loosen_bounds(original):
    bounds=list(original)
    for i in range(2,len(bounds)):
        bounds[i]=tuple(None if b is None else 2*b for b in bounds[i])
    return bounds


def additional_prior(vector,size):
    """Difference from existing sigma(common)=10, sigma(relative)=1 priors."""
    v=np.asarray(vector);g=np.zeros_like(v)
    a=1/COMMON_SIGMA**2-1/10.**2;b=1/INDIVIDUAL_SIGMA**2-1
    value=.5*a*v[6]**2+.5*b*float(v[7:size]@v[7:size])
    g[6]=a*v[6];g[7:size]=b*v[7:size]
    return value,g


def kkt_residual(vector,gradient,scale,bounds,A,tolerance=2e-6):
    """Scaled stationarity residual with nonnegative active-constraint multipliers."""
    from scipy.optimize import nnls
    v=np.asarray(vector);free=np.array([not(a is not None and b is not None and a==b) for a,b in bounds])
    normals=[]
    for i,(lo,hi) in enumerate(bounds):
        if not free[i]:continue
        unit=np.zeros(len(v));unit[i]=1
        if hi is not None and hi-v[i]<=tolerance:normals.append(unit.copy())
        if lo is not None and v[i]-lo<=tolerance:normals.append(-unit)
    delta=A@v
    for row,d in zip(A,delta):
        if INDIVIDUAL_BOUND-d<=tolerance:normals.append(row)
        if d+INDIVIDUAL_BOUND<=tolerance:normals.append(-row)
    g=(gradient*scale)[free]
    if normals:
        matrix=(np.asarray(normals)*scale)[:,free].T
        multipliers,_=nnls(matrix,-g,maxiter=1000)
        g=g+matrix@multipliers
    return float(np.max(np.abs(g),initial=0))


def polish_active_face(evaluate,vector,scale,bounds,A):
    """Observed-Hessian Newton steps tangent to active physical constraints."""
    from scipy.linalg import null_space
    current=vector.copy()
    for _ in range(3):
        value,g=evaluate(current);norm=kkt_residual(current,g,scale,bounds,A)
        if norm<=5e-4:break
        normals=[]
        for i,(lo,hi) in enumerate(bounds):
            if (lo is not None and current[i]-lo<2e-6) or (hi is not None and hi-current[i]<2e-6):
                unit=np.zeros(len(current));unit[i]=1.;normals.append(unit)
        for row,d in zip(A,A@current):
            if abs(d)>=INDIVIDUAL_BOUND-2e-6:normals.append(row)
        Z=null_space(np.asarray(normals)*scale) if normals else np.eye(len(current))
        if not Z.shape[1]:break
        h=1e-5;H=np.empty((Z.shape[1],Z.shape[1]))
        for j,z in enumerate(Z.T):
            plus=evaluate(current+h*z*scale)[1]*scale
            minus=evaluate(current-h*z*scale)[1]*scale
            H[:,j]=Z.T@(plus-minus)/(2*h)
        H=(H+H.T)/2
        if np.min(np.linalg.eigvalsh(H))<=0:break
        direction=(Z@np.linalg.solve(H,-Z.T@(g*scale)))*scale
        accepted=False
        for fraction in (1.,.5,.25,.125):
            trial=current+fraction*direction
            if np.max(np.abs(A@trial),initial=0)>INDIVIDUAL_BOUND+1e-8:continue
            if any((a is not None and x<a-1e-8) or (b is not None and x>b+1e-8) for x,(a,b) in zip(trial,bounds)):continue
            trial_value,trial_g=evaluate(trial)
            if trial_value<=value+1e-7 and kkt_residual(trial,trial_g,scale,bounds,A)<norm:
                current=trial;accepted=True;break
        if not accepted:break
    return current


def fit_loose(data,initial_fit,satellites,probability,center,*,fixed_position=None,start_position=None,budget_s=60.):
    from rf_calibration_diagnostic import CalibrationObjective
    from scipy.optimize import minimize
    started=time.monotonic()
    initial=np.asarray(initial_fit['parameters']).copy();satellites=np.asarray(satellites)
    common=float(np.mean(initial[6+satellites]))
    # The unchanged constructor validates the original +/-10 s initialization.
    # Use an admissible initialization, then restore the intended loose-model vector.
    initial[6+satellites]-=common-np.clip(common,-10.,10.)
    obj=CalibrationObjective(data,initial,satellites,False,budget_s)
    obj.likelihood.detection_probability=probability
    vector=obj.initial.copy();vector[obj.size:]=initial_fit['rf_coefficient_hz_per_ghz']
    vector[6]=np.clip(common,-COMMON_BOUND,COMMON_BOUND)
    vector[:2]=fixed_position if fixed_position is not None else (center if start_position is None else start_position)
    bounds=loosen_bounds(obj.bounds);bounds[:2]=[(c-5,c+5) for c in center]
    if fixed_position is not None:bounds[:2]=[(x,x) for x in fixed_position]
    A=np.zeros((0,len(vector)))  # Original model has no hard relative-timing cap.
    def feasible(v):
        return max(np.abs(A@v),default=0)<=INDIVIDUAL_BOUND+1e-7 and all(
            (a is None or x>=a-1e-7) and (b is None or x<=b+1e-7) for x,(a,b) in zip(v,bounds))
    best=None;calls=0
    def evaluate(v):
        nonlocal best,calls
        value,g=obj.evaluate(v);prior,pg=additional_prior(v,obj.size);value+=prior;g+=pg;calls+=1
        if feasible(v) and (best is None or value<best['objective']):best=dict(vector=v.copy(),objective=value)
        return value,g
    value,_=evaluate(vector)
    # Fisher diagonal scaling keeps initial constrained steps well-sized.
    H=obj.curvature(vector);H[6,6]+=1/COMMON_SIGMA**2-1/100.
    H[7:obj.size,7:obj.size]+=np.eye(obj.size-7)*(1/INDIVIDUAL_SIGMA**2-1)
    scale=np.clip(1/np.sqrt(np.maximum(np.diag(H),1e-10)),1e-5,1000.)
    scaled_bounds=[(None if a is None else a/s,None if b is None else b/s) for (a,b),s in zip(bounds,scale)]
    origin=value;terminal=[];messages=[]
    for _ in range(3):
        if time.monotonic()-started>=budget_s:break
        obj.base.deadline=started+budget_s
        def fun(x):
            value,g=evaluate(x*scale);return value-origin,g*scale
        try:
            res=minimize(fun,vector/scale,jac=True,method='SLSQP',bounds=scaled_bounds,
                         options=dict(maxiter=400,ftol=1e-10))
            terminal.append(res.x*scale);messages.append(str(res.message))
        except DeadlineReached:
            messages.append('time budget reached');break
        obj.base.deadline=float('inf')
        candidates=[best['vector'],terminal[-1]];checked=[]
        for v in candidates:
            if feasible(v):
                f,g=evaluate(v);checked.append((kkt_residual(v,g,obj.scale,bounds,A),f,v))
        minimum=min(c[1] for c in checked)
        norm,_,vector=min((c for c in checked if c[1]<=minimum+1e-7),key=lambda c:c[0])
        if norm<=1e-3:break
    obj.base.deadline=float('inf')
    candidates=[best['vector']]+[v for v in terminal if feasible(v)]
    checked=[]
    for v in candidates:
        f,g=evaluate(v);checked.append((kkt_residual(v,g,obj.scale,bounds,A),f,v.copy()))
    minimum=min(c[1] for c in checked)
    norm,_,vector=min((c for c in checked if c[1]<=minimum+1e-7),key=lambda c:c[0])
    if norm>1e-3:
        obj.base.deadline=time.monotonic()+12.
        try:vector=polish_active_face(evaluate,vector,obj.scale,bounds,A)
        except (DeadlineReached,np.linalg.LinAlgError):pass
        obj.base.deadline=float('inf')
    value,g=evaluate(vector);state=obj.base.state(vector[:obj.size]);delta=state['individual_shifts_s']
    norm=kkt_residual(vector,g,obj.scale,bounds,A)
    prior=.5*(vector[6]/COMMON_SIGMA)**2+.5*float(delta@delta)/INDIVIDUAL_SIGMA**2
    data_nll=-float(obj.likelihood.last_result['total_log_likelihood'])
    np.testing.assert_allclose(value,data_nll+prior,atol=1e-7,rtol=0)
    return dict(vector=vector,parameters=state['parameters'],rf_coefficient_hz_per_ghz=vector[obj.size:],
        objective=value,data_nll=data_nll,nuisance_prior_nll=prior,gradient=g,free_position_gradient=g[:2],
        success=bool(feasible(vector) and state['ephemeris_valid'] and norm<=1e-3),kkt_residual=norm,messages=messages,
        common_tau_s=float(vector[6]),individual_tau_s=delta,total_tau_s=state['total_shifts_s'],
        common_bound_active=bool(abs(vector[6])>=COMMON_BOUND-1e-5),
        individual_bound_active_count=0,
        rx_drift_bound_active_count=int(sum(abs(vector[i])>=100.-1e-5 for i in (3,5))),
        rf_bound_active_count=int(np.sum(np.abs(vector[obj.size:])>=10000.-1e-5)),
        ephemeris_valid=bool(state['ephemeris_valid']),
        satellite_support=obj.likelihood.last_result['satellite_support'],detection_probability=probability,
        elapsed_s=time.monotonic()-started,calls=calls)
