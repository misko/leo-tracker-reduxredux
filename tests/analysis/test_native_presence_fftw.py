"""Optional FFT backend: explicit dependency, no implicit install or silent skip."""

import ctypes as ct
import json
import os
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import ROOT, NativePresence, Result, build_library, pointer
from tools.presence_fftw import fftw_options
from tools.qualify_presence_worker import compare_values

pytestmark = pytest.mark.fftw


class FFT(ct.Structure):
    _fields_ = [("size", ct.c_size_t)] + [
        (name, ct.c_void_p) for name in ("roots", "output", "scratch", "backend_plan")
    ]


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    prefix = os.environ.get("FFTW_PREFIX")
    if not prefix:
        pytest.fail(
            "fftw-marked tests require FFTW_PREFIX; exclude with -m 'not fftw' when unavailable"
        )
    options = fftw_options(Path(prefix))
    directory = tmp_path_factory.mktemp("presence-fftw")
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = (
        tuple(protocol["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in protocol["variants"][0]["defines"].items())
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1",)
    )
    return (
        build_library(directory / "builtin.so", cflags=flags),
        build_library(
            directory / "fftw.so",
            cflags=flags + options["cflags"],
            ldflags=options["ldflags"],
            dependencies=options["dependencies"],
        ),
    )


@pytest.mark.parametrize("size", [2, 5, 10, 25, 50, 125, 128, 512, 5000, 8192, 10000, 16384, 32768])
def test_fftw_matches_numpy_reuses_workspace_and_handles_alias(libraries, size):
    native = ct.CDLL(str(libraries[1]))
    native.leo_fft_init.argtypes = [ct.POINTER(FFT), ct.c_size_t]
    native.leo_fft_forward.argtypes = [ct.POINTER(FFT), ct.c_void_p]
    native.leo_fft_free.argtypes = [ct.POINTER(FFT)]
    native.leo_fft_backend_identity.restype = ct.c_char_p
    assert native.leo_fft_backend_identity().startswith(b"fftw-")
    fft = FFT()
    assert native.leo_fft_init(ct.byref(fft), size) == 0
    try:
        values = np.random.default_rng(195).normal(size=(size, 2)).view(np.complex128).ravel()
        before = values.copy()
        for _ in range(3):
            native.leo_fft_forward(ct.byref(fft), pointer(values))
            output = np.ctypeslib.as_array(
                ct.cast(fft.output, ct.POINTER(ct.c_double)), shape=(2 * size,)
            ).view(np.complex128)
            np.testing.assert_allclose(output, np.fft.fft(values), rtol=1e-12, atol=1e-12)
            np.testing.assert_array_equal(values, before)
        expected = np.fft.fft(output.copy())
        native.leo_fft_forward(ct.byref(fft), fft.output)
        np.testing.assert_allclose(output, expected, rtol=1e-12, atol=1e-9)
    finally:
        native.leo_fft_free(ct.byref(fft))
    assert not fft.backend_plan and not fft.output and not fft.scratch
    for invalid in (0, 1, 7, 32769):
        assert native.leo_fft_init(ct.byref(fft), invalid) == -1
        native.leo_fft_free(ct.byref(fft))


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("kind", ["noise", "tone", "pilot"])
def test_fractional_detector_matches_builtin_with_original_tolerances(libraries, rate, edge, kind):
    rng = np.random.default_rng(871)
    count = rate // 50
    x = 800 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    if kind == "tone":
        x += 10000 * np.exp(2j * np.pi * (-173123) * np.arange(count) / rate)
    elif kind == "pilot":
        frame = qin_edge_pilot_frame(rate, edge)
        for j in range(15):
            start = 317 + round(j * rate / 750)
            stop = min(count, start + len(frame))
            x[start:stop] += (
                8000
                * frame[: stop - start]
                * np.exp(2j * np.pi * 312345 * np.arange(start, stop) / rate)
            )
    iq = np.rint(np.column_stack((x.real, x.imag))).astype(np.int16)
    values = iq[:, 0].astype(float) + 1j * iq[:, 1]
    outputs = []
    for library in libraries:
        with NativePresence(library, rate, edge) as native:
            result = Result()
            assert (
                native.library.leo_presence_run_ci16(
                    native.workspace, pointer(iq), count, ct.byref(result)
                )
                == 0
            )
            nuisance = native.nuisance()
            del nuisance["cpu_ms"]
            outputs.append((result, nuisance, native.coarse(values)))
    baseline, actual = outputs
    assert baseline[0].candidate_count == actual[0].candidate_count
    fields = (
        "epoch",
        "fractional_complete",
        "tracking_cfo_hz",
        "fractional_offset_samples",
        "exact_score",
        "control_score",
        "margin",
        "acquired_cfo_hz",
    )
    for a, b in zip(
        actual[0].candidates[: actual[0].candidate_count],
        baseline[0].candidates[: baseline[0].candidate_count],
        strict=True,
    ):
        compare_values(
            {name: getattr(a, name) for name in fields}, {name: getattr(b, name) for name in fields}
        )
    compare_values(actual[1], baseline[1], nuisance=True)
    np.testing.assert_allclose(actual[2], baseline[2], rtol=1e-9, atol=1e-12)
