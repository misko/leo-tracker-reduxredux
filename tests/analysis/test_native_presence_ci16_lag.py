import ctypes as ct
import json
import subprocess

import numpy as np
import pytest

from tools.native_presence import ROOT, NativePresence, Result, build_library, pointer


@pytest.fixture(scope="module")
def lag_function(tmp_path_factory):
    path = tmp_path_factory.mktemp("ci16-lag") / "lag.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O3",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "tests/fixtures/native_presence_ci16_lag.c"),
            "-o",
            str(path),
        ],
        check=True,
    )
    library = ct.CDLL(str(path))
    function = library.test_ci16_lag
    function.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_size_t, ct.c_void_p]
    function.restype = None
    return function


@pytest.mark.parametrize("count,lag", [(7, 0), (7, 3), (50000, 0), (100000, 16384)])
@pytest.mark.parametrize("kind", ["random", "minimum", "alternating"])
def test_integer_lag_is_exact_at_full_scale(lag_function, count, lag, kind):
    rng = np.random.default_rng(517)
    iq = rng.integers(-32768, 32768, (count, 2), dtype=np.int16)
    if kind == "minimum":
        iq[:] = -32768
    elif kind == "alternating":
        iq[::2] = [-32768, 32767]
        iq[1::2] = [32767, -32768]
    a, b = iq[: count - lag].astype(np.int64), iq[lag:].astype(np.int64)
    expected = np.array(
        [
            np.sum(a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]),
            np.sum(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]),
        ],
        dtype=np.float64,
    )
    output = np.zeros(2)
    lag_function(pointer(iq), count, lag, pointer(output))
    np.testing.assert_array_equal(output, expected)


@pytest.fixture(scope="module")
def ci16_library(tmp_path_factory):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in protocol["variants"][0]["defines"].items()
    )
    return build_library(tmp_path_factory.mktemp("ci16-tone") / "presence.so", cflags=flags)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_ci16_and_fp64_ingestion_have_same_tone_evidence(ci16_library, rate, edge):
    rng = np.random.default_rng(724)
    n = rate // 50
    values = 8000 * np.exp(2j * np.pi * (-173123) * np.arange(n) / rate)
    values += 1500 * (rng.normal(size=n) + 1j * rng.normal(size=n))
    iq = np.rint(np.column_stack((values.real, values.imag))).astype(np.int16)
    samples = iq[:, 0].astype(np.float64) + 1j * iq[:, 1]
    original = iq.copy()
    with NativePresence(ci16_library, rate, edge) as native:
        expected = native.run(samples)
        nuisance = native.nuisance()
        result = Result()
        assert (
            native.library.leo_presence_run_ci16(native.workspace, pointer(iq), n, ct.byref(result))
            == 0
        )
        actual = native.nuisance()
        for key in nuisance:
            if key != "cpu_ms":
                assert actual[key] == pytest.approx(nuisance[key], rel=1e-9, abs=1e-10)
        assert result.candidate_count == expected.candidate_count
        for a, b in zip(
            result.candidates[: result.candidate_count],
            expected.candidates[: expected.candidate_count],
            strict=True,
        ):
            assert a.epoch == b.epoch and a.fractional_complete == b.fractional_complete
            assert a.exact_score == pytest.approx(b.exact_score, rel=1e-9, abs=1e-10)
            assert a.control_score == pytest.approx(b.control_score, rel=1e-9, abs=1e-10)
            assert a.fractional_offset_samples == pytest.approx(
                b.fractional_offset_samples, abs=1e-7
            )
            assert a.tracking_cfo_hz == pytest.approx(b.tracking_cfo_hz, abs=0.001)
    np.testing.assert_array_equal(iq, original)
