from dataclasses import replace

import numpy as np
import pytest
from adapter import Window
from evaluate import evaluate

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from tools.native_presence import NativePresence, build_library


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    return build_library(tmp_path_factory.mktemp("iter128-capability") / "native.so")


@pytest.mark.parametrize("rate", [2_500_000, 10_000_000])
@pytest.mark.parametrize("edge,offset", [("lower", 0), ("upper", 0.27)])
def test_actual_native_fractional_geometry(library, rate, edge, offset):
    rng = np.random.default_rng(128)
    x = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
    oracle = conditioned_glrt64_score(
        x,
        rate,
        epoch_sample=37,
        acquired_cfo_hz=12345,
        edge=edge,
        fractional_epoch_offset_samples=offset,
    )
    window = Window(
        "synthetic",
        0,
        0,
        0,
        37,
        offset,
        12345,
        oracle.tracking_cfo_hz,
        oracle.exact_score,
        oracle.control_score,
        True,
        edge,
    )
    if rate == 10_000_000:
        with pytest.raises(ValueError, match="initialization rejected"):
            NativePresence(library, rate, edge)
        result = evaluate(x, window, rate)
        assert result["scorer_kind"] == "original-python-conditioned-scorer"
        assert result["parity"] == "passed"
        return
    with NativePresence(library, rate, edge) as native:
        result = evaluate(x, window, rate, native=native)
        assert result["parity"] == "passed"
        assert result["original_passed"] is True
        with pytest.raises(ValueError, match="CFO parity"):
            evaluate(
                x, replace(window, original_cfo_hz=window.original_cfo_hz + 1), rate, native=native
            )
