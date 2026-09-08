import json
import subprocess

import numpy as np
import pytest

from leo.analysis.research.tone_nuisance import remove_stationary_tone
from tools.native_presence import ROOT, NativePresence, build_executable, build_library, write_probe


def flags():
    protocol = json.loads((ROOT / "config/analysis/arm-presence-native-tone-v1.json").read_text())
    variant = protocol["variants"][0]
    return tuple(protocol["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in variant["defines"].items()
    )


@pytest.fixture(scope="module", params=["recursive", "iterative", "blocked"])
def libraries(tmp_path_factory, request):
    directory = tmp_path_factory.mktemp("native-tone")
    selected = flags() + (
        ("-DLEO_PRESENCE_ITERATIVE_FFT=1",) if request.param == "iterative" else ()
    )
    if request.param == "blocked":
        selected += ("-DLEO_PRESENCE_ITERATIVE_FFT=1", "-DLEO_PRESENCE_TONE_BLOCKED=1")
    native = build_library(directory / "tone.so", cflags=selected)
    plain = build_library(
        directory / "plain.so", cflags=tuple(x for x in selected if "LEO_PRESENCE_TONE_" not in x)
    )
    return native, plain


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("amplitude", [0, 0.3, 1, 6])
def test_native_tone_fit_matches_python_conditioned_detector(libraries, rate, edge, amplitude):
    rng = np.random.default_rng(781)
    values = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
    values += amplitude * np.exp(2j * np.pi * (-277123) * np.arange(len(values)) / rate)
    original = values.copy()
    cleaned, fit = remove_stationary_tone(values, rate)
    with (
        NativePresence(libraries[0], rate, edge) as native,
        NativePresence(libraries[1], rate, edge) as plain,
    ):
        result, reference = native.run(values), plain.run(cleaned)
        evidence = native.nuisance()
        assert evidence["enabled"] and bool(evidence["applied"]) == fit.applied
        assert evidence["frequency_hz"] == pytest.approx(fit.frequency_hz or 0, abs=0.001)
        assert evidence["spectral_fraction"] == pytest.approx(fit.spectral_fraction, abs=1e-10)
        assert evidence["fitted_power_fraction"] == pytest.approx(
            fit.fitted_power_fraction, abs=1e-10
        )
        assert not plain.nuisance()["enabled"]
        assert result.candidate_count == reference.candidate_count
        for got, want in zip(
            result.candidates[: result.candidate_count],
            reference.candidates[: reference.candidate_count],
            strict=True,
        ):
            assert got.epoch == want.epoch and got.fractional_complete == want.fractional_complete
            assert got.acquired_cfo_hz == pytest.approx(want.acquired_cfo_hz, abs=0.001)
            assert got.fractional_offset_samples == pytest.approx(
                want.fractional_offset_samples, abs=1e-7
            )
            assert got.exact_score == pytest.approx(want.exact_score, rel=1e-9, abs=1e-10)
            assert got.control_score == pytest.approx(want.control_score, rel=1e-9, abs=1e-10)
        assert native.run(np.zeros(len(values))).candidate_count == 0
        assert not native.nuisance()["applied"]
        with pytest.raises(ValueError):
            native.run(values[: len(values) // 2])
    np.testing.assert_array_equal(values, original)


def test_nuisance_wire_is_separate_from_existing_profiles(tmp_path):
    binary = build_executable(tmp_path / "native", cflags=flags())
    probe = tmp_path / "zero.probe"
    write_probe(probe, np.zeros(50000), 2500000, "lower", 10**16 + 51, ci16=True)
    for detail, schema in (
        ("--profile", "native-presence-replay-profile-v1"),
        ("--nuisance", "native-presence-nuisance-replay-v1"),
    ):
        row = json.loads(
            subprocess.run(
                [str(binary), str(probe), "1", detail], check=True, capture_output=True, text=True
            ).stdout
        )
        assert row["schema"] == schema
        assert ("nuisance" in row) == (detail == "--nuisance")
        assert row["device_counter"] == str(10**16 + 51)
