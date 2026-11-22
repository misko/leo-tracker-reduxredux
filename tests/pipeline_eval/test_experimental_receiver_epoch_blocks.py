import ctypes as ct

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import receiver_build, receiver_epoch_blocks


@pytest.fixture(scope="module")
def chooser(tmp_path_factory):
    binary = tmp_path_factory.mktemp("epoch-blocks") / "receiver.so"
    receiver_epoch_blocks.overlay(receiver_build.build)(binary, fftw=False, fma=False, reuse=False)
    library = ct.CDLL(str(binary))
    function = library.experimental_epoch_peaks
    function.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_void_p]
    function.restype = None
    return function


def compare(chooser, scores, radius):
    expected, actual = scores.copy(), scores.copy()
    reference, blocked = [np.empty(12, dtype="<i4") for _ in range(2)]
    chooser(expected.ctypes.data, len(scores), radius, len(reference), 0, reference.ctypes.data)
    chooser(actual.ctypes.data, len(scores), radius, len(blocked), 1, blocked.ctypes.data)
    assert actual.tobytes() == expected.tobytes()
    assert blocked.tobytes() == reference.tobytes()
    return blocked


@pytest.mark.parametrize("count,radius", [(1, 0), (65, 6), (130, 2), (3333, 2), (13333, 6), (14501, 6)])
def test_blocked_peaks_preserve_score_mutation_and_ties_at_wrap(chooser, count, radius):
    rng = np.random.default_rng(1721)
    score = rng.integers(0, 10, count).astype("<f8")
    score[[0, count - 1]] = 10.
    peaks = compare(chooser, score, radius)
    assert peaks[0] == 0
    compare(chooser, np.zeros(count, dtype="<f8"), radius)
    compare(chooser, -np.ones(count, dtype="<f8"), radius)


@pytest.mark.parametrize("nan_index", [0, 17, 64])
def test_blocked_peaks_handle_nonfinite_inputs_like_the_ordered_scan(chooser, nan_index):
    score = np.zeros(131, dtype="<f8")
    score[[63, 78, 130]] = np.inf
    score[12] = -np.inf
    score[nan_index] = np.nan
    compare(chooser, score, 2)
