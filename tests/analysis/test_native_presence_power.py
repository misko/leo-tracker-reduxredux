"""Pilot-power proposals and the following full-window fractional confirmation."""

import json

import numpy as np
import pytest

from leo.analysis.research.arm_presence import noise_control
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import ROOT, NativePresence, build_library


@pytest.fixture(
    scope="module", params=[(0, False), (0, True), (4096, False), (4096, True), (2048, True)]
)
def power_library(tmp_path_factory, request):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-power-proposal-v1.json").read_text()
    )
    variant = next(v for v in protocol["variants"] if v["name"] == "power2_f2")
    flags = tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{key}={value}" for key, value in variant["defines"].items()
    )
    bins, limited_complex = request.param
    flags += (f"-DLEO_PRESENCE_POWER_BINS={bins}",)
    if limited_complex:
        flags += ("-fcx-limited-range",)
    return build_library(
        tmp_path_factory.mktemp("power-proposal") / "presence.so", cflags=flags
    ), bins


def power_reference(samples, rate, edge, bins=0):
    n = round(rate / 750)
    folded, support = np.zeros(n), np.zeros(n)
    for frame in range(16):
        start = round(frame * rate / 750)
        count = min(n, len(samples) - start)
        if count <= 0:
            break
        folded[:count] += np.abs(samples[start : start + count]) ** 2
        support[:count] += 1
    folded /= np.maximum(support, 1)
    template = np.abs(np.asarray(qin_edge_pilot_frame(rate, edge), dtype=np.complex128)) ** 2
    folded -= folded.mean()
    template -= template.mean()
    if bins:
        positions = np.arange(bins) * n / bins
        folded = np.interp(positions, np.arange(n), folded, period=n)
        template = np.interp(positions, np.arange(n), template, period=n)
        folded -= folded.mean()
        template -= template.mean()
    scores = np.fft.ifft(np.fft.fft(folded) * np.conj(np.fft.fft(template))).real / (
        np.linalg.norm(folded) * np.linalg.norm(template)
    )
    if bins:
        scores = np.interp(np.arange(n) * bins / n, np.arange(bins), scores, period=bins)
    return scores


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_power_correlation_matches_arbitrary_length_circular_oracle(power_library, rate, edge):
    library, bins = power_library
    samples = noise_control(rate // 50, rate, seed=819, kind="gaussian").astype(np.complex128)
    with NativePresence(library, rate, edge) as native:
        result = native.coarse(samples)
        np.testing.assert_allclose(
            result[5], power_reference(samples, rate, edge, bins), atol=1e-12, rtol=1e-10
        )
        assert np.all(np.isneginf(np.delete(result, 5, axis=0)))
        rotated = samples * np.exp(2j * np.pi * 314159 * np.arange(len(samples)) / rate)
        np.testing.assert_allclose(native.coarse(rotated)[5], result[5], atol=1e-12, rtol=1e-10)
        assert native.run(np.zeros(len(samples))).candidate_count == 0
        assert native.run(np.ones(len(samples))).candidate_count == 0


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("cfo", [-399999, -80000, 250000, 399999])
def test_power_proposal_blind_cfo_and_fractional_confirmation(power_library, rate, cfo):
    library, _ = power_library
    samples = noise_control(rate // 50, rate, seed=990, kind="gaussian").astype(np.complex128)
    template = qin_edge_pilot_frame(rate, "upper")
    for frame in range(15):
        start = 1024 + round(frame * rate / 750)
        stop = min(len(samples), start + len(template))
        if stop > start:
            samples[start:stop] += (
                20
                * template[: stop - start]
                * np.exp(2j * np.pi * cfo * np.arange(start, stop) / rate)
            )
    with NativePresence(library, rate, "upper") as native:
        result = native.run(samples)
    completed = [c for c in result.candidates[: result.candidate_count] if c.fractional_complete]
    assert completed
    assert any(c.margin > 0.2 and abs(c.tracking_cfo_hz - cfo) < 1500 for c in completed)
    for candidate in completed:
        reference = conditioned_glrt64_score(
            samples,
            rate,
            epoch_sample=candidate.epoch,
            acquired_cfo_hz=candidate.acquired_cfo_hz,
            edge="upper",
            fractional_epoch_offset_samples=candidate.fractional_offset_samples,
        )
        assert candidate.exact_score == pytest.approx(reference.exact_score, abs=1e-10, rel=1e-9)
        assert candidate.control_score == pytest.approx(
            reference.control_score, abs=1e-10, rel=1e-9
        )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("seam_offset", [0, -1, -2])
def test_power_proposals_refine_across_circular_seam(power_library, rate, seam_offset):
    library, _ = power_library
    n = round(rate / 750)
    epoch = seam_offset % n
    samples = noise_control(rate // 50, rate, seed=121, kind="gaussian").astype(np.complex128)
    template = qin_edge_pilot_frame(rate, "lower")
    cfo = 101000
    for frame in range(15):
        start = epoch + round(frame * rate / 750)
        stop = min(len(samples), start + len(template))
        if stop > start:
            samples[start:stop] += (
                40
                * template[: stop - start]
                * np.exp(2j * np.pi * cfo * np.arange(start, stop) / rate)
            )
    with NativePresence(library, rate, "lower") as native:
        result = native.run(samples)
    assert any(
        c.fractional_complete
        and c.margin > 0.2
        and min((c.epoch - epoch) % n, (epoch - c.epoch) % n) <= 2
        and abs(c.tracking_cfo_hz - cfo) < 1500
        for c in result.candidates[: result.candidate_count]
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_power_folding_partial_last_frame(power_library, rate):
    library, bins = power_library
    samples = noise_control(rate // 217, rate, seed=811, kind="gaussian").astype(np.complex128)
    with NativePresence(library, rate, "upper") as native:
        scores = native.coarse(samples)
    np.testing.assert_allclose(
        scores[5], power_reference(samples, rate, "upper", bins), atol=1e-12, rtol=1e-10
    )
