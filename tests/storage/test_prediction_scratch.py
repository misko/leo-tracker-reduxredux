"""Lifecycle and read-only guarantees for disposable prediction banks."""

from contextlib import nullcontext

import numpy as np
import pytest

from leo.storage.prediction_scratch import PredictionScratch


@pytest.mark.parametrize("fail", [False, True])
def test_direct_mapping_prefix_and_cleanup(tmp_path, fail):
    with (
        pytest.raises(RuntimeError) if fail else nullcontext(),
        PredictionScratch(tmp_path) as scratch,
    ):
        writable = scratch.allocate((10, 3))
        writable[:4] = np.arange(12).reshape(4, 3)
        retained = scratch.finalize(writable, 4)
        assert isinstance(retained, np.memmap)
        assert not retained.flags.writeable
        np.testing.assert_array_equal(retained, np.arange(12).reshape(4, 3))
        assert list(tmp_path.rglob("*.npy"))
        if fail:
            raise RuntimeError("propagation failed")
    assert not list((tmp_path / "prediction-scratch").iterdir())


def test_empty_arrays_and_legacy_retention(tmp_path):
    with PredictionScratch(tmp_path) as scratch:
        empty = scratch.finalize(scratch.allocate((0, 3)), 0)
        assert empty.shape == (0, 3)
        retained = scratch.retain(np.arange(12, dtype=np.float32).reshape(4, 3))
        assert retained.dtype == np.float32
        np.testing.assert_array_equal(retained, np.arange(12).reshape(4, 3))
        assert scratch.finalize(scratch.allocate((4, 3)), 0).shape == (0, 3)
        with pytest.raises(ValueError, match="capacity"):
            scratch.finalize(np.empty((2, 3)), 3)
