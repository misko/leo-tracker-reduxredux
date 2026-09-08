"""Native component qualification; C compiler required, no RF or archive needed."""

import ctypes as ct
import hashlib
import json
import subprocess

import numpy as np
import pytest

from leo.analysis.research.arm_presence import fresh_glrt, noise_control
from leo.analysis.starlink import acquisition
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import (
    NativePresence,
    Result,
    build_executable,
    build_library,
    pointer,
    write_probe,
)


@pytest.fixture(scope="module", params=["default", "portable"])
def library(tmp_path_factory, request):
    flags = ("-DLEO_PRESENCE_FORCE_PORTABLE",) if request.param == "portable" else ()
    return build_library(
        tmp_path_factory.mktemp("native-presence") / "presence.so", cflags=flags
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_coarse_grid_matches_existing_kernel(library, rate, edge):
    values = noise_control(rate // 50, rate, seed=123, kind="gaussian").astype(np.complex128)
    template = np.asarray(qin_edge_pilot_frame(rate, edge), dtype=np.complex128)
    expected = acquisition._folded_anchor_score_grid(
        values,
        template,
        rate,
        tuple(range(-400_000, 400_001, 80_000)),
        acquisition.DEFAULT_ANCHOR_SYMBOLS,
        round(rate / 750),
    )
    with NativePresence(library, rate, edge) as native:
        actual = native.coarse(values)
    np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=1e-12)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("offset", [0, -0.39, 0.27, 1.31])
def test_fractional_glrt_matches_existing_scorer(library, rate, edge, offset):
    samples = noise_control(rate // 50, rate, seed=87, kind="gaussian")
    expected = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=347,
        acquired_cfo_hz=12345.5,
        edge=edge,
        fractional_epoch_offset_samples=offset,
    )
    with NativePresence(library, rate, edge) as native:
        actual = native.glrt(samples, 347, 12345.5, offset)
    np.testing.assert_allclose(
        actual[:2], [expected.exact_score, expected.control_score], atol=1e-10, rtol=1e-9
    )
    assert actual[2] == pytest.approx(expected.residual_cfo_hz, rel=0, abs=0.001)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("kind", ["gaussian", "tone_noise"])
def test_complete_glrt2_matches_python_oracle(library, rate, edge, kind):
    values = noise_control(rate // 50, rate, seed=712341, kind=kind)
    expected = fresh_glrt(values, rate, edge=edge, candidate_count=2)
    with NativePresence(library, rate, edge) as native:
        result = native.run(values)
    actual = [c for c in result.candidates[: result.candidate_count] if c.fractional_complete]
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert a.epoch == e.epoch_sample
        assert a.acquired_cfo_hz == pytest.approx(e.acquired_cfo_hz, rel=0, abs=0.001)
        assert a.fractional_offset_samples == pytest.approx(
            e.fractional_offset_samples, rel=0, abs=1e-7
        )
        assert a.tracking_cfo_hz == pytest.approx(e.tracking_cfo_hz, rel=0, abs=0.001)
        np.testing.assert_allclose(
            [a.exact_score, a.margin], [e.exact_score, e.margin], atol=1e-10, rtol=1e-9
        )
        assert (a.margin >= 0.025) == e.passed
    assert result.total_cpu_ms >= result.coarse_cpu_ms + result.fine_cpu_ms


def test_zero_invalid_and_closed_inputs(library):
    with NativePresence(library, 2_500_000, "lower") as native:
        assert native.run(np.zeros(50000)).candidate_count == 0
        for invalid in [np.zeros(5), np.zeros(50001), np.full(50000, np.nan), np.ones((2, 50000))]:
            with pytest.raises(ValueError):
                native.run(invalid)
    native.close()
    with pytest.raises(ValueError, match="closed"):
        native.run(np.zeros(50000))
    with pytest.raises(ValueError, match="initialization"):
        NativePresence(library, 3_000_000, "lower")


def test_ci16_matches_float_entrypoint(library):
    rng = np.random.default_rng(83)
    iq = rng.integers(-32768, 32768, (50000, 2), dtype=np.int16)
    samples = iq[:, 0].astype(float) + 1j * iq[:, 1]
    with NativePresence(library, 2_500_000, "lower") as native:
        expected = native.run(samples)
        actual = Result()
        assert (
            native.library.leo_presence_run_ci16(
                native.workspace, pointer(iq), len(iq), ct.byref(actual)
            )
            == 0
        )
    assert actual.candidate_count == expected.candidate_count
    for a, e in zip(actual.candidates, expected.candidates, strict=True):
        assert bytes(a) == bytes(e)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_all_acquisition_candidates_including_unbracketed(library, rate, edge):
    samples = noise_control(rate // 50, rate, seed=712341, kind="tone_noise").astype(np.complex128)
    expected = acquisition.acquire_symbolwise(
        samples,
        rate,
        acquisition.ReceiverFrequencyCalibration("research", 0, "0" * 64),
        edge=edge,
        config=acquisition.SymbolwiseAcquisitionConfig(
            maximum_probe_samples=len(samples),
            retained_candidate_count=2,
            candidate_epoch_separation_samples=5,
            candidate_cfo_separation_hz=10000,
        ),
    )
    with NativePresence(library, rate, edge) as native:
        result = native.run(samples)
    assert result.candidate_count == len(expected.candidates)
    for a, e in zip(result.candidates[: result.candidate_count], expected.candidates, strict=True):
        assert a.epoch == e.refined_epoch_sample
        assert a.acquired_cfo_hz == pytest.approx(e.absolute_cfo_hz, rel=0, abs=0.001)
        np.testing.assert_allclose(
            [
                a.coarse_score,
                a.acquire_score,
                a.verify_score,
                a.verify_control_score,
                a.conditioned_score,
            ],
            [
                e.coarse_score,
                e.acquire_score,
                e.verify_score,
                e.conditioned_control_score,
                e.conditioned_exact_score,
            ],
            rtol=1e-9,
            atol=1e-10,
        )


@pytest.mark.parametrize("rate,cfo,epoch", [(2_500_000, -399999, 0), (5_000_000, 399999, 6666)])
def test_known_pilot_signal_at_search_boundaries(library, rate, cfo, epoch):
    template = qin_edge_pilot_frame(rate, "upper")
    samples = noise_control(rate // 50, rate, seed=97, kind="gaussian").astype(np.complex128)
    for frame in range(15):
        start = epoch + round(frame * rate / 750)
        stop = min(len(samples), start + len(template))
        if stop > start:
            samples[start:stop] += (
                8
                * template[: stop - start]
                * np.exp(2j * np.pi * cfo * np.arange(start, stop) / rate)
            )
    samples = samples.astype(np.complex64)
    expected = fresh_glrt(samples, rate, edge="upper", candidate_count=2)
    with NativePresence(library, rate, "upper") as native:
        result = native.run(samples)
    actual = [c for c in result.candidates[: result.candidate_count] if c.fractional_complete]
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert a.epoch == e.epoch_sample
        assert a.acquired_cfo_hz == pytest.approx(e.acquired_cfo_hz, rel=0, abs=0.001)
        assert a.fractional_offset_samples == pytest.approx(
            e.fractional_offset_samples, rel=0, abs=1e-7
        )
        assert a.margin == pytest.approx(e.margin, abs=1e-10, rel=1e-9)


def test_standalone_counter_and_malformed_probe(tmp_path):
    executable = build_executable(tmp_path / "replay")
    receipt = json.loads((tmp_path / "replay.build.json").read_text())
    assert receipt["binary_sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert receipt["sources_sha256"]["src/leo/analysis/native_presence/presence.c"]
    assert receipt["sources_sha256"]["src/leo/analysis/starlink/_native_acquisition_grid.inc"]
    assert receipt["compiler_version"]
    assert receipt["command"][-1] == str(executable)
    with pytest.raises(FileExistsError):
        build_executable(executable)
    probe = tmp_path / "input.probe"
    write_probe(probe, np.zeros(50000), 2_500_000, "lower", 10**16 + 23)
    result = subprocess.run(
        [str(executable), str(probe), "2"], check=True, capture_output=True, text=True
    )
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 2
    assert all(r["device_counter"] == str(10**16 + 23) and r["candidates"] == [] for r in rows)
    assert subprocess.run([str(executable), str(probe), "21"], capture_output=True).returncode == 2
    truncated = tmp_path / "truncated.probe"
    truncated.write_bytes(probe.read_bytes()[:-16])
    assert (
        subprocess.run([str(executable), str(truncated), "1"], capture_output=True).returncode == 2
    )
    with pytest.raises(FileExistsError):
        write_probe(probe, np.zeros(50000), 2_500_000, "lower")


def test_build_rejects_existing_receipt_and_unknown_compiler(tmp_path):
    receipt = tmp_path / "replay.build.json"
    receipt.write_text("existing evidence")
    with pytest.raises(FileExistsError):
        build_executable(tmp_path / "replay")
    assert receipt.read_text() == "existing evidence"
    assert not (tmp_path / "replay").exists()
    with pytest.raises(FileNotFoundError):
        build_library(tmp_path / "library.so", compiler="/not-a-compiler")


@pytest.mark.parametrize("size", [2, 5, 10, 25, 50, 125, 128, 512, 5000, 10000])
def test_bounded_fft_matches_numpy(library, size):
    class FFT(ct.Structure):
        _fields_ = [
            ("size", ct.c_size_t),
            ("roots", ct.c_void_p),
            ("output", ct.c_void_p),
            ("scratch", ct.c_void_p),
        ]

    native = ct.CDLL(str(library))
    native.leo_fft_init.argtypes = [ct.POINTER(FFT), ct.c_size_t]
    native.leo_fft_forward.argtypes = [ct.POINTER(FFT), ct.c_void_p]
    native.leo_fft_forward.restype = None
    native.leo_fft_free.argtypes = [ct.POINTER(FFT)]
    native.leo_fft_free.restype = None
    fft = FFT()
    assert native.leo_fft_init(ct.byref(fft), size) == 0
    try:
        rng = np.random.default_rng(18)
        values = rng.normal(size=size) + 1j * rng.normal(size=size)
        native.leo_fft_forward(ct.byref(fft), pointer(values))
        result = np.ctypeslib.as_array(
            ct.cast(fft.output, ct.POINTER(ct.c_double)), shape=(size * 2,)
        ).view(np.complex128)
        np.testing.assert_allclose(result, np.fft.fft(values), rtol=1e-12, atol=1e-12)
    finally:
        native.leo_fft_free(ct.byref(fft))
    assert native.leo_fft_init(ct.byref(fft), 7) == -1
    native.leo_fft_free(ct.byref(fft))
