import ctypes as ct
import subprocess

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import receiver_build


@pytest.fixture(scope="module")
def fir(tmp_path_factory):
    work = tmp_path_factory.mktemp("fir-tile")
    native = receiver_build.PINNED / "tools/pipeline_eval/variants/delay_product_kernel.c"
    source = work / "reference.c"
    source.write_text(
        "#define delay_decimate leo_pgo_delay_decimate\n"
        + receiver_build.paired_fir(native.read_text())
        + """
int fixture_reference(const float *in, const float *coeff, int taps, int stride, float *out) {
    return leo_pgo_delay_decimate(in, coeff, taps, stride, out);
}
int fixture_avx2(void) { return __builtin_cpu_supports("avx2"); }
""",
    )
    binary = work / "tile-fixture.so"
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-O3", "-fopenmp-simd", "-ffp-contract=off",
         "-fno-strict-aliasing", "-I", receiver_build.HERE, source,
         receiver_build.HERE / "receiver_fir_tile.c", "-lm", "-o", binary],
        check=True,
    )
    library = ct.CDLL(str(binary))
    for name in ("fixture_reference", "delay_decimate"):
        getattr(library, name).argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
    return library


@pytest.mark.hardware
@pytest.mark.parametrize("fractional", [False, True])
def test_tiled_fir_matches_every_output_including_edges(fir, fractional):
    if not fir.fixture_avx2():
        pytest.skip("AVX2 is required to exercise the tiled FIR")
    rng = np.random.default_rng(90396)
    data = rng.integers(-32768, 32768, size=400_001, dtype=np.int16).astype(np.float32)[1:]
    if fractional:
        data = data * np.float32(1.0 / 117)
    data[12:20] = [0., -0., 0., -0., 1., -1., 0., -0.]
    coeff = rng.uniform(-.05, .05, 82).astype(np.float32)[1:]
    reference, output = (np.empty(100_001, dtype=np.float32)[1:] for _ in range(2))
    assert fir.fixture_reference(data.ctypes.data, coeff.ctypes.data, 81, 4, reference.ctypes.data) == 0
    assert fir.delay_decimate(data.ctypes.data, coeff.ctypes.data, 81, 4, output.ctypes.data) == 0
    assert output.tobytes() == reference.tobytes()


def test_nonproduction_geometry_and_alias_delegate(fir):
    coefficients = np.array([0.25, 0.5, .25] * 27, dtype=np.float32)
    data = np.arange(400_000, dtype=np.float32)
    control, candidate = data.copy(), data.copy()
    assert fir.fixture_reference(control.ctypes.data, coefficients.ctypes.data, 81, 4, control.ctypes.data) == 0
    assert fir.delay_decimate(candidate.ctypes.data, coefficients.ctypes.data, 81, 4, candidate.ctypes.data) == 0
    assert candidate.tobytes() == control.tobytes()
    control, candidate = np.empty(200_000, dtype=np.float32), np.empty(200_000, dtype=np.float32)
    assert fir.fixture_reference(data.ctypes.data, coefficients.ctypes.data, 3, 2, control.ctypes.data) == 0
    assert fir.delay_decimate(data.ctypes.data, coefficients.ctypes.data, 3, 2, candidate.ctypes.data) == 0
    assert candidate.tobytes() == control.tobytes()
    assert fir.delay_decimate(None, coefficients.ctypes.data, 81, 4, candidate.ctypes.data) == -1
