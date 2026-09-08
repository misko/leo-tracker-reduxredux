"""Independent direct-FFT oracle for the default-off final-symbol experiment."""

import math

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import NativePresence, build_library


@pytest.fixture(scope="module", params=[0, 1])
def library(tmp_path_factory, request):
    return build_library(
        tmp_path_factory.mktemp("presence-diversity") / "presence.so",
        cflags=(
            "-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1",
            f"-DLEO_PRESENCE_PRECOMPUTE={request.param}",
        ),
    )


def oracle(samples, rate, edge, epoch, cfo, offset):
    templates = [
        qin_edge_pilot_frame(rate, edge, symbol_roll=roll).astype(complex) for roll in (0, 17)
    ]
    spectra = np.zeros((2, 512))
    ceilings = np.zeros(2)
    integer = abs(offset - round(offset)) <= 1e-12
    starts = []
    for frame in range(16):
        anchor = epoch + round(frame * (rate / 750))
        symbol = 152 if frame % 2 else 2
        last = round((symbol + 64) * rate * 4.4e-6) - 1
        if symbol != 2 and anchor + last + offset >= len(samples) - (0 if integer else 8):
            symbol = 2
            last = round(66 * rate * 4.4e-6) - 1
        if anchor + last + offset >= len(samples) - (0 if integer else 8):
            break
        first = round(symbol * rate * 4.4e-6)
        if anchor + first + offset < (0 if integer else 7):
            break
        starts.append(symbol)
        cells = np.arange(first, last + 1)
        positions = anchor + cells + offset
        if integer:
            received = samples[np.rint(positions).astype(int)]
        else:
            indices = np.floor(positions).astype(int)[:, None] + np.arange(-7, 9)
            distances = positions[:, None] - indices
            weights = np.sinc(distances) * np.sinc(distances / 8)
            received = np.sum(samples[indices] * weights, axis=1) / weights.sum(axis=1)
        corrected = received * np.exp(-2j * np.pi * cfo * (cells + offset) / rate)
        for which, template in enumerate(templates):
            correlations = []
            for index in range(symbol, symbol + 64):
                begin, end = (round(s * rate * 4.4e-6) for s in (index, index + 1))
                correlations.append(
                    np.sum(template[begin:end].conj() * corrected[begin - first : end - first])
                )
            correlations = np.asarray(correlations)
            ceilings[which] += np.sum(np.abs(correlations)) ** 2
            spectra[which] += np.abs(np.fft.fft(correlations, 512)) ** 2
    best = np.argmax(spectra, axis=1)
    scores = np.divide(spectra[np.arange(2), best], ceilings, out=np.zeros(2), where=ceilings > 0)
    residual = (best[0] if best[0] < 256 else best[0] - 512) / (512 * 4.4e-6)
    return np.array([*scores, residual if ceilings[0] > 0 else 0]), starts


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("offset", [0.0, 0.375, -1.25])
@pytest.mark.parametrize("short", [False, True])
def test_diverse_final_score_matches_independent_fft_and_fractional_sampler(
    library, rate, edge, offset, short
):
    rng = np.random.default_rng(99881)
    size = math.ceil(rate / 375) if short else rate // 50
    samples = rng.normal(size=size) + 1j * rng.normal(size=size)
    epoch = round(0.65 * rate / 750) if short else 317
    expected, starts = oracle(samples, rate, edge, epoch, 173123.0, offset)
    with NativePresence(library, rate, edge) as native:
        actual = native.glrt(samples, epoch, 173123.0, offset)
    np.testing.assert_allclose(actual[:2], expected[:2], rtol=1e-9, atol=1e-10)
    assert actual[2] == pytest.approx(expected[2], rel=0, abs=0.001)
    assert starts[:2] == ([2, 2] if short else [2, 152])


def test_cached_regions_survive_cfo_offset_and_execution_mode_changes(library):
    rng = np.random.default_rng(99882)
    iq = rng.integers(-2000, 2000, (50000, 2), dtype=np.int16)
    samples = iq[:, 0].astype(float) + 1j * iq[:, 1]
    with NativePresence(library, 2500000, "lower") as native:
        for cfo, offset in ((0.0, 0.0), (173123.0, 0.375), (-173123.0, -1.25), (0.0, 0.0)):
            native.confirm(iq, 317)  # Two-frame early lattice followed by diverse final scoring.
            expected, _ = oracle(samples, 2500000, "lower", 317, cfo, offset)
            actual = native.glrt(samples, 317, cfo, offset)
            np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-10)
