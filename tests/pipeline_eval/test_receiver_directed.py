import ctypes as ct
from random import Random
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.directed_verifier_trial import CODE, PERIOD, compare, external_seeds, seed


def test_supplied_time_keeps_wrapped_epoch_and_fraction():
    before = seed(-.25, -18_000.)
    after = seed(PERIOD + .25, 18_000.)
    assert (before.epoch, before.sample, before.offset, before.hz) == (0, 0, -.25, -18_000.)
    assert (after.epoch, after.sample, after.offset, after.hz) == (0, 0, .25, 18_000.)


def test_perturbed_proposal_does_not_claim_original_or_decoy():
    factor = (0, 3000, .2, -401_000., .15, .03)
    proposals, negatives = external_seeds((factor,), 0., Random(1), False)
    assert len(proposals) == len(negatives) == 4
    assert abs(proposals[0].coarse_epoch - 3000.2) <= 1.
    assert abs(proposals[0].hz + 401_000.) <= 400.
    assert all(abs(s.hz + 401_000.) > 250 or abs(s.coarse_epoch - 3000.2) > 2 for s in negatives)
    close = (1, 3001, .1, -400_800., .14, .03)
    wrong_sign = (1, 3000, .2, 401_000., .15, .03)
    assert compare((factor,), (wrong_sign, close))[:2] == ({0: 1}, 1)


@pytest.fixture(scope="module")
def aperture_load(tmp_path_factory):
    directory = tmp_path_factory.mktemp("directed-load")
    source = (CODE / "receiver_directed_verify.inc").read_text().split("/* With a supplied", 1)[0]
    stub = """
#include <stdint.h>
enum { samples = 200000, n = 13333, max_frames = 15, first = 88, stop = 2904 };
typedef struct { double re, im; } PortableFineSample;
typedef struct { struct { PortableFineSample fine[samples]; } iq; } PortableVerifier;
static int frame_start(unsigned epoch, unsigned frame) {
    return (int)(epoch + (frame * 40000 + 1) / 3);
}
static int portable_verifier_load(PortableVerifier *w, const int16_t *iq, unsigned lane) {
    for (int i = 0; i < samples; ++i)
        w->iq.fine[i] = (PortableFineSample){iq[4*i + 2*lane], iq[4*i + 2*lane + 1]};
    return 0;
}
"""
    file = directory / "load.c"
    file.write_text(stub + source)
    built = directory / "load.so"
    subprocess.run(["cc", "-O3", "-fPIC", "-shared", file, "-o", built], check=True)
    function = ct.CDLL(str(built)).directed_load_apertures
    function.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint, ct.POINTER(ct.c_uint), ct.c_int]
    function.restype = ct.c_int
    return function


@pytest.mark.parametrize("epochs", [(3011,), (129, 13111), (13332, 3000)])
def test_aperture_load_covers_stencil_and_wrap(aperture_load, epochs):
    original = np.arange(800_000, dtype=np.int32).astype(np.int16).reshape(200_000, 2, 2)
    out = np.full((200_000, 2), np.nan, dtype=np.float64)
    seeds = (ct.c_uint * len(epochs))(*epochs)
    assert aperture_load(out.ctypes.data, original.ctypes.data, 1, seeds, len(epochs)) == 0
    if 13332 in epochs:
        np.testing.assert_array_equal(out, original[:, 1])
        return
    mask = np.zeros(len(out), dtype=np.bool_)
    for epoch in epochs:
        for frame in range(15):
            start = epoch + (frame * 40000 + 1) // 3
            mask[start + 88 - 32:start + 2904 + 32] = True
    np.testing.assert_array_equal(out[mask], original[mask, 1])
    assert np.isnan(out[~mask]).all()
