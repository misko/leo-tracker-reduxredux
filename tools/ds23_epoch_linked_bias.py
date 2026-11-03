"""Frequency-bias covariance for repeatedly frame-linked curved fragments."""

import numpy as np


def linked_covariance(keys, edges, *, marginal_sigma_hz=300., independent_sigma_hz=30.):
    if not 0 < independent_sigma_hz <= marginal_sigma_hz:
        raise ValueError('positive independent SD no larger than marginal SD required')
    if len(set(keys)) != len(keys):
        raise ValueError('unique curve keys required')
    lookup = {key:k for k,key in enumerate(keys)}
    parents = list(range(len(keys)))
    def root(k):
        while parents[k] != k:
            parents[k] = parents[parents[k]]
            k = parents[k]
        return k
    for a,b in edges:
        if a not in lookup or b not in lookup:
            raise ValueError('only existing curved calibration fragments may be linked')
        parents[root(lookup[a])] = root(lookup[b])
    groups = np.array([root(k) for k in range(len(keys))])
    shared = marginal_sigma_hz**2-independent_sigma_hz**2
    covariance = (groups[:,None]==groups[None,:])*shared
    covariance += np.eye(len(keys))*independent_sigma_hz**2
    return covariance
