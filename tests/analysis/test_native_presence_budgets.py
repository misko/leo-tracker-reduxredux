"""Reduced acquisition is explicit; final scoring still sees the original IQ."""

import json
import struct
import subprocess

import numpy as np
import pytest

from leo.analysis.research.arm_presence import noise_control
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.evaluate_native_presence_budgets import associated
from tools.native_presence import ROOT, NativePresence, build_executable, build_library, write_probe


@pytest.fixture(scope="module")
def sparse_library(tmp_path_factory):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-budget-experiment-v1.json").read_text()
    )
    variant = next(v for v in protocol["variants"] if v["name"] == "sparse2_narrow")
    flags = tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{key}={value}" for key, value in variant["defines"].items()
    )
    return build_library(tmp_path_factory.mktemp("sparse-presence") / "presence.so", cflags=flags)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_sparse_grid_and_explicit_profile(sparse_library, rate, edge):
    samples = noise_control(rate // 50, rate, seed=441, kind="gaussian")
    stride = 2 * (rate // 2_500_000)
    with NativePresence(sparse_library, rate, edge) as native:
        profile = native.profile()
        assert profile["epoch_stride"] == stride
        assert profile["coarse_frames"] == profile["fine_frames"] == profile["epoch_frames"] == 2
        assert profile["anchor_stride"] == 3
        assert profile["conditioned_radius_hz"] == 200
        grid = native.coarse(samples)
        assert np.all(np.isfinite(grid[:, ::stride]))
        for offset in range(1, stride):
            assert np.all(np.isneginf(grid[:, offset::stride]))
        assert native.run(np.zeros(len(samples))).candidate_count == 0
    with pytest.raises(ValueError, match="closed"):
        native.profile()


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_full_confirmation_is_not_shortened_with_acquisition(sparse_library, rate, edge):
    samples = noise_control(rate // 50, rate, seed=314, kind="gaussian").astype(np.complex128)
    template = qin_edge_pilot_frame(rate, edge)
    for frame in range(15):
        start = 1024 + round(frame * rate / 750)
        stop = min(len(samples), start + len(template))
        if start < stop:
            samples[start:stop] += (
                20
                * template[: stop - start]
                * np.exp(2j * np.pi * 80000 * np.arange(start, stop) / rate)
            )
    changed = samples.copy()
    tail = rate // 200  # First 5 ms covers every two-frame acquisition hypothesis.
    changed[tail:] = 30 * noise_control(len(samples) - tail, rate, seed=273, kind="gaussian")
    with NativePresence(sparse_library, rate, edge) as native:
        first = native.run(samples)
        second = native.run(changed)
    a = [c for c in first.candidates[: first.candidate_count] if c.fractional_complete]
    b = [c for c in second.candidates[: second.candidate_count] if c.fractional_complete]
    assert a and len(a) == len(b)
    for before, after in zip(a, b, strict=True):
        assert before.epoch == after.epoch
        assert before.acquired_cfo_hz == after.acquired_cfo_hz
        assert before.fractional_offset_samples == after.fractional_offset_samples
        reference = conditioned_glrt64_score(
            changed,
            rate,
            epoch_sample=after.epoch,
            acquired_cfo_hz=after.acquired_cfo_hz,
            edge=edge,
            fractional_epoch_offset_samples=after.fractional_offset_samples,
        )
        assert after.exact_score == pytest.approx(reference.exact_score, rel=1e-9, abs=1e-10)
    assert max(c.margin for c in a) > max(c.margin for c in b) + 0.1


def test_profile_wire_format_is_separate_and_legacy_still_works(tmp_path):
    executable = build_executable(tmp_path / "presence")
    probe = tmp_path / "zero.probe"
    write_probe(probe, np.zeros(50000), 2_500_000, "lower", 10**16 + 91)
    cases = (
        ([], "native-presence-replay-v1"),
        (["--profile"], "native-presence-replay-profile-v1"),
    )
    for extra, schema in cases:
        row = json.loads(
            subprocess.run(
                [str(executable), str(probe), "1", *extra],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        assert row["schema"] == schema
        assert row["device_counter"] == str(10**16 + 91)
        assert ("profile" in row) == bool(extra)
        if extra:
            assert row["profile"]["epoch_stride"] == 1
    with pytest.raises(subprocess.CalledProcessError):
        build_library(tmp_path / "invalid.so", cflags=("-DLEO_PRESENCE_FINE_FRAMES=1",))


def test_reference_association_requires_both_frequency_and_timing():
    policy = {"maximum_cfo_difference_hz": 8000, "maximum_circular_epoch_difference_us": 2}
    expected = {"epoch_sample": 0, "fractional_offset_samples": 0.1, "tracking_cfo_hz": 10000}
    actual = {"epoch": 3333, "fractional_offset_samples": 0.2, "tracking_cfo_hz": 11000}
    assert associated(actual, expected, 2_500_000, policy)
    assert not associated({**actual, "tracking_cfo_hz": 30000}, expected, 2_500_000, policy)
    assert not associated({**actual, "epoch": 100}, expected, 2_500_000, policy)


def test_ci16_probe_writer_is_lossless_and_preserves_counter(tmp_path):
    rate, counter = 2500000, 10**16 + 17
    values = np.full(rate // 50, -32768 + 32767j)
    path = tmp_path / "integer.probe"
    write_probe(path, values, rate, "upper", counter, ci16=True)
    data = path.read_bytes()
    assert struct.unpack_from("<4sIIIIQ", data) == (b"LPR1", rate, 1, len(values), 2, counter)
    raw = np.frombuffer(data, dtype="<i2", offset=28 + 32 * round(rate / 750)).reshape(-1, 2)
    np.testing.assert_array_equal(raw[:, 0], values.real)
    np.testing.assert_array_equal(raw[:, 1], values.imag)
    for invalid in (0.5, 32768, -32769, np.inf, np.nan):
        with pytest.raises(ValueError, match="exactly representable"):
            write_probe(
                tmp_path / "invalid.probe", np.full(len(values), invalid), rate, "upper", ci16=True
            )
        assert not (tmp_path / "invalid.probe").exists()
