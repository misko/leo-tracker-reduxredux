"""Optimizer-only candidate-weighted curvature arm; objective/stops unchanged."""
import time
import numpy as np
from weighted_candidate_curvature import curvature_direction


def fit(model,initial,deadline,max_iterations=64,gradient_tolerance=1e-4,direction_function=curvature_direction):
    x=np.asarray(initial,dtype=float).copy();precision=np.asarray(model.precision)
    scale=np.ones_like(x);positive=precision>0;scale[positive]=1/np.sqrt(precision[positive]);scale[:2]=10.
    if max_iterations<1 or gradient_tolerance<=0:raise ValueError('invalid settings')
    value,g,labels=model.evaluate(x);values=[value];steps=[];reason='iteration_limit';converged=False;decrements=[]
    for iteration in range(max_iterations):
        if time.monotonic()>=deadline:reason='wall_budget';break
        if np.max(abs(g*scale))<gradient_tolerance:converged=True;reason='scaled_gradient';break
        try:physical=direction_function(model,x,g)
        except (ValueError,np.linalg.LinAlgError):reason='curvature_failed';break
        slope=float(g@physical)
        if not np.isfinite(slope) or slope>=0:reason='non_descent';break
        decrements.append(-slope);norm=np.linalg.norm(physical[:2])
        if norm>5:physical*=5/norm;slope=float(g@physical)
        accepted=None
        for backtrack in range(24):
            if time.monotonic()>=deadline:reason='wall_budget';break
            alpha=2.**(-backtrack);trial=x+alpha*physical
            try:trial_value,_,trial_labels=model.evaluate(trial,gradient=False)
            except (ValueError,np.linalg.LinAlgError):continue
            if trial_value<=value+1e-4*alpha*slope:
                try:new_value,new_g,new_labels=model.evaluate(trial,trial_labels)
                except (ValueError,np.linalg.LinAlgError):continue
                accepted=(trial,new_value,new_g,new_labels,alpha);break
        if accepted is None:
            if reason!='wall_budget':reason='line_search_failed'
            break
        x,value,g,labels,alpha=accepted;values.append(value);steps.append(alpha)
    return dict(mean=x.tolist(),objectives=values,associations=list(labels),converged=converged,reason=reason,
        iterations=len(steps),step_sizes=steps,scaled_gradient_inf=float(np.max(abs(g*scale))),curvature_decrements=decrements,
        qualification='Exact marginal objective/gradient, all-candidate probability-weighted residual curvature direction; same Armijo/stopping rules. Not exact Hessian or calibrated covariance.')
