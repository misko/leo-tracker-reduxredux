"""The FP32 experiment has a separate grid tolerance, never a relaxed oracle."""

import json
from dataclasses import asdict

import numpy as np
import pytest

from leo.analysis.research.arm_presence import fresh_glrt, noise_control
from leo.analysis.starlink import acquisition
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import ROOT, NativePresence, build_library
from tools.qualify_native_presence import compare


@pytest.fixture(scope="module")
def fp32_library(tmp_path_factory):
    return build_library(
        tmp_path_factory.mktemp("presence-fp32") / "presence.so",
        cflags=("-DLEO_PRESENCE_COARSE_FP32",),
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_fp32_grid_against_separately_frozen_precision_gate(fp32_library, rate, edge):
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-fp32-experiment-v1.json").read_text()
    )
    samples = noise_control(rate // 50, rate, seed=123, kind="gaussian").astype(np.complex128)
    expected = acquisition._folded_anchor_score_grid(
        samples,
        np.asarray(qin_edge_pilot_frame(rate, edge), dtype=np.complex128),
        rate,
        tuple(range(-400_000, 400_001, 80_000)),
        acquisition.DEFAULT_ANCHOR_SYMBOLS,
        round(rate / 750),
    )
    with NativePresence(fp32_library, rate, edge) as native:
        actual = native.coarse(samples)
    np.testing.assert_allclose(
        actual, expected, atol=protocol["coarse_grid_atol"], rtol=protocol["coarse_grid_rtol"]
    )


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("kind", ["gaussian", "tone_noise"])
def test_fp32_final_candidates_keep_original_frozen_gate(fp32_library, rate, edge, kind):
    protocol = json.loads((ROOT / "config/analysis/arm-presence-native-v1.json").read_text())
    samples = noise_control(rate // 50, rate, seed=712341, kind=kind)
    expected = [asdict(c) for c in fresh_glrt(samples, rate, edge=edge, candidate_count=2)]
    with NativePresence(fp32_library, rate, edge) as native:
        result = native.run(samples)
    actual = [
        {
            name: getattr(c, name)
            for name in (
                "epoch",
                "fractional_complete",
                "acquired_cfo_hz",
                "tracking_cfo_hz",
                "fractional_offset_samples",
                "exact_score",
                "margin",
            )
        }
        for c in result.candidates[: result.candidate_count]
    ]
    compare(actual, expected, protocol["numerical_tolerances_frozen_before_native_results"])


def test_fp32_zero_and_scale_invariance(fp32_library):
    samples = noise_control(50000, 2_500_000, seed=812, kind="gaussian").astype(np.complex128)
    with NativePresence(fp32_library, 2_500_000, "lower") as native:
        assert native.run(np.zeros(50000)).candidate_count == 0
        expected = native.coarse(samples)
        for scale in (1e-200, 1e8):
            np.testing.assert_allclose(
                native.coarse(samples * scale), expected, atol=2e-6, rtol=2e-5
            )


def test_unrepresentable_fp32_normalization_is_error_not_negative(fp32_library):
    samples = np.full(50000, 1e-50 + 1e-50j, dtype=np.complex128)
    samples[-1] = 1
    with NativePresence(fp32_library, 2_500_000, "lower") as native:
        with pytest.raises(ValueError, match="rejected"):
            native.run(samples)
        with pytest.raises(ValueError, match="rejected"):
            native.coarse(samples)
