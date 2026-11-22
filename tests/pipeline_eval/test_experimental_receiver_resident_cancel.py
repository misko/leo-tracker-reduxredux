import ctypes as ct

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import receiver_build, receiver_resident_cancel


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp("resident-cancel") / "receiver.so"
    receiver_resident_cancel.overlay(receiver_build.build)(path, fftw=False, fma=False)
    lib = ct.CDLL(str(path))
    lib.pilot_cancel.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_void_p,
                                 ct.c_void_p, ct.c_double, ct.c_double]
    lib.pilot_cancel_resident.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_double, ct.c_double]
    return lib


@pytest.mark.parametrize("lane,epoch,hz", [
    (0, 0., -714331.), (1, 13332.8, 453181.), (1, 6412.33333, -799800.), (0, 3999.5, 0.),
])
def test_resident_signed_residual_matches_stereo_cancel_at_every_sample(library, lane, epoch, hz):
    rng = np.random.default_rng(1833)
    raw = rng.integers(-32768, 32768, size=(200000, 2, 2), dtype="<i2")
    saved = raw.tobytes()
    old = np.empty_like(raw)
    resident = np.ascontiguousarray(raw[:, lane], dtype="<f4")
    pilot = rng.normal(size=80000).astype("<f4")
    pilot[2 * 264:2 * 8712] = 0.
    original_work, resident_work = np.empty_like(pilot), np.empty_like(pilot)
    assert library.pilot_cancel(raw.ctypes.data, old.ctypes.data, lane, pilot.ctypes.data,
                                original_work.ctypes.data, epoch, hz) == 0
    assert library.pilot_cancel_resident(resident.ctypes.data, pilot.ctypes.data,
                                         resident_work.ctypes.data, epoch, hz) == 0
    expected = np.ascontiguousarray(old[:, lane], dtype="<f4")
    assert resident.tobytes() == expected.tobytes()
    assert resident_work.tobytes() == original_work.tobytes()
    assert raw.tobytes() == saved
    assert np.array_equal(old[:, 1 - lane], raw[:, 1 - lane])
    assert np.any(old[:, lane] != raw[:, lane])
    assert np.any((old[:, lane] == -32768) | (old[:, lane] == 32767))


@pytest.mark.parametrize("epoch,hz", [(-1., 0.), (13333., 0.), (12., 6e6), (float("nan"), 800000.)])
def test_resident_cancel_rejects_invalid_inputs_without_writing(library, epoch, hz):
    iq = np.ones((200000, 2), dtype="<f4")
    pilot = np.ones(80000, dtype="<f4")
    scratch = np.zeros_like(pilot)
    assert library.pilot_cancel_resident(iq.ctypes.data, pilot.ctypes.data,
                                         scratch.ctypes.data, epoch, hz) == -1
    assert np.all(iq == 1)
    assert not np.any(scratch)
