"""Normalized mixture of activity-local and globally available set likelihoods."""
import numpy as np


def mixture_log_likelihood(local,global_score,global_weight=.1):
    if not 0<=global_weight<=1:raise ValueError('Invalid mixture weight')
    local=np.asarray(local,float);global_score=np.asarray(global_score,float)
    if local.shape!=global_score.shape:raise ValueError('Mismatched group likelihoods')
    if global_weight==0:return local.copy()
    if global_weight==1:return global_score.copy()
    return np.logaddexp(np.log1p(-global_weight)+local,np.log(global_weight)+global_score)
