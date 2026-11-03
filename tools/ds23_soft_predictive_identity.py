"""Variational satellite identities for predictive-only linear tracks.

Every Gaussian component integrates the SAME shared curved-data calibration
posterior, once. Only the predictive integral has a variational Gaussian latent;
none of its posterior updates replace the curved calibration coefficients.
"""

import numpy as np


def whiten_bias(raw,design,sigma,bias_sigma_hz=300.):
    """Symmetric whitening of diagonal noise plus one marginalized track bias."""
    y,u,s=np.asarray(raw,float),np.asarray(design,float),np.asarray(sigma,float)
    if (y.ndim!=1 or not len(y) or u.ndim!=2 or u.shape[0]!=len(y) or s.shape!=y.shape
            or not all(np.isfinite(v).all() for v in [y,u,s]) or np.any(s<=0)
            or not np.isfinite(bias_sigma_hz) or bias_sigma_hz<0):
        raise ValueError('finite matching observations/design and positive noise required')
    a=bias_sigma_hz/s;z=y/s;v=u/s[:,None];square=float(a@a)
    if square:
        factor=(1-1/np.sqrt(1+square))/square
        z=z-a*(factor*(a@z));v=v-a[:,None]*(factor*(a@v))[None,:]
    return dict(white_raw=z,white_design=v,gram=v.T@v,rhs=v.T@z,quadratic=float(z@z),
        normalization=float(len(y)*np.log(2*np.pi)+2*np.log(s).sum()+np.log1p(square)))


def identity_bound(pools,priors=None,initial=None,*,maximum_iterations=80,tolerance=1e-7):
    """Coordinate-ascent ELBO for q(common Gaussian) prod q(track identity).

    Pools contain sufficient statistics from ``whiten_bias``. Priors are fixed
    and normalized within each track. Fixed one-hot priors reproduce the exact
    joint Gaussian predictive likelihood, including all cross-track covariance.
    This is a variational bound, not an exact label marginal or identity proof.
    """
    if not pools or any(not p for p in pools) or maximum_iterations<1 or tolerance<=0:
        raise ValueError('nonempty identity pools and positive iteration controls required')
    counts=[len(p) for p in pools];ends=np.r_[0,np.cumsum(counts)]
    grams=np.stack([s['gram'] for p in pools for s in p]);rhs=np.stack([s['rhs'] for p in pools for s in p])
    constants=np.array([s['quadratic']+s['normalization'] for p in pools for s in p])
    width=rhs.shape[1]
    if grams.shape!=(len(rhs),width,width) or not all(np.isfinite(v).all() for v in [grams,rhs,constants]):
        raise ValueError('matching finite identity sufficient statistics required')
    prior=[np.ones(n)/n for n in counts] if priors is None else [np.asarray(v,float) for v in priors]
    if len(prior)!=len(pools) or any(v.shape!=(n,) or not np.isfinite(v).all() or np.any(v<0) or abs(v.sum()-1)>1e-12 for v,n in zip(prior,counts,strict=True)):
        raise ValueError('normalized nonnegative identity priors required')
    pi=np.concatenate(prior);rho=pi.copy() if initial is None else np.concatenate(initial).astype(float)
    if rho.shape!=pi.shape or np.any(rho<0) or np.any((pi==0)&(rho!=0)):
        raise ValueError('initial weights must respect identity prior support')
    for a,b in zip(ends[:-1],ends[1:],strict=True):
        if not np.isfinite(rho[a:b]).all() or abs(rho[a:b].sum()-1)>1e-12:
            raise ValueError('initial identity weights must sum to one')
    history=[];last_change=np.inf
    def gaussian(weights):
        precision=np.eye(width)+np.einsum('j,jab->ab',weights,grams,optimize=True)
        cross=weights@rhs;root=np.linalg.cholesky((precision+precision.T)/2)
        inverse=np.linalg.solve(root,np.eye(width));covariance=inverse.T@inverse
        mean=covariance@cross;logdet=float(2*np.log(np.diag(root)).sum())
        active=weights>0;kl=float(np.sum(weights[active]*np.log(weights[active]/pi[active])))
        objective=float(weights@constants-cross@mean+logdet+2*kl)
        return mean,covariance,logdet,kl,objective
    for iteration in range(maximum_iterations):
        mean,covariance,logdet,kl,objective=gaussian(rho);history.append(objective)
        expected=constants-2*(rhs@mean)+np.einsum('jab,ab->j',grams,covariance+np.outer(mean,mean),optimize=True)
        updated=np.zeros_like(rho)
        for a,b in zip(ends[:-1],ends[1:],strict=True):
            supported=pi[a:b]>0;logits=np.log(pi[a:b][supported])-.5*expected[a:b][supported]
            weights=np.exp(logits-logits.max());weights/=weights.sum()
            updated[a:b][supported]=weights
        last_change=float(np.max(abs(updated-rho)));rho=updated
        if last_change<=tolerance:break
    mean,covariance,logdet,kl,objective=gaussian(rho);history.append(objective)
    if any(b>a+1e-7 for a,b in zip(history[:-1],history[1:],strict=True)):
        raise ValueError('coordinate ascent decreased the variational evidence')
    residual=[];trace=0.;normalization=0.
    for weight,block in zip(rho,[s for p in pools for s in p],strict=True):
        residual.extend(np.sqrt(weight)*(block['white_raw']-block['white_design']@mean))
        trace+=weight*float(np.sum(block['gram']*covariance.T))
        normalization+=weight*block['normalization']
    gaussian_KL_trace=float(np.trace(covariance)+logdet-width)
    residual=np.r_[residual,mean,np.sqrt(max(0.,trace)),np.sqrt(max(0.,gaussian_KL_trace)),np.sqrt(max(0.,2*kl))]
    if abs(float(residual@residual)+normalization-objective)>2e-6:
        raise ValueError('variational residual does not reproduce the full normalized bound')
    return dict(objective=objective,normalization_constant=float(normalization),residual=residual,
        weights=[rho[a:b] for a,b in zip(ends[:-1],ends[1:],strict=True)],
        mean=mean,covariance=covariance,history=history,iterations=iteration+1,
        final_weight_change=last_change,converged=last_change<=tolerance,label_KL=kl)


def attach_soft_identities(p,entries,powers,*,fixed=False,maximum_iterations=80):
    """Offer all current curved-supported identities, preserving physical rows.

    Candidate aliases stay at the original measured track's alias. The curved
    catalogue search is unchanged; this is a conditional active-family identity
    experiment, not a fresh full-catalogue linear-track search.
    """
    if not entries:return p
    from ds23_predictive_linear import linear_geometry
    from ds23_height_problem import geometry_features
    labels=sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
        |{e['candidate_index'] for e in entries})
    offered=[];indices=[];original_indices=[]
    for entry in entries:
        choices=[entry['candidate_index']] if fixed else labels
        original_indices.append(choices.index(entry['candidate_index']))
        indices.append(choices)
        offered.extend([dict(entry,candidate_index=j,norad=int(p.scan.norads[j])) for j in choices])
    view,values,sigma,_,slices=linear_geometry(p,offered);curved=p.calculate
    boundaries=np.r_[0,np.cumsum([len(c) for c in indices])]
    def calculate(position):
        c=curved(position);group=p.noise_groups[p.keep]
        w=np.asarray(powers)[group]*c['noise_precision'][group]/p.point_noise[p.keep]**2
        features=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+features.T@(features*w[:,None])
        root=np.linalg.cholesky((gram+gram.T)/2);geometry=geometry_features(view,position,0.)
        raw=values-view.q*geometry['intercept']-geometry['features']@c['coefficient']
        uncertainty=np.linalg.solve(root,geometry['features'].T).T
        blocks=[whiten_bias(raw[sl],uncertainty[sl],sigma[sl]*np.sqrt(2)) for sl in slices]
        pools=[blocks[a:b] for a,b in zip(boundaries[:-1],boundaries[1:],strict=True)]
        initial=[np.eye(len(pool))[old] for pool,old in zip(pools,original_indices,strict=True)]
        result=identity_bound(pools,initial=initial,maximum_iterations=maximum_iterations)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['negative_twice_elbo']+=result['objective']
        c['normalization_constant']+=result['normalization_constant'];c['residual']=np.r_[c['residual'],result['residual']]
        selected=[a+int(np.argmax(weights)) for a,weights in zip(boundaries[:-1],result['weights'],strict=True)]
        selected_slices=[slices[k] for k in selected]
        c.update(linear_predictive_objective=result['objective'],soft_identity=result,
            linear_raw_prediction_residual_hz=np.concatenate([raw[sl] for sl in selected_slices]),
            linear_elevation=np.concatenate([geometry['elevation'][sl] for sl in selected_slices]),
            MAP_linear_entries=[offered[k] for k in selected],identity_candidates=indices,
            linear_calibration_coefficient_unchanged=True)
        return c
    counts=[len(p.scan.tracks[e['track_index']]['times']) for e in entries];ends=np.r_[0,np.cumsum(counts)]
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=entries
    p.linear_slices=[slice(a,b) for a,b in zip(ends[:-1],ends[1:],strict=True)]
    return p
