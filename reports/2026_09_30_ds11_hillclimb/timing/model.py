"""Timing sensitivities around the original IID likelihood, not clock calibration."""
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import ds7_fast_baseline_adapter as baseline


class TimingModel:
    def __init__(self, documents, config, variant):
        if len(documents) != 1:
            raise ValueError('Single recording required')
        self.variant = variant
        if variant not in ('original', 'zero', 'sd010', 'sd050'):
            raise ValueError(variant)
        baseline.baseline.profile = baseline.profile
        self.model = baseline.Stationary(documents[0], config)
        self.sd = {'sd010': .1, 'sd050': .5}.get(variant)
        self.bounds = [(-12., 12.), (-12., 12.), (0., 0.) if variant=='zero' else (-5., 5.)]
        self.metadata = dict(variant=variant, timing_prior_sd_s=self.sd,
                             scientific_status='Uncalibrated timing sensitivity')

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float).copy()
        if self.variant == 'zero':
            x[2] = 0.
        score, derivative = self.model.evaluate(x, gradient)
        if self.sd is not None:
            score -= .5*(x[2]/self.sd)**2
            derivative[2] -= x[2]/self.sd**2
        if self.variant == 'zero':
            derivative[2] = 0.
        return dict(score=score, gradient=derivative)


def build_model(documents, config, variant, index=None):
    return TimingModel(documents, config, variant)
