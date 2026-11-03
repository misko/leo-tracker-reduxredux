"""Native predictor parity, boundary conditions, and planted pilot checks.

These host tests explicitly require a C compiler, failing if it is unavailable.
"""
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tools.fast8_cfo_free_checks import prepare_bank, template_features
from tools.fast8_pilot_predictor import PilotPredictor, pilot_period


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    out = tmp_path_factory.mktemp("pilot") / "fold.so"
    source = Path(__file__).parents[2] / "tools/fast8_pilot_fold.c"
    subprocess.run(["cc", "-O3", "-fPIC", "-shared", "-ffp-contract=off",
                    "-Wall", "-Wextra", "-Werror", str(source), "-o", str(out)], check=True)
    return out


@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("receivers", [1, 2])
def test_native_matches_reference_for_full_scale_noise_and_pilot(library, edge, receivers):
    rng = np.random.default_rng(51)
    predictor = PilotPredictor(library, edge, receivers)
    bank = prepare_bank(pilot_period(edge), pilot_period(edge, 17), (1,))
    noise = rng.integers(-32768, 32768, (50000, receivers, 2), dtype=np.int16)
    period = pilot_period(edge)
    x = np.tile(np.roll(period, 217), 5)
    for cfo in (-400000, 0, 400000):
        shifted = x * np.exp(2j * np.pi * cfo * np.arange(50000) / 2500000)
        planted = np.empty_like(noise)
        planted[:, :, 0] = np.rint(shifted.real[:, None] * 3000).astype(np.int16)
        planted[:, :, 1] = np.rint(shifted.imag[:, None] * 3000).astype(np.int16)
        for raw in (noise, planted):
            actual = predictor.score_ci16(raw)
            for rx in range(receivers):
                z = raw[:, rx, 0].astype(float) + 1j * raw[:, rx, 1]
                expected = template_features(z, bank)
                assert actual[rx]["epoch_sample"] == expected["epoch_sample"]
                for key in ("exact", "control", "margin"):
                    assert actual[rx][key] == pytest.approx(expected[key], abs=2e-12)
            if raw is planted:
                assert actual[0]["epoch_sample"] == 217
                assert actual[0]["margin"] > .8


def test_zero_constant_rails_reuse_and_bad_geometry(library):
    predictor = PilotPredictor(library, "lower")
    for value in (0, 32767, -32768):
        raw = np.full((50000, 2, 2), value, dtype=np.int16)
        for _ in range(2):
            assert all(r["margin"] == 0 for r in predictor.score_ci16(raw))
    raw[25000, 0, 0] += 1  # Nearly constant: must not lose centered energy.
    bank = prepare_bank(pilot_period("lower"), pilot_period("lower", 17), (1,))
    expected = template_features(raw[:, 0, 0].astype(float)+1j*raw[:, 0, 1], bank)
    assert predictor.score_ci16(raw)[0]["margin"] == pytest.approx(expected["margin"], abs=2e-12)
    for bad in (raw[:-1], raw.astype(float), raw[:, ::-1]):
        with pytest.raises(ValueError):
            predictor.score_ci16(bad)
    with pytest.raises(ValueError):
        PilotPredictor(library, "invalid")
    with pytest.raises(ValueError):
        PilotPredictor(library, "lower", 3)
