import ctypes as ct

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.differential_pilot import surface
from tools.pipeline_eval.variants.experimental.receiver_adjacent import Adjacent
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.experimental.receiver_tracking import agree
from tools.pipeline_eval.variants.frame_coherence import FRAME, ranked_centers

pytestmark = pytest.mark.fftw


@pytest.fixture
def planted_lane(tmp_path):
    binary = tmp_path / "adjacent.so"
    build(binary, adjacent_primary=True, fma=False)
    edge = "lower"
    synthesis = qin_edge_pilot_frame(30_000_000, edge)
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    noise = np.random.default_rng(8005).integers(-1024, 1025, size=(200000, 2, 2), dtype=np.int16)
    noise[:, 0, :] = 0
    first, _ = unit_wave(synthesis, 400, -308000, 143, False)
    second, _ = unit_wave(synthesis, 17000, 221000, 201, True)
    raw, clips = mix(noise, 1, [(first, 10), (second, -2)])
    assert not clips
    receiver = Adjacent(binary, asset, edge)
    try:
        yield receiver, raw, edge
    finally:
        receiver.close()


def test_single_lane_scout_matches_historical_score(planted_lane):
    receiver, raw, edge = planted_lane
    create = receiver.lib.leo_differential_scout_create
    create.argtypes = []
    create.restype = ct.c_void_p
    destroy = receiver.lib.leo_differential_scout_destroy
    destroy.argtypes = [ct.c_void_p]
    destroy.restype = None
    scout = receiver.lib.leo_differential_scout_lane
    scout.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, *[ct.c_void_p] * 3]
    scout.restype = None
    context = create()
    assert context
    actual = np.empty((2, FRAME), dtype="<f8")
    try:
        for lane in (0, 1):
            scout(context, raw.ctypes.data, lane, receiver.reference_filters.ctypes.data,
                  receiver.reference_energy.ctypes.data, actual[lane].ctypes.data)
    finally:
        destroy(context)
    expected = surface(raw, edge)
    assert not np.any(actual[0])
    assert np.max(abs(actual[1] - expected[1])) < 5e-6 * np.max(abs(expected[1]))
    assert ranked_centers(actual[1], 12) == ranked_centers(expected[1], 12)


def test_signed_confirmation_and_residual_fallback_are_lane_local(planted_lane):
    receiver, raw, _ = planted_lane
    empty, _, silent = receiver.detect(raw, 0, 0, True)
    assert not empty
    assert silent["first_fallback"] == 1 and silent["residual_attempted"] == 0

    exact, *_ = receiver.timed(raw, 1, 0)
    primary, _, trace = receiver.detect(raw, 1, 0, False)
    assert len(exact) == 2
    assert trace["first_confirmed"] == trace["residual_attempted"] == 1
    assert primary[0][3] < 0 and agree(exact[0], primary[0])
    assert all(factor[4] > factor[5] for factor in primary)
    fallback, _, guarded = receiver.detect(raw, 1, 0, True)
    assert len(fallback) == 2
    assert all(agree(a, b) for a, b in zip(exact, fallback, strict=True))
    assert guarded["residual_confirmed"] + guarded["residual_fallback"] == 1
    assert receiver.timed(raw, 1, 0)[0] == exact
