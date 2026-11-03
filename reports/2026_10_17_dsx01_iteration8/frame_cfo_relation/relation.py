"""Descriptive local phase rates; no orbital/clock inference or identity input."""
import numpy as np


def branches(times,phase,sample_rate_hz,*,maximum_gap_s=5.,guard_fraction=.25):
    """Conservative numerical branch guard, not physical transmitted-cycle proof."""
    times,phase=np.asarray(times,float),np.asarray(phase,float)
    if times.shape!=phase.shape or times.ndim!=1 or not len(times) or not np.isfinite(np.r_[times,phase]).all():
        raise ValueError('Aligned finite phase/time rows required')
    period=sample_rate_hz/750.;change=(np.diff(phase)+period/2)%period-period/2
    cuts=np.flatnonzero((np.diff(times)<=0)|(np.diff(times)>maximum_gap_s)|(abs(change)>guard_fraction*period))+1
    return np.split(np.arange(len(times)),cuts)


def phase_prediction(first_frame_s,phase_samples,cfo_support_s,sample_rate_hz):
    """Use even-index phases only; derivative is evaluated at CFO support centers."""
    first,phase,support=map(lambda x:np.asarray(x,float),(first_frame_s,phase_samples,cfo_support_s))
    if first.ndim!=1 or phase.shape!=first.shape or support.shape!=first.shape or len(first)<5:
        raise ValueError('At least5 aligned rows required')
    train=np.arange(len(first))%2==0;held=~train;period=sample_rate_hz/750.
    delta=(np.diff(phase[train])+period/2)%period-period/2
    if np.any(abs(delta)>period/4):raise ValueError('Alternating phase anchors fail quarter-period guard')
    unwrapped=np.unwrap(phase[train]*2*np.pi/period)*period/(2*np.pi)
    center=float(first[train].mean());degree=2 if train.sum()>=5 else 1
    coefficients=np.polynomial.polynomial.polyfit(first[train]-center,unwrapped,degree)
    fitted=np.polynomial.polynomial.polyval(first-center,coefficients)
    derivative=np.polynomial.polynomial.polyval(support-center,np.polynomial.polynomial.polyder(coefficients))
    x=derivative/sample_rate_hz;x_centered=x-x[train].mean()
    residual=(phase-fitted+period/2)%period-period/2
    return dict(train=train,held=held,degree=degree,phase_time_center_s=center,coefficients=coefficients,
        derivative_samples_s=derivative,x_centered=x_centered,
        phase_train_rms_samples=float(np.sqrt(np.mean(residual[train]**2))),
        phase_held_rms_samples=float(np.sqrt(np.mean(residual[held]**2))))


def compare_cfo(measured_hz,rf_hz,support_s,phase):
    """TRAIN centering, fixed +/-physical scales and a descriptive slope only."""
    measured,rf,support=map(lambda x:np.asarray(x,float),(measured_hz,rf_hz,support_s))
    train,held=phase['train'],phase['held'];y=measured/rf;y=y-y[train].mean();x=phase['x_centered']
    dt=support-support[train].mean();xx=float(x[train]@x[train])
    beta=float(x[train]@y[train]/xx) if xx>1e-24 else None
    time_slope=float(dt[train]@y[train]/(dt[train]@dt[train]))
    return dict(y_centered=y,x_centered=x,train=train,held=held,beta=beta,
        time_only_prediction=time_slope*dt,
        descriptive_prediction=np.zeros(len(y)) if beta is None else beta*x)
