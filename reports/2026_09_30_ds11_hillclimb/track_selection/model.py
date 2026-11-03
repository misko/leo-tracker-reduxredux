from collections import Counter
import numpy as np

def arrays(rows, strength):
    counts = Counter((r['window'], r['rx']) for r in rows)
    weights = np.array([1/counts[r['window'], r['rx']] for r in rows])
    features = [[r['rx'], r['rf_hz']/1e9]+([r['exact'], r['control']] if strength else []) for r in rows]
    return np.asarray(features, float), np.array([r['retained'] for r in rows], float), weights

def standardize(features, weights):
    mean = np.average(features, axis=0, weights=weights)
    scale = np.sqrt(np.average((features-mean)**2, axis=0, weights=weights))
    return mean, np.where(scale>1e-12, scale, 1.)

def design(features, mean, scale):
    return np.column_stack((np.ones(len(features)), (features-mean)/scale))

def objective(beta, x, y, weights):
    from scipy.special import expit
    z = x@beta
    penalty = beta.copy(); penalty[0] = 0
    value = np.dot(weights, np.logaddexp(0, z)-y*z)+.5*np.dot(penalty, penalty)
    gradient = x.T@(weights*(expit(z)-y))+penalty
    return float(value), gradient

def log_probability(beta, x, y):
    z = x@beta
    return -np.logaddexp(0, (1-2*y)*z)
