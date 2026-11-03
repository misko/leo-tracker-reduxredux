import importlib.util
import math
from pathlib import Path

import numpy as np

path = Path(__file__).resolve().parents[1] / '2026_09_29_frequency_contrast/contrast_position.py'
spec = importlib.util.spec_from_file_location('frozen_contrast', path)
contrast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contrast)


class FrozenAssociation:
    def __init__(self, original, donor):
        self.original = original
        self.models = original.models
        self.documents = original.documents
        self.fixed = {}
        for di, (doc, engine) in enumerate(zip(self.documents, self.models, strict=True)):
            for ti, track in enumerate(doc['tracks']):
                pred, visible = engine.prediction(track, np.array([*donor[:2], donor[di+2]]))
                assert visible.any()
                train, _ = contrast.contrast_density((track['y'][None, :] - pred)[:, track['mask']])
                prior = math.log(0.8) - math.log(int(visible.sum()))
                components = np.r_[math.log(0.2) + original.background[di, ti][0], prior + train[visible]]
                logp = components - np.logaddexp.reduce(components)
                probabilities = np.exp(logp)
                weights = np.zeros(len(visible))
                weights[visible] = probabilities[1:]
                constant = probabilities[0] * components[0] + probabilities[1:].sum() * prior - probabilities @ logp
                self.fixed[di, ti] = (visible.copy(), weights, float(constant))

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float)
        score, derivative = 0.0, np.zeros_like(x)
        for di, (doc, engine) in enumerate(zip(self.documents, self.models, strict=True)):
            local = np.array([*x[:2], x[di+2]])
            for ti, track in enumerate(doc['tracks']):
                expected, weights, constant = self.fixed[di, ti]
                pred, visible = engine.prediction(track, local)
                if not np.array_equal(visible, expected):
                    raise ValueError('Frozen donor visible support changed')
                mask = track['mask']
                train, influence = contrast.contrast_density((track['y'][None, :] - pred)[:, mask])
                score += constant + float(weights @ train)
                if gradient:
                    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                        plus, minus = local.copy(), local.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        if axis == 2:
                            plus[axis] = min(5, plus[axis])
                            minus[axis] = max(-5, minus[axis])
                        pp, vp = engine.prediction(track, plus)
                        pm, vm = engine.prediction(track, minus)
                        if not np.array_equal(vp, expected) or not np.array_equal(vm, expected):
                            raise ValueError('Frozen donor derivative support changed')
                        dp = (pp[:, mask] - pm[:, mask]) / (plus[axis]-minus[axis])
                        derivative[axis if axis < 2 else di+2] += float(weights @ np.sum(influence*dp, axis=1))
        return dict(score=score, gradient=derivative)
