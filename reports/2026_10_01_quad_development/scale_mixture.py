"""Equal-prior normalized mixture of independent and shared track scales."""
import numpy as np
from scale_prediction import log_density, conditional


def components(rows):
    independent = sum(log_density(r['d'], r['q'], r['logdet']) for r in rows)
    shared = log_density(sum(r['d'] for r in rows), sum(r['q'] for r in rows), sum(r['logdet'] for r in rows))
    return independent, shared


def mixture(rows):
    a, b = components(rows)
    return float(np.logaddexp(a, b)-np.log(2))


def held_prediction(held, training):
    a, b = components(training); z = np.logaddexp(a, b)
    independent = log_density(held['d'], held['q'], held['logdet'])
    shared = conditional(held['d'], held['q'], held['logdet'], sum(r['d'] for r in training), sum(r['q'] for r in training))
    value = float(np.logaddexp(a-z+independent, b-z+shared))
    return value, float(np.exp(b-z))


def track_weights(rows):
    a, b = components(rows); rho = float(np.exp(b-np.logaddexp(a, b)))
    shared = (4+sum(r['d'] for r in rows))/(4+sum(r['q'] for r in rows))
    return np.array([rho*shared+(1-rho)*(4+r['d'])/(4+r['q']) for r in rows]), rho
