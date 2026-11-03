"""Numerically centre the SAME objective by differencing individual rows.

This avoids subtracting two complete NLLs near 40,000 when a local improvement
is smaller than their float64 spacing. Priors, gradients and constraints are
unchanged. Acceptance is audited against the unwrapped scientific model.
"""
import numpy as np


class CentredObjective:
    def __init__(self, model, vector, nuisance):
        self.model=model
        ev,details=model.evaluate_details(vector,nuisance)
        self.reference_rows=np.array(details['row_nll'],copy=True)
        self.reference_prior=float(details['prior_penalty'])
        self.reference_objective=float(ev[0])
        self.calls=1

    def __getattr__(self,name):
        if name=='model':raise AttributeError(name)
        return getattr(self.model,name)

    def evaluate_joint(self,vector,nuisance):
        ev,details=self.model.evaluate_details(vector,nuisance)
        self.calls+=1
        rows=np.asarray(details['row_nll'])
        if rows.shape!=self.reference_rows.shape:
            raise ValueError('Centred comparison requires exactly the same scored rows')
        delta=np.sum(rows-self.reference_rows,dtype=np.longdouble)
        delta+=np.longdouble(details['prior_penalty'])-np.longdouble(self.reference_prior)
        return float(delta),*ev[1:]
