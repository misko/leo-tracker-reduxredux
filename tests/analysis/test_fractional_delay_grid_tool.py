from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "prototype_fractional_delay_grid.py"
    spec = importlib.util.spec_from_file_location("prototype_fractional_delay_grid", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_integer_lattice_preserves_rational_3333_3334_cadence() -> None:
    tool = _tool()
    starts = np.asarray([tool._lattice_start(index) for index in range(7)])

    assert np.array_equal(np.diff(starts), [3333, 3334, 3333, 3333, 3334, 3333])
    residual_thirds = np.rint(
        3 * (starts - (tool.ABSOLUTE_EPOCH + np.arange(7) * tool.RATE / tool.FRAME_RATE_HZ))
    ).astype(int)
    assert set(residual_thirds) == {-1, 0, 1}


def test_surface_score_has_unit_ceiling_for_an_exact_scalar_template() -> None:
    tool = _tool()
    matched = np.ones((300, 8), dtype=np.complex128)

    score = tool._surface_one(matched, np.asarray([0.0]), np.asarray([0.0]))

    assert score.shape == (1, 1)
    assert score[0, 0] == pytest.approx(1.0)


def test_windowed_sinc_positive_delay_matches_later_waveform_convention() -> None:
    tool = _tool()
    index = np.arange(256, dtype=float)
    omega = 0.17
    base = np.exp(1j * omega * index)

    delayed = tool._windowed_sinc_shift(base, 0.25)
    expected = np.exp(1j * omega * (index - 0.25))

    assert np.max(np.abs(delayed[32:-32] - expected[32:-32])) < 2e-3


def test_artifact_paths_are_repository_relative() -> None:
    tool = _tool()

    assert tool._repository_path(Path(tool.__file__)) == "tools/prototype_fractional_delay_grid.py"
    with pytest.raises(ValueError):
        tool._repository_path(Path("/tmp/not-in-repository"))
