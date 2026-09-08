import json

import numpy as np
import pytest

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.evaluate_native_presence_differential import correlation, select_peaks
from tools.native_presence import ROOT, NativePresence, build_library


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("lag", [1, 2, 4])
@pytest.mark.parametrize("bins", [0, 4096])
def test_differential_cfo_invariance_and_sign(rate, lag, bins):
    rng = np.random.default_rng(72)
    samples = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
    template = qin_edge_pilot_frame(rate, "lower").astype(np.complex128)
    original = correlation(samples, template, rate, lag, bins)
    cfo = 198123
    rotated = samples * np.exp(2j * np.pi * cfo * np.arange(len(samples)) / rate)
    actual = correlation(rotated, template, rate, lag, bins)
    np.testing.assert_allclose(
        actual, original * np.exp(2j * np.pi * cfo * lag / rate), atol=1e-12, rtol=1e-9
    )


def test_peak_selection_wraps_and_does_not_flag_constant_scores():
    values = np.zeros(32)
    values[[0, 1, 10, 31]] = [4, 3, 2, 3.5]
    assert select_peaks(values, 1, 8, 5) == [0, 10]
    assert not select_peaks(np.ones(32), 1, 8, 5)


@pytest.fixture(scope="module", params=[1, 0])
def differential_library(tmp_path_factory, request):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-native-differential-v1.json").read_text()
    )
    variant = protocol["variants"][0]
    flags = tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in variant["defines"].items()
    )
    flags += (f"-DLEO_PRESENCE_DIFFERENTIAL_LOCAL_RADIUS={request.param}",)
    return build_library(
        tmp_path_factory.mktemp("native-differential") / "presence.so", cflags=flags
    )


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_native_differential_local_scores_and_invariance(differential_library, rate, edge):
    rng = np.random.default_rng(915)
    samples = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
    template = qin_edge_pilot_frame(rate, edge).astype(np.complex128)
    expected = (
        np.abs(correlation(samples, template, rate, 4))
        + 0.5 * correlation(samples, template, rate, 0).real
    )
    with NativePresence(differential_library, rate, edge) as native:
        grid = native.coarse(samples)
        selected = np.isfinite(grid[5])
        assert 8 <= selected.sum() <= 24
        assert np.all(np.isneginf(np.delete(grid, 5, axis=0)))
        np.testing.assert_allclose(grid[5, selected], expected[selected], rtol=1e-9, atol=1e-12)
        rotated = samples * np.exp(2j * np.pi * 321987 * np.arange(len(samples)) / rate)
        other = native.coarse(rotated)
        np.testing.assert_array_equal(np.isfinite(other), np.isfinite(grid))
        np.testing.assert_allclose(other[5, selected], grid[5, selected], rtol=1e-9, atol=1e-12)
        assert native.run(np.zeros(len(samples))).candidate_count == 0
        assert native.run(np.ones(len(samples))).candidate_count == 0


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("epoch", [0, 1024])
@pytest.mark.parametrize("cfo", [-399999, -110900, 250000, 399999])
def test_native_differential_blind_acquisition_and_full_confirmation(
    differential_library, rate, epoch, cfo
):
    rng = np.random.default_rng(707)
    samples = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
    template = qin_edge_pilot_frame(rate, "upper")
    for frame in range(15):
        start = epoch + round(frame * rate / 750)
        stop = min(len(samples), start + len(template))
        if stop > start:
            samples[start:stop] += (
                20
                * template[: stop - start]
                * np.exp(2j * np.pi * cfo * np.arange(start, stop) / rate)
            )
    with NativePresence(differential_library, rate, "upper") as native:
        result = native.run(samples)
    assert result.candidate_count == 1
    candidate = result.candidates[0]
    assert candidate.fractional_complete and candidate.margin > 0.2
    assert abs(candidate.tracking_cfo_hz - cfo) < 1500
    reference = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=candidate.epoch,
        acquired_cfo_hz=candidate.acquired_cfo_hz,
        edge="upper",
        fractional_epoch_offset_samples=candidate.fractional_offset_samples,
    )
    assert candidate.exact_score == pytest.approx(reference.exact_score, rel=1e-9, abs=1e-10)
    assert candidate.control_score == pytest.approx(reference.control_score, rel=1e-9, abs=1e-10)
