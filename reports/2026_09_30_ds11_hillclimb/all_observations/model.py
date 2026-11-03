"""Same-scan final estimation using all observations in the frozen bank.

The original mask still determines candidate visibility. A separate copied
mask controls fitting, so the caller's independent diagnostic remains intact.
Former held observations are explicitly estimation data in this experiment.
"""
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import ds7_fast_baseline_adapter as fast


class FixedVisibility(fast.Stationary):
    def prediction(self, track, x):
        original = dict(track, mask=track['_visibility_mask'])
        return super().prediction(original, x)


class Model:
    def __init__(self, documents, config, variant):
        if variant not in ('original', 'all') or len(documents) != 1:
            raise ValueError('one recording and original/all variant required')
        fast.baseline.profile = fast.profile
        tracks = []
        original_count = total_count = 0
        for track in documents[0]['tracks']:
            original = np.asarray(track['mask'], dtype=bool).copy()
            fit_mask = np.ones_like(original) if variant == 'all' else original.copy()
            tracks.append(dict(track, mask=fit_mask, _visibility_mask=original))
            original_count += int(original.sum())
            total_count += len(original)
        document = dict(documents[0], tracks=tracks)
        self.engine = FixedVisibility(document, config)
        self.metadata = dict(
            variant=variant, original_training_observations=original_count,
            available_observations=total_count,
            fitting_observations=total_count if variant == 'all' else original_count,
            candidate_visibility='original training mask',
            held_diagnostic_independent=variant == 'original',
            limitation='Candidate banks and track admission remain conditioned on the original export.')

    def evaluate(self, x, gradient=True):
        score, derivative = self.engine.evaluate(np.asarray(x, dtype=float), gradient=gradient)
        return dict(score=score, gradient=derivative)


def build_model(documents, config, variant, index=None):
    return Model(documents, config, variant)
