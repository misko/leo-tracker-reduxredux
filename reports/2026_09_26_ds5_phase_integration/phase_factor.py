"""Pure optional circular evidence factor; no storage or catalogue dependencies."""
import numpy as np
from scipy.special import i0e,logsumexp

def log_i0(x):
    x=np.asarray(x,float)
    return np.log(i0e(x))+abs(x)

def phase_evidence(observed,predicted,kappa):
    """Log likelihood relative to uniform phase, marginalizing one shared beta.

    predicted has shape (..., observations). One call is one validated phase
    reference group. A free beta per observation intentionally adds zero evidence.
    kappa must be fixed from independent controls/training, not the held residual.
    """
    y=np.asarray(observed,float);p=np.asarray(predicted,float);k=np.asarray(kappa,float)
    if y.ndim!=1 or p.shape[-1]!=len(y) or k.shape!=y.shape:
        raise ValueError('phase arrays must share the observation dimension')
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(p)) or not np.all(np.isfinite(k)) or np.any(k<0):
        raise ValueError('finite phases and nonnegative concentrations required')
    vector=np.sum(k*np.exp(1j*(y-p)),axis=-1)
    return log_i0(abs(vector))-np.sum(log_i0(k))

def predictive_evidence(observed,predicted,kappa,train):
    """Conditional held evidence after integrating beta under training data."""
    y=np.asarray(observed);p=np.asarray(predicted);k=np.asarray(kappa);mask=np.asarray(train,bool)
    if mask.shape!=y.shape or not mask.any() or mask.all():raise ValueError('nonempty train and held groups required')
    return phase_evidence(y,p,k)-phase_evidence(y[mask],p[...,mask],k[mask])

def update_candidates(cfo_log_prior,phase_log_evidence,qualified=True):
    """Normalize an optional phase update over an existing candidate set.

    Phase inputs must describe independent or explicitly conditional support.
    Qualification is an upstream authority decision; missing phase is neutral.
    """
    prior=np.asarray(cfo_log_prior,float);factor=np.asarray(phase_log_evidence,float)
    if prior.ndim!=1 or factor.shape!=prior.shape or not np.all(np.isfinite(prior)) or not np.all(np.isfinite(factor)):
        raise ValueError('matching finite candidate vectors required')
    logits=prior+(factor if qualified else 0.)
    return np.exp(logits-logsumexp(logits))

def update_pair_candidates(left_cfo_log_prior,right_cfo_log_prior,pair_phase_log_evidence,qualified=True):
    """One DD factor couples two candidate identities; marginalize the joint once."""
    left=np.asarray(left_cfo_log_prior,float);right=np.asarray(right_cfo_log_prior,float)
    factor=np.asarray(pair_phase_log_evidence,float)
    if left.ndim!=1 or right.ndim!=1 or factor.shape!=(len(left),len(right)):
        raise ValueError('pair factor dimensions must match the two shortlists')
    if not all(np.all(np.isfinite(x)) for x in (left,right,factor)):
        raise ValueError('finite candidate evidence required')
    logits=left[:,None]+right[None,:]+(factor if qualified else 0.)
    joint=np.exp(logits-logsumexp(logits))
    return dict(joint=joint,left=joint.sum(axis=1),right=joint.sum(axis=0))
