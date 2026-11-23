from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from exact_noise_gate_0402 import PreparedNoiseScreen, parity
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


@pytest.mark.parametrize("length", [4, 8, 32, 139])
def test_prepared_time_arithmetic_preserves_every_original_bit(length):
    random = np.random.default_rng(401)
    times = np.cumsum(random.uniform(0.1, 4, size=length))
    residual = random.normal(0, 120, size=(6, length))
    residual[0] = 0.
    residual[1] += 15000.
    residual[2] *= 1e-8
    screen = PreparedNoiseScreen(times)
    for sample in (residual, np.asfortranarray(residual), residual[:1], residual[:, ::-1]):
        parity(screen(sample), batch_noise_screen(sample, times))


def test_same_lengths_do_not_share_prepared_time_geometry():
    tracks = np.asarray([0, 1, 2, 3, 4, 8, 10, 19], float)
    shifted = tracks ** 2
    residual = np.asarray([0., 27., 277., -400., 716., 160., 110., 310.])[None, :]
    original, other = PreparedNoiseScreen(tracks), PreparedNoiseScreen(shifted)
    parity(original(residual), batch_noise_screen(residual, tracks))
    parity(other(residual), batch_noise_screen(residual, shifted))
    assert original(residual)["slope_z"][0] != other(residual)["slope_z"][0]


def test_invalid_time_and_residual_are_visible():
    with pytest.raises(ValueError, match="positive time span"):
        PreparedNoiseScreen(np.zeros(6))
    with pytest.raises(ValueError, match="matching finite"):
        PreparedNoiseScreen(np.arange(6))(np.full((1, 6), np.nan))
