from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.conditional_support import PERIOD, harmonic_difference
from tools.pipeline_eval.variants import conditional_support_recovery as recovery


def test_harmonic_audit_requires_integer_native_lift():
    native = np.array([120, -400, 50.0])
    change = np.array([0, -2, 3])
    assert np.array_equal(harmonic_difference(native, native + PERIOD * change), change)
    with pytest.raises(ValueError, match="harmonic"):
        harmonic_difference(native, native + PERIOD * change + 1.0)


def test_pair_requires_both_frozen_basin_predictions():
    phase = recovery.phase.PHASES
    k = int(np.flatnonzero(phase == 14.0)[0])
    a = np.full((2, 2, len(phase)), 40.0)
    b = a.copy()
    a[0, 1, k] = 0.3
    a[1, 1, k] = 0.8
    b[1, 1, k] = 0.4
    b[0, 1, k] = 1.3
    tracks = [SimpleNamespace(lane=0, rf=n * 1e9, t=np.arange(27.0)) for n in (11, 12)]
    proposals = recovery.pair_candidates({0: a, 1: b}, tracks)
    assert len(proposals) == 1 and proposals[0]["phase_s"] == 14.0
    assert proposals[0]["cross_scores"] == [0.3, 1.3, 0.8, 0.4]
    b[0, 1, k] = 9.0
    assert not recovery.pair_candidates({0: a, 1: b}, tracks)
    b[0, 1, k] = 1.3
    assert not recovery.pair_candidates({0: a, 1: b}, [tracks[0]] * 2)
