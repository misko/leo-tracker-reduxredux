"""Direct FFT oracle for energy-selected integer timing support, not RF truth."""

import subprocess

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tests.analysis.test_native_presence_energy_support import libraries as libraries
from tests.analysis.test_native_presence_energy_support import protocol as protocol
from tools.native_presence import NativePresence, build_library
from tools.presence_dwell import unpack
from tools.presence_structured_challenge import generate


def support(values, rate, epoch):
    n = round(rate / 750)
    energies = []
    for frame in range(16):
        start = epoch + round(frame * (rate / 750))
        if start + n + 2 > len(values):
            break
        energies.append(np.sum(abs(values[start : start + n]) ** 2))
    first = int(np.argmax(np.asarray(energies[:-1]) + energies[1:]))
    regions = []
    for frame in (first, first + 1):
        start = epoch + round(frame * (rate / 750))
        powers = [
            np.sum(
                abs(
                    values[
                        start + round(s * rate * 4.4e-6) : start + round((s + 64) * rate * 4.4e-6)
                    ]
                )
                ** 2
            )
            for s in (2, 152)
        ]
        regions.append(int(np.argmax(powers)))
    return first, regions


def oracle_grid(values, rate, edge, epoch, cfo, first, regions):
    templates = [qin_edge_pilot_frame(rate, edge, symbol_roll=r).astype(complex) for r in (0, 17)]
    result = []
    for delta in range(-2, 3):
        local = (epoch + delta) % round(rate / 750)
        spectra, ceilings = np.zeros((2, 512)), np.zeros(2)
        for frame, region in enumerate(regions):
            anchor = local + round((first + frame) * (rate / 750))
            for which, template in enumerate(templates):
                correlations = []
                for symbol in range(2 + 150 * region, 66 + 150 * region):
                    indices = np.arange(
                        round(symbol * rate * 4.4e-6), round((symbol + 1) * rate * 4.4e-6)
                    )
                    correlations.append(
                        np.sum(
                            template[indices].conj()
                            * values[anchor + indices]
                            * np.exp(-2j * np.pi * cfo * indices / rate)
                        )
                    )
                correlations = np.asarray(correlations)
                spectra[which] += abs(np.fft.fft(correlations, 512)) ** 2
                ceilings[which] += np.sum(abs(correlations)) ** 2
        result.append(spectra.max(axis=1) / ceilings)
    return np.asarray(result)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("start", [40.0, 56.0, 58.0])
@pytest.mark.parametrize("artifact", ["symbols", "symbols-uncached"])
def test_fixed_region_lattice_matches_independent_fft(
    libraries, protocol, rate, edge, start, artifact
):
    iq, truth = generate(
        dict(
            rate_hz=rate,
            edge=edge,
            seed=996201,
            kind="pilot",
            snr_db=12.0,
            start_ms=start,
            duration_ms=4.0 if start < 58 else 2.0,
        ),
        protocol,
    )
    section = iq[rate // 25 : rate * 3 // 50].copy()
    before = section.copy()
    values = section[:, 0].astype(float) + 1j * section[:, 1]
    epoch = round(truth["epoch_samples"])
    with NativePresence(libraries[artifact], rate, edge) as native:
        result = unpack(native.confirm(section, epoch))
        assert not native.nuisance()["applied"]
        candidate = result["candidates"][0]
        first, regions = support(values, rate, epoch)
        expected = oracle_grid(
            values, rate, edge, epoch, candidate["acquired_cfo_hz"], first, regions
        )
        np.testing.assert_allclose(candidate["exact_grid"], expected[:, 0], rtol=1e-9, atol=1e-10)
        np.testing.assert_allclose(candidate["control_grid"], expected[:, 1], rtol=1e-9, atol=1e-10)
        assert candidate["fractional_complete"]
        assert abs(candidate["tracking_cfo_hz"] - truth["cfo_hz"]) < 8000
        assert (
            abs(
                candidate["epoch"] + candidate["fractional_offset_samples"] - truth["epoch_samples"]
            )
            / rate
            < 2e-6
        )
        assert native.profile()["fine_frames"] == native.profile()["epoch_frames"] == 2
    np.testing.assert_array_equal(section, before)


@pytest.mark.parametrize(
    "flags",
    [
        ("-DLEO_PRESENCE_ENERGY_SYMBOL_SUPPORT=1",),
        ("-DLEO_PRESENCE_ENERGY_SYMBOL_SUPPORT=2",),
    ],
)
def test_unsupported_symbol_policy_rejected(tmp_path, flags):
    with pytest.raises(subprocess.CalledProcessError):
        build_library(tmp_path / "invalid.so", cflags=flags)
