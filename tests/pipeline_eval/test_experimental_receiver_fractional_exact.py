import ctypes as ct
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tests.pipeline_eval.test_experimental_receiver_phase_free import invoke
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental import (
    receiver_fractional_exact,
    receiver_phase_free_overlay,
)
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.verifier_integration import FRAC_COMPLETE


pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    work = tmp_path_factory.mktemp("absolute-fractional-verifier")
    original = receiver_phase_free_overlay.verifier_overlay
    measurement = receiver_phase_free_overlay.measurement_overlay
    paths = {arm: work / f"{arm}.so" for arm in ("stock", "exact", "selected")}
    build(paths["stock"], fftw=False, fma=False, pack_stencil=True)
    for arm in ("exact", "selected"):
        defer = arm == "selected"

        def verifier(source, defer=defer):
            return receiver_fractional_exact.overlay(original(source), defer=defer)

        def receiver(source, defer=defer):
            source = measurement(source)
            return receiver_fractional_exact.deferred_measurement(source) if defer else source

        with (
            patch.object(receiver_phase_free_overlay, "verifier_overlay", side_effect=verifier),
            patch.object(receiver_phase_free_overlay, "measurement_overlay", side_effect=receiver),
        ):
            build(paths[arm], fftw=False, fma=False, pack_stencil=True, phase_free=True)
    return paths


@pytest.mark.parametrize(
    "epoch,hz,lane", [(0, -358000., 0), (714, 238000., 1), (13331, 381010., 0)],
)
def test_absolute_scores_match_stock_with_zero_and_nonzero_residuals(binaries, epoch, hz, lane):
    iq = np.random.default_rng(173).integers(-300, 301, (200_000, 2, 2), dtype=np.int16)
    pilot = qin_edge_pilot_frame(30_000_000, "upper")
    wave, _ = unit_wave(pilot, 3 * epoch + 1, hz, 143, False)
    planted, clipped = mix(iq, lane, [(wave, 9)])
    assert not clipped
    jobs = [(epoch, hz), (epoch, hz + 2500.), (epoch, hz), (epoch, hz - 2500.)]

    stock = invoke(binaries["stock"], planted, lane, jobs)
    exact = invoke(binaries["exact"], planted, lane, jobs)
    assert list(map(bytes, exact)) == list(map(bytes, stock))
    assert all(row.flags & FRAC_COMPLETE for row in exact)
    assert exact[0].fractional_residual_hz == 0.
    assert exact[1].fractional_residual_hz < 0.
    assert exact[3].fractional_residual_hz > 0.
    stock = invoke(binaries["stock"], planted, lane, jobs, diagnostic=True)
    exact = invoke(binaries["exact"], planted, lane, jobs, diagnostic=True)
    assert list(map(bytes, exact)) == list(map(bytes, stock))


def test_deferred_repair_uses_its_lane_then_invalidates_state(binaries):
    rng = np.random.default_rng(681)
    iq = rng.integers(-45, 46, (200_000, 2, 2), dtype=np.int16)
    edge = "upper"
    pilot = qin_edge_pilot_frame(30_000_000, edge)
    primary, _ = unit_wave(pilot, 865, -117_310., 812, False)
    secondary, _ = unit_wave(pilot, 7682, 261_701., 912, False)
    iq, clipped = mix(iq, 0, [(primary, 14), (secondary, 9)])
    assert not clipped
    templates = [qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll).view("<f4")
                 for roll in (0, CONTROL_SYMBOL_ROLL)]
    asset = np.concatenate([*templates, coefficients(4), pilot.view("<f4")]).astype("<f4")
    with ExitStack() as stack:
        receivers = {arm: Receiver(binaries[arm], asset) for arm in ("stock", "selected")}
        for receiver in receivers.values():
            stack.callback(receiver.close)
        deferred = receivers["selected"]
        repair = deferred.lib.experimental_repair_fractional_selection
        repair.restype, repair.argtypes = ct.c_int, [ct.c_void_p, ct.POINTER(Factor)]
        stock = receivers["stock"].timed(iq, 0, 0.)[0]
        actual = deferred.timed(iq, 0, 0.)[0]
        assert len(stock) == len(actual) == 2
        assert [f[:4] for f in actual] == [f[:4] for f in stock]
        for approximate, exact in zip(actual, stock, strict=True):
            row = Factor(*approximate)
            assert repair(deferred.ctx, ct.byref(row)) == 1
            assert bytes(row) == bytes(Factor(*exact))

        assert deferred.timed(np.zeros_like(iq), 1, 41_000.)[0] == ()
        stale = Factor(*actual[0])
        assert repair(deferred.ctx, ct.byref(stale)) == -1
