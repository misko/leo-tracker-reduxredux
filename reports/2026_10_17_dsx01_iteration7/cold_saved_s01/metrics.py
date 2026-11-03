"""Fixed-denominator assignment changes; identities remain model labels."""
from collections import Counter
import numpy as np


def zero_c(vector, nuisance):
    v, n = np.asarray(vector, float).copy(), np.asarray(nuisance, float).copy()
    v[6] = 0.
    return v, n


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values)**2))) if len(values) else None


def compare(original, saved, mask):
    mask = np.asarray(mask, bool)
    a, b = original['associated'] & mask, saved['associated'] & mask
    both = a & b
    same = both & (original['satellite_number'] == saved['satellite_number'])
    return dict(denominator=int(mask.sum()), original_assigned=int(a.sum()), saved_assigned=int(b.sum()),
        original_assigned_rms_hz=rms(original['residual_hz'][a]), saved_assigned_rms_hz=rms(saved['residual_hz'][b]),
        new=int((b & ~a).sum()), lost=int((a & ~b).sum()), retained=int(both.sum()),
        retained_identity_changes=int((both & ~same).sum()), retained_same_identity=int(same.sum()),
        intersection_original_rms_hz=rms(original['residual_hz'][both]),
        intersection_saved_rms_hz=rms(saved['residual_hz'][both]),
        same_identity_original_rms_hz=rms(original['residual_hz'][same]),
        same_identity_saved_rms_hz=rms(saved['residual_hz'][same]),
        original_identity_histogram={str(k):v for k, v in sorted(Counter(map(int, original['satellite_number'][a])).items())},
        saved_identity_histogram={str(k):v for k, v in sorted(Counter(map(int, saved['satellite_number'][b])).items())})
