"""Normalized t4 mixture over independent raw-sample variance-inflation masks."""
from math import lgamma

import numpy as np


class SampleVarianceMixture:
    """Integrate Bernoulli sample masks after a supplied linear contrast map.

    Conditional scale is C + extra_variance B diag(mask) B.T. Each component
    retains the original shared t4 scale mixing; this is not independent t noise
    on arbitrary contrast coordinates. Intended for short, bounded tracks.
    """

    def __init__(self, covariance, contrasts, probability, extra_variance):
        covariance = np.asarray(covariance, dtype=float)
        contrasts = np.asarray(contrasts, dtype=float)
        if (covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]
                or contrasts.ndim != 2 or contrasts.shape[0] != covariance.shape[0]
                or not 1 <= contrasts.shape[1] <= 12 or not covariance.size
                or np.any(~np.isfinite(covariance)) or np.any(~np.isfinite(contrasts))
                or not np.allclose(covariance, covariance.T)
                or not np.isfinite(probability) or not 0 <= probability < 1
                or not np.isfinite(extra_variance) or extra_variance <= 0):
            raise ValueError('invalid scale, contrasts or mask model')
        np.linalg.cholesky(covariance)
        self.dimension = covariance.shape[0]
        n = contrasts.shape[1]
        if probability == 0:
            self.masks = np.zeros((1, n))
            self.log_weights = np.zeros(1)
        else:
            self.masks = ((np.arange(2**n)[:, None] >> np.arange(n)) & 1).astype(float)
            count = self.masks.sum(axis=1)
            self.log_weights = count*np.log(probability)+(n-count)*np.log1p(-probability)
        scales = covariance[None]+extra_variance*np.einsum(
            'in,mn,jn->mij', contrasts, self.masks, contrasts)
        chol = np.linalg.cholesky(scales)
        identity = np.broadcast_to(np.eye(self.dimension), scales.shape)
        self.precisions = np.linalg.solve(scales, identity)
        logdet = 2*np.log(np.diagonal(chol, axis1=-2, axis2=-1)).sum(axis=1)
        self.normalizers = (lgamma((4+self.dimension)/2)-lgamma(2)
                            -.5*(self.dimension*np.log(4*np.pi)+logdet))

    def evaluate(self, residual):
        residual = np.asarray(residual, dtype=float)
        if residual.shape != (self.dimension,) or np.any(~np.isfinite(residual)):
            raise ValueError('invalid residual')
        solved = np.einsum('mij,j->mi', self.precisions, residual)
        quadratic = np.einsum('mi,i->m', solved, residual)
        logs = (self.log_weights+self.normalizers
                -.5*(4+self.dimension)*np.log1p(quadratic/4))
        largest = float(logs.max())
        probabilities = np.exp(logs-largest)
        total = float(probabilities.sum())
        probabilities /= total
        weights = (4+self.dimension)/(4+quadratic)
        precision = np.einsum('m,m,mij->ij', probabilities, weights, self.precisions)
        return largest+np.log(total), precision, probabilities@self.masks
