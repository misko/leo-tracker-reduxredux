"""Continuous extension of the unchanged deployed GLRT64 residual score only."""
import numpy as np


def bounded_maximum(score,lower,upper):
    # Lean scalar golden-section solve: the historical runtime has NumPy only.
    ratio=(np.sqrt(5.)-1)/2
    a,b=lower,upper;x=b-ratio*(b-a);y=a+ratio*(b-a)
    sx,sy=score(x),score(y);calls=2
    while b-a>1e-5 and calls<64:
        if sx<sy:
            a=x;x=y;sx=sy;y=a+ratio*(b-a);sy=score(y)
        else:
            b=y;y=x;sy=sx;x=b-ratio*(b-a);sx=score(x)
        calls+=1
    return (float(x if sx>=sy else y),calls,bool(b-a<=1e-5))


def derivative_root(derivative,lower,upper):
    for _ in range(64):
        middle=(lower+upper)/2
        if derivative(middle)>0:lower=middle
        else:upper=middle
        if upper-lower<=1e-8:break
    return float((lower+upper)/2)


def direct_score(values, lags_s, frequency_hz, ceiling):
    phase=np.exp(-2j*np.pi*frequency_hz*lags_s)
    first=-2j*np.pi*lags_s
    s=np.sum(values*phase,axis=1)
    d=np.sum(values*phase*first,axis=1)
    dd=np.sum(values*phase*first**2,axis=1)
    return (float(np.sum(abs(s)**2)/ceiling),
            float(2*np.real(np.vdot(s,d))/ceiling),
            float(2*np.real(np.vdot(d,d)+np.vdot(s,dd))/ceiling))


def refine_correlations(values,times_s,original_bin_hz,grid_size=512):
    """Bounded autocorrelation maximum plus independent direct derivative-root check."""
    values=np.asarray(values,complex);times=np.asarray(times_s,float)
    if values.ndim!=2 or values.shape!=times.shape or values.shape[1]!=64 or not values.shape[0]:
        raise ValueError('nonempty frame by64 original correlations/times required')
    if not np.isfinite(values).all() or not np.isfinite(times).all():
        raise ValueError('finite original correlations/times required')
    lags=times-times[:,:1];step=float(np.median(np.diff(times,axis=1)))
    if step<=0 or np.max(abs(lags-np.arange(64)[None,:]*step))>1e-12:
        raise ValueError('nonuniform symbol geometry is outside this exact cache port')
    ceiling=float(np.sum(np.sum(abs(values),axis=1)**2))
    if ceiling<=0:raise ValueError('nonpositive original coherent ceiling')
    coefficients=np.sum([np.correlate(row,row,'full') for row in values],axis=0)/ceiling
    delays=np.arange(-63,64)*step
    def score(f):return float(np.real(coefficients@np.exp(-2j*np.pi*f*delays)))
    spacing=1/(grid_size*step);lower=float(original_bin_hz-spacing/2);upper=float(original_bin_hz+spacing/2)
    frequency,evaluations,success=bounded_maximum(score,lower,upper);value=score(frequency)
    derivative_lower=direct_score(values,lags,lower,ceiling)[1]
    derivative_upper=direct_score(values,lags,upper,ceiling)[1]
    reference=None;reference_error=None
    if derivative_lower>0 and derivative_upper<0:
        reference=derivative_root(lambda f:direct_score(values,lags,f,ceiling)[1],lower,upper)
    else:reference_error='no_positive_to_negative_derivative_bracket_in_original_cell'
    ds=direct_score(values,lags,frequency,ceiling)
    boundary=min(frequency-lower,upper-frequency)<=.05
    frequency_error=abs(frequency-reference) if reference is not None else None
    qualified=bool(success and not boundary and reference is not None and frequency_error<=.01 and
        abs(value-ds[0])<=1e-10 and ds[2]<0 and value>=score(original_bin_hz)-1e-12)
    return dict(original_bin_hz=float(original_bin_hz),grid_spacing_hz=spacing,bracket_hz=[lower,upper],
        residual_cfo_hz=frequency,score=value,original_bin_score=score(original_bin_hz),
        score_improvement=value-score(original_bin_hz),solver_success=success,
        solver_evaluations=evaluations,boundary=boundary,reference_root_hz=reference,
        reference_error=reference_error,reference_frequency_difference_hz=frequency_error,
        direct_score_difference=abs(value-ds[0]),direct_derivative=ds[1],direct_curvature=ds[2],
        numerically_qualified=qualified,global_peak_certified=False)


def refine(samples,sample_rate_hz,edge,acquired_cfo_hz,integer_epoch_sample,
           fractional_epoch_offset_samples,original_residual_cfo_hz,
           original_exact_score,original_control_score):
    """Return result and compact correlations. No storage, truth or candidate selection.

    Epoch, acquired CFO and symbol correlations remain exactly the original ones.
    Only the residual-frequency argmax is made continuous within its winning cell.
    """
    from leo.analysis.starlink.fast_scan_scores import _conditioned_correlation_workspace,_glrt_pair
    symbols=np.arange(2,66)
    workspace=_conditioned_correlation_workspace(np.asarray(samples,complex),sample_rate_hz,
        int(integer_epoch_sample),float(acquired_cfo_hz),edge=edge,selected_symbols=symbols,
        fractional_epoch_offset_samples=float(fractional_epoch_offset_samples))
    exact=workspace.select(symbols);control=workspace.select(symbols,control=True)
    old_exact,old_control=_glrt_pair(exact,control,size=512)
    closure=dict(exact_score_error=abs(old_exact[0]-original_exact_score),
        control_score_error=abs(old_control[0]-original_control_score),
        residual_frequency_error_hz=abs(old_exact[1]-original_residual_cfo_hz))
    passed=closure['exact_score_error']<=1e-10 and closure['control_score_error']<=1e-10 and closure['residual_frequency_error_hz']<=1e-7
    if not passed:raise ValueError('original512-bin score closure failed: '+str(closure))
    target=refine_correlations(exact.values,exact.times_s,old_exact[1])
    rolled=refine_correlations(control.values,control.times_s,old_control[1])
    result=dict(acquired_cfo_hz=float(acquired_cfo_hz),integer_epoch_sample=int(integer_epoch_sample),
        fractional_epoch_offset_samples=float(fractional_epoch_offset_samples),
        old_residual_cfo_hz=float(original_residual_cfo_hz),
        old_tracking_cfo_hz=float(acquired_cfo_hz+original_residual_cfo_hz),
        corrected_tracking_cfo_hz=float(acquired_cfo_hz+target['residual_cfo_hz']),
        old_exact_score=float(original_exact_score),old_control_score=float(original_control_score),
        corrected_exact_score=target['score'],corrected_control_score=rolled['score'],
        corrected_margin=target['score']-rolled['score'],original_grid_closure=closure,
        exact=target,control=rolled,frames=int(exact.values.shape[0]),symbols_per_frame=64,
        numerical_frequency_qualified=target['numerically_qualified'],
        numerical_margin_qualified=target['numerically_qualified'] and rolled['numerically_qualified'],
        original_candidate_epoch_and_gate_preserved=True,within_symbol_redemodulation_changed=False)
    return result,dict(exact_values=exact.values,control_values=control.values,times_s=exact.times_s)
