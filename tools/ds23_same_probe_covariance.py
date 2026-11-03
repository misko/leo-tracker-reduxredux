"""RF-only multi-emitter residual comparison on identical receiver probes.

Probe identity may be shared across different paths; physical peak ownership
is exclusive. Curvature/epoch controls reject simple aliases and sidelobes
before inspecting matched residual covariance. No satellite or GPS input.
"""

import numpy as np
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def disjoint_peak_paths(models,maximum=32):
    used=set();selected=[]
    for model in models:
        indices=set(map(int,model['indices']))
        if indices&used:continue
        selected.append(model);used.update(indices)
        if len(selected)>=maximum:break
    return selected


def residual_pair(times,first,second,degree):
    t,a,b=[np.asarray(x,float) for x in (times,first,second)]
    if t.ndim!=1 or a.shape!=t.shape or b.shape!=t.shape or len(t)<=degree+2 or not 1<=degree<=4:
        raise ValueError('supported paired vectors and polynomial degree1..4 required')
    if not np.isfinite(np.r_[t,a,b]).all() or np.any(np.diff(t)<=0):raise ValueError('finite ordered paired measurements required')
    x=(t-t.mean())/max(float(np.ptp(t))/2,1.)
    design=np.polynomial.legendre.legvander(x,degree);q,_=np.linalg.qr(design)
    r1=a-q@(q.T@a);r2=b-q@(q.T@b);dof=len(t)-degree-1
    v1=float(r1@r1/dof);v2=float(r2@r2/dof);cov=float(r1@r2/dof)
    rho=cov/np.sqrt(max(v1*v2,1e-30))
    return dict(first_residual_hz=r1,second_residual_hz=r2,first_sigma_hz=np.sqrt(v1),second_sigma_hz=np.sqrt(v2),
        covariance_hz2=cov,correlation=rho,difference_sigma_hz=float(np.sqrt(np.sum((r1-r2)**2)/dof)),
        independent_difference_sigma_hz=float(np.sqrt(v1+v2)),degree=degree,degrees_of_freedom=dof)


def compare_paths(first,second,fs,*,seed=20261021):
    if first['lane']!=second['lane']:raise ValueError('same receiver/channel/RF lane required')
    one={p:k for k,p in enumerate(first['probes'])};two={p:k for k,p in enumerate(second['probes'])}
    common=sorted(set(one)&set(two),key=lambda p:first['times'][one[p]])
    if len(common)<16:return None
    a=np.array([one[p] for p in common]);b=np.array([two[p] for p in common])
    t=np.asarray(first['times'])[a]
    if np.ptp(t)<20:return None
    np.testing.assert_allclose(t,np.asarray(second['times'])[b],rtol=0,atol=1e-9)
    y1=np.asarray(first['values'])[a];y2=np.asarray(second['values'])[b]
    difference=y2-y1
    separation=abs((difference+PERIOD/2)%PERIOD-PERIOD/2)
    epochs=(np.asarray(first['epochs'])[a]-np.asarray(second['epochs'])[b]+fs/1500)%(fs/750)-fs/1500
    degree=max(first['degree'],second['degree'])
    stats=residual_pair(t,y1,y2,degree)
    affine=np.column_stack((np.ones(len(t)),t-t.mean()))
    delta_linear=difference-affine@np.linalg.lstsq(affine,difference,rcond=None)[0]
    delta_residual=stats['second_residual_hz']-stats['first_residual_hz']
    curvature_rms=float(np.sqrt(np.mean(delta_linear**2)))
    curvature_gain=float((np.sum(delta_linear**2)-np.sum(delta_residual**2))/(2*150.**2)-(degree-1)*np.log(len(t)))
    # A non-unit affine carrier relation can also be an instrumental image.
    relation=np.column_stack((np.ones(len(t)),y1-y1.mean()))
    relation_residual=y2-relation@np.linalg.lstsq(relation,y2,rcond=None)[0]
    relation_rms=float(np.sqrt(np.mean(relation_residual**2)))
    geometry_checks=dict(separated_CFO=bool(np.mean(separation>1500)>=.9),
        distinct_epoch=bool(np.median(abs(epochs))/fs>=2e-6 and np.mean(abs(epochs)/fs>=.8e-6)>=.8),
        distinct_active_curvature=curvature_rms>=250 and curvature_gain>=10,
        not_affine_frequency_image=relation_rms>=250)
    full_noise={}
    for name,r in [('first',stats['first_residual_hz']),('second',stats['second_residual_hz'])]:
        full_noise[name]={k:v[0] for k,v in batch_noise_screen(r[None],t).items()}
    split=[]
    for indices in (np.arange(0,len(t),2),np.arange(1,len(t),2)):
        split.append(residual_pair(t[indices],y1[indices],y2[indices],degree)['correlation'])
    rng=np.random.default_rng(seed);r1=stats['first_residual_hz'];r2=stats['second_residual_hz']
    controls=[float(r1@rng.permutation(r2)/max(np.linalg.norm(r1)*np.linalg.norm(r2),1e-30)) for _ in range(399)]
    rank=float((1+sum(v>=stats['correlation'] for v in controls))/400)
    checks=dict(geometry_checks,first_residual_noise=bool(full_noise['first']['noise_screen_pass']),
        second_residual_noise=bool(full_noise['second']['noise_screen_pass']),
        positive_covariance=stats['correlation']>=.6,
        stable_interleaved_covariance=bool(min(split)>=.4),matched_beats_shuffled=rank<=.01)
    return dict(first=first['key'],second=second['key'],lane=first['lane'],probes=common,time_s=t,
        first_values=y1,second_values=y2,relative_linear_residual_RMS_hz=curvature_rms,
        relative_curvature_BIC_gain=curvature_gain,affine_frequency_relation_RMS_hz=relation_rms,
        median_epoch_difference_us=float(np.median(abs(epochs))/fs*1e6),
        **stats,interleaved_residual_correlations=split,shuffled_correlation_rank=rank,
        shuffled_correlations=controls,residual_noise=full_noise,geometry_checks=geometry_checks,
        checks=checks,common_noise_candidate=all(checks.values()),
        selection_and_multiple_pair_testing_make_surrogate_rank_diagnostic_not_calibrated=True)
