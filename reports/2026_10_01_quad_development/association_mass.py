"""Stable conditional branch-mass diagnostics, not posterior calibration."""
import numpy as np


def summarize_scores(scores):
    scores=np.asarray(scores,dtype=float)
    if scores.ndim!=1 or len(scores)<2 or np.any(np.isnan(scores)) or np.any(np.isposinf(scores)) or not np.any(np.isfinite(scores)):
        raise ValueError('at least two valid branch scores and finite mass required')
    shifted=scores-np.max(scores);weights=np.exp(shifted);prob=weights/np.sum(weights)
    order=np.argsort(-scores,kind='stable');positive=prob>0
    entropy=float(-np.sum(prob[positive]*np.log(prob[positive])))
    return dict(top_index=int(order[0]),gap=float(scores[order[0]]-scores[order[1]]) if np.isfinite(scores[order[1]]) else None,
        top_probability=float(prob[order[0]]),background_probability=float(prob[-1]),entropy=entropy,
        effective_branches=float(np.exp(entropy)),marginal_correction=float(np.log(np.sum(weights))),
        omitted_mass={str(k):float(np.sum(prob[order[k:]])) for k in [1,2,4]},
        mass_sum=float(np.sum(prob)),branches=len(scores))
