"""Native decision support, immutable input and independent numerical parity."""

import ctypes as ct
from dataclasses import asdict

import numpy as np
import pytest

from leo.analysis.host_decision import NativeHostDecision
from tools.investigate_adaptive_decision_budget import control_iq
from tools.prepare_decimated_dwell_replay import build, coefficients, reference
from tools.presence_dwell import NativeDwell


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    return build(tmp_path_factory.mktemp("host-decision") / "decision.so", shared=True)


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_independent_filter_and_existing_detector_parity(library, edge):
    iq = np.random.default_rng(481).integers(-3000, 3000, (1200000, 2), dtype=np.int16)
    original = iq.copy()
    filtered = reference(iq, *coefficients("direct"))
    filtered[:40] = 0
    with NativeDwell(library, 2500000, edge, 512) as ref, NativeHostDecision(library) as host:
        expected = ref.run(filtered, maximum=1, seeded=False)
        actual = host.run(iq, edge=edge)
        assert actual.screen_mask == 63
        assert actual.confirmation_mask == expected.confirmation_window_mask
        assert actual.supported_start == 40
        assert actual.supported_end == 300000
        np.testing.assert_array_equal(actual.screen_scores, expected.rank.scores)
        c = expected.confirmations[0].candidates[0]
        assert (actual.epoch, actual.exact_score, actual.margin) == (
            c.epoch, c.exact_score, c.margin,
        )
        host.run(np.zeros_like(iq), edge="upper")
        repeated = host.run(iq, edge=edge)
        for key, value in asdict(actual).items():
            if not key.endswith("_ms"):
                assert asdict(repeated)[key] == value
    np.testing.assert_array_equal(iq, original)


@pytest.mark.parametrize("window,epoch,expected", [
    (0, 0, 0), (0, 39, 0), (0, 41, 0), (0, 42, 1), (0, 3332, 1),
    (1, 0, 1), (5, 0, 1), (6, 42, 0), (0, -1, 0), (0, 3333, 0),
])
def test_fractional_candidate_support_boundary(library, window, epoch, expected):
    native = ct.CDLL(str(library))
    native.leo_host_decision_supported_v1.argtypes = [ct.c_uint32, ct.c_int32]
    assert native.leo_host_decision_supported_v1(window, epoch) == expected


def test_rejects_wrong_rate_geometry_and_closed_workspace(library):
    with NativeHostDecision(library) as host:
        for values in (np.zeros((300000, 2), dtype=np.int16),
                       np.zeros((1200000, 4), dtype=np.int16),
                       np.zeros((1200000, 2), dtype=np.float32)):
            with pytest.raises(ValueError, match="complete"):
                host.run(values, edge="lower")
    with pytest.raises(ValueError, match="closed"):
        host.run(np.zeros((1200000, 2), dtype=np.int16), edge="lower")
    host.close()


@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("window", range(6))
def test_pilot_in_each_temporal_window(library, edge, window):
    iq = control_iq(edge, "pilot", window, 100 + window)
    with NativeHostDecision(library) as host:
        result = host.run(iq, edge=edge)
    assert result.screen_mask == 63
    assert result.confirmation_mask == 1 << window
    assert result.outcome == "detected"
    assert result.candidate_supported and result.fractional_complete
    assert window * 200000 <= result.source_epoch_offset < (window + 1) * 200000


@pytest.mark.parametrize("kind", ["noise", "tone", "alias_tone", "startup_only"])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_negative_and_startup_transient_controls(library, edge, kind):
    iq = control_iq(edge, kind, 0, 301)
    if kind == "startup_only":
        iq.fill(0)
        iq[:160] = np.random.default_rng(120).integers(-32768, 32768, (160, 2), dtype=np.int16)
    with NativeHostDecision(library) as host:
        result = host.run(iq, edge=edge)
    assert result.screen_mask == 63
    assert result.outcome != "detected"
