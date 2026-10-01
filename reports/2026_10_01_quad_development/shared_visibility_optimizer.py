"""Experimental limited-memory BFGS for the complete hard-association objective."""
import time
import numpy as np


def fit(model,initial,deadline,max_iterations=64,gradient_tolerance=1e-4,memory=8):
    x=np.asarray(initial,dtype=float).copy();precision=np.asarray(model.precision)
    scale=np.ones_like(x);positive=precision>0;scale[positive]=1/np.sqrt(precision[positive]);scale[:2]=10.
    if max_iterations<1 or memory<1 or gradient_tolerance<=0:raise ValueError('invalid optimization settings')
    value,g,labels=model.evaluate(x);history=[];values=[value];steps=[];reason='iteration_limit';converged=False
    for iteration in range(max_iterations):
        if time.monotonic()>=deadline:reason='wall_budget';break
        gy=g*scale
        if np.max(abs(gy))<gradient_tolerance:converged=True;reason='scaled_gradient';break
        q=gy.copy();alphas=[]
        for s,y,rho in reversed(history):
            a=rho*float(s@q);alphas.append(a);q-=a*y
        gamma=float(history[-1][0]@history[-1][1]/(history[-1][1]@history[-1][1])) if history else 1.
        direction=q*gamma
        for (s,y,rho),a in zip(history,reversed(alphas),strict=True):direction+=s*(a-rho*float(y@direction))
        direction=-direction
        if float(gy@direction)>=0:history=[];direction=-gy
        physical=scale*direction;norm=np.linalg.norm(physical[:2])
        if norm>5:direction*=5/norm;physical=scale*direction
        slope=float(gy@direction);accepted=None
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
        new_x,new_value,new_g,new_labels,alpha=accepted
        s=(new_x-x)/scale;y=(new_g-g)*scale;curvature=float(s@y)
        if new_labels!=labels:history=[]
        elif curvature>1e-12*np.linalg.norm(s)*np.linalg.norm(y):
            history.append((s,y,1/curvature));history=history[-memory:]
        x,value,g,labels=new_x,new_value,new_g,new_labels;values.append(value);steps.append(alpha)
    return dict(mean=x.tolist(),objectives=values,associations=list(labels),converged=converged,
        reason=reason,iterations=len(steps),step_sizes=steps,scaled_gradient_inf=float(np.max(abs(g*scale))),
        qualification='Experimental full-score L-BFGS; inverse-prior coordinate scaling,10km position scale,5km spatial step cap. Independent acceptance audit still required.')
