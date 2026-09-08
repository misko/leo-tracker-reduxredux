import ctypes as ct
import json
import subprocess

import numpy as np
import pytest

from tools.native_presence import ROOT, NativePresence, Result, build_library, pointer


@pytest.fixture(scope="module")
def fold_function(tmp_path_factory):
    path = tmp_path_factory.mktemp("ci16-fold") / "fold.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O3",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "tests/fixtures/native_presence_ci16_fold.c"),
            "-lm",
            "-o",
            str(path),
        ],
        check=True,
    )
    library = ct.CDLL(str(path))
    function = library.test_ci16_fold
    function.argtypes = [ct.c_uint32, ct.c_void_p, ct.c_size_t] + [ct.c_void_p] * 4
    function.restype = None
    return function


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("length", ["minimum", "partial", "full"])
@pytest.mark.parametrize("kind", ["random", "minimum", "alternating", "zeros"])
def test_exact_fold_sums_support_and_tails(fold_function, rate, length, kind):
    count = {"minimum": int(np.ceil(rate / 375)), "partial": rate // 50 - 7, "full": rate // 50}[
        length
    ]
    rng = np.random.default_rng(735)
    iq = rng.integers(-32768, 32768, (count, 2), dtype=np.int16)
    if kind == "minimum":
        iq[:] = -32768
    elif kind == "alternating":
        iq[::2] = [-32768, 32767]
        iq[1::2] = [32767, -32768]
    elif kind == "zeros":
        iq[:] = 0
    original = iq.tobytes()
    n = round(rate / 750)
    expected_power = np.zeros(n, dtype=np.int64)
    real, imag = np.zeros((2, n), dtype=np.int64)
    support, diff_support = np.zeros((2, n), dtype=np.int32)
    a = iq.astype(np.int64)
    for frame in range(16):
        start = round(frame * (rate / 750))
        if start >= count:
            break
        valid, paired = min(n, count - start), min(n, max(0, count - start - 4))
        x, y = a[start : start + valid], a[start + 4 : start + 4 + paired]
        expected_power[:valid] += x[:, 0] ** 2 + x[:, 1] ** 2
        real[:paired] += x[:paired, 0] * y[:, 0] + x[:paired, 1] * y[:, 1]
        imag[:paired] += x[:paired, 0] * y[:, 1] - x[:paired, 1] * y[:, 0]
        support[:valid] += 1
        diff_support[:paired] += 1
    power, diff = np.zeros(n), np.zeros(n, dtype=np.complex128)
    actual_support, actual_diff_support = np.zeros((2, n), dtype=np.int32)
    fold_function(
        rate,
        pointer(iq),
        count,
        pointer(power),
        pointer(diff),
        pointer(actual_support),
        pointer(actual_diff_support),
    )
    for actual, expected in (
        (power, expected_power),
        (diff.real, real),
        (diff.imag, imag),
        (actual_support, support),
        (actual_diff_support, diff_support),
    ):
        np.testing.assert_array_equal(actual, expected)
    assert iq.tobytes() == original


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = (
        tuple(protocol["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in protocol["variants"][0]["defines"].items())
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1",)
    )
    return build_library(tmp_path_factory.mktemp("ci16-fold-native") / "presence.so", cflags=flags)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("tone", [False, True])
def test_raw_integer_search_and_tone_fallback_preserve_outputs(library, rate, edge, tone):
    rng = np.random.default_rng(139)
    count = rate // 50
    x = 800 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    if tone:
        x += 10000 * np.exp(2j * np.pi * 137123 * np.arange(count) / rate)
    iq = np.rint(np.column_stack((x.real, x.imag))).astype(np.int16)
    samples = iq[:, 0].astype(np.float64) + 1j * iq[:, 1]
    with NativePresence(library, rate, edge) as native:
        expected_grid = native.coarse(samples)
        grid = np.zeros_like(expected_grid)
        function = native.library.leo_presence_coarse_ci16
        function.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p]
        assert function(native.workspace, pointer(iq), count, pointer(grid)) == 0
        np.testing.assert_array_equal(grid, expected_grid)
        expected = native.run(samples)
        nuisance = native.nuisance()
        assert nuisance["applied"] == int(tone)
        result = Result()
        assert (
            native.library.leo_presence_run_ci16(
                native.workspace, pointer(iq), count, ct.byref(result)
            )
            == 0
        )
        assert result.candidate_count == expected.candidate_count
        assert bytes(result.candidates) == bytes(expected.candidates)
        assert native.nuisance()["applied"] == nuisance["applied"]
        grid[:] = 17
        assert function(native.workspace, pointer(iq), count + 1, pointer(grid)) == -1
        assert np.all(grid == 17)
