"""Exact Gamma-integrated prediction using whitened residual energies."""
from math import lgamma, log, pi


def log_density(dimension, energy, logdet, nu=4.):
    if dimension == 0:
        if energy != 0 or logdet != 0: raise ValueError('nonempty sufficient statistics')
        return 0.
    if dimension < 0 or energy < 0 or nu <= 0: raise ValueError('invalid statistics')
    return (lgamma((nu+dimension)/2)-lgamma(nu/2)-.5*(dimension*log(nu*pi)+logdet)
            -.5*(nu+dimension)*log(1+energy/nu))


def conditional(d, q, logdet, train_d, train_q):
    nu = 4.+train_d; scale = (4.+train_q)/nu
    return log_density(d, q/scale, logdet+d*log(scale), nu)
