import ctypes as ct
import subprocess

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import (
    receiver_build, receiver_cancel_packed, receiver_resident_cancel,
)


@pytest.fixture(scope="module")
def cancellation(tmp_path_factory):
    work = tmp_path_factory.mktemp("packed-cancel")
    directory = receiver_build.PINNED / "tools/pipeline_eval/variants"
    released = (directory / "pilot_cancel.c").read_text()
    resident = receiver_resident_cancel.cancel(receiver_build.clamp_residual(released))
    packed = receiver_cancel_packed.overlay(resident)
    code = """
int test_round_nearest(void) { return fesetround(FE_TONEAREST); }
int test_round_upward(void) { return fesetround(FE_UPWARD); }
int test_subtract(float *iq, const float *wave, int count, double re, double im) {
    if (!__builtin_cpu_supports("avx2")) return 0;
    subtract_packed(iq, wave, count, re, im);
    return 1;
}
"""
    results = []
    for label, source in (("resident", resident), ("packed", packed + code)):
        path = work / f"{label}.c"
        path.write_text(source)
        binary = path.with_suffix(".so")
        subprocess.run(["cc", "-shared", "-fPIC", "-O3", "-ffp-contract=off", "-fno-math-errno",
                        "-I", directory, "-I", receiver_build.HERE, path, "-lm", "-o", binary], check=True)
        library = ct.CDLL(str(binary))
        library.pilot_cancel_resident.argtypes = [ct.c_void_p] * 3 + [ct.c_double] * 2
        results.append(library)
    return results


@pytest.mark.parametrize(("epoch", "carrier"), [(0., 0.), (0.34, -521_304.), (7001.65, 172_005.),
                                                (13332.9, -5e6), (81., 5e6)])
def test_signed_residual_retains_every_sample(cancellation, epoch, carrier):
    rng = np.random.default_rng(801)
    raw = rng.integers(-32768, 32768, size=400_000, dtype=np.int16).astype(np.float32)
    pilot = rng.standard_normal(size=80_000).astype(np.float32)
    scratch = np.zeros_like(pilot)
    outputs = []
    for library in cancellation:
        output = raw.copy()
        assert library.pilot_cancel_resident(
            output.ctypes.data, pilot.ctypes.data, scratch.ctypes.data, epoch, carrier,
        ) == 0
        outputs.append(output.tobytes())
    assert outputs[0] == outputs[1]


@pytest.mark.hardware
def test_packed_rounding_clipping_ties_and_odd_tail(cancellation):
    kernel = cancellation[1].test_subtract
    kernel.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double]
    iq = np.array([-2, 1, -32768, 32767, -1, 2, 0, 0, 2, -3], dtype=np.float32)
    wave = np.array([.5, -.5, 1, -1, .5, -.5, np.nan, np.nan, -.5, .5], dtype=np.float32)
    if not kernel(iq.ctypes.data, wave.ctypes.data, len(iq) // 2, 1., 0.):
        pytest.skip("AVX2 is required for the packed branch")
    assert iq.tolist() == [-2, 2, -32768, 32767, -2, 2, -32768, -32768, 2, -4]


def test_other_rounding_mode_uses_scalar_reference(cancellation):
    resident, packed = cancellation
    pilot = np.resize(np.array([.75, -.6, .22], dtype=np.float32), 80_000)
    scratch = np.empty_like(pilot)
    reference = np.resize(np.array([-40., 13., 3., 20.], dtype=np.float32), 400_000)
    candidate = reference.copy()
    assert packed.test_round_upward() == 0
    try:
        assert resident.pilot_cancel_resident(
            reference.ctypes.data, pilot.ctypes.data, scratch.ctypes.data, 12214.2, -87_500.,
        ) == 0
        assert packed.pilot_cancel_resident(
            candidate.ctypes.data, pilot.ctypes.data, scratch.ctypes.data, 12214.2, -87_500.,
        ) == 0
    finally:
        assert packed.test_round_nearest() == 0
    assert reference.tobytes() == candidate.tobytes()
