"""Research RX oscillator curvature with immutable original timing priors."""
import numpy as np
from leo.analysis.regional_position_score import PositionObjective

def quadratic_design(observations):
    x=np.zeros((len(observations.window_ids),2))
    t=observations.times_s-observations.time_center_s
    for rx in (0,1):
        mask=observations.receiver==rx
        linear=np.column_stack([np.ones(mask.sum()),t[mask]])
        raw=t[mask]**2
        residual=raw-linear@np.linalg.lstsq(linear,raw,rcond=None)[0]
        peak=np.max(abs(residual))
        if peak<=1e-9:raise ValueError('quadratic oscillator gauge needs distinct times')
        x[mask,rx]=100*residual/peak
    return x

class QuadraticObjective(PositionObjective):
    """Two coefficients: unit=100Hz peak, independent Gaussian sigma=2 units."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.old_size=self.size
        self.basis=np.column_stack([self.basis,np.zeros((len(self.bank.numbers),2))])
        self.quadratic=quadratic_design(self.observations)
    def evaluate(self,vector):
        vector=np.asarray(vector,float)
        saved=self.baseline
        self.baseline=saved+self.quadratic@vector[-2:]
        try:value,gradient,terms=super().evaluate(vector)
        finally:self.baseline=saved
        gradient[-2:]+=self.quadratic.T@terms.prediction_gradient.sum(axis=1)+vector[-2:]/4
        return value+.5*np.sum((vector[-2:]/2)**2),gradient,terms
