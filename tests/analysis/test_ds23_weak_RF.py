from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_0289_weak_RF import restricted_frames
from fast_local_pilot_refinement import FastPilotWorkspace


def test_training_subset_has_exact_original_frame_likelihood_without_other_frames():
    y = np.random.default_rng(4).normal(size=48000)+1j*np.random.default_rng(5).normal(size=48000)
    workspace = FastPilotWorkspace(y, 2400000., 'lower', 120.)
    frequencies = np.array([250., 750.])
    for parity, label in [(0, 'even'), (1, 'odd')]:
        train = restricted_frames(workspace, parity)
        np.testing.assert_allclose(train.evaluate(frequencies), workspace.evaluate(frequencies, subset=label), rtol=0, atol=1e-15)
        assert len(train.frames)+len(restricted_frames(workspace, 1-parity).frames) == len(workspace.frames)
    assert len(workspace.frames) > len(restricted_frames(workspace, 0).frames)
