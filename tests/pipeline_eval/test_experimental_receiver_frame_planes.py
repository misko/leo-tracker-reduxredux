from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(scope="module")
def modes(tmp_path_factory):
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(reports))
        trial = import_module("reports.ALGO08.single-core-2x.receiver_frame_planes_trial")
    return trial, trial.mode_fixture(tmp_path_factory.mktemp("frame-planes"))


@pytest.mark.hardware
@pytest.mark.parametrize(("stride", "width"), [(4, 4740), (1, 18964)])
def test_both_ordered_modes_are_byte_equal(modes, stride, width):
    trial, fixture = modes
    if not fixture.have_avx2():
        pytest.skip("AVX2 is required to exercise the packed frame planes")
    rng = np.random.default_rng(5811)
    data = rng.standard_normal(2 * (200_000 // stride), dtype=np.float32)
    data[::17] = -0.
    result = trial.run_modes(fixture, data, stride, width, 1)
    assert result["output_sha256"]


@pytest.mark.hardware
def test_tied_eigenvalues_preserve_mode_selection(modes):
    trial, fixture = modes
    if not fixture.have_avx2():
        pytest.skip("AVX2 is required to exercise the packed frame planes")
    data = np.full(100_000, 3.5, dtype=np.float32)
    data[1::2] = -81.
    reference = np.zeros(4 * 4740, dtype=np.float32)
    result = trial.run_modes(fixture, data, 4, 4740, 1)
    assert result["output_sha256"] == trial.digest(reference.tobytes())


def test_nonmultiple_width_falls_back(modes):
    trial, fixture = modes
    data = np.arange(100_000, dtype=np.float32)
    assert trial.run_modes(fixture, data, 4, 4741, 1)["output_sha256"]
