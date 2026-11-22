from contextlib import ExitStack
from importlib import import_module

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.experimental.receiver_covariance_overlay import build_probe
from tools.pipeline_eval.variants.experimental.receiver_covariance_trial import (
    ProbeReceiver,
    compare,
)


def test_spectral_bound_does_not_bound_local_relative_coherence():
    frames = np.eye(14, dtype=complex)
    template = frames[0].conj()
    eigenvalues = np.linalg.eigvalsh(frames @ frames.conj().T)
    projections = frames @ template
    assert eigenvalues[-1] / eigenvalues.sum() == pytest.approx(1 / 14)
    assert np.vdot(projections, projections).real == eigenvalues[-1]
    assert abs(projections[0])**2 / np.vdot(frames[0], frames[0]).real == 1


def test_factor_loss_is_attributed_to_the_native_pass_even_under_rank_ordering():
    primary = (0, 11, 0., -300000., .11, .03)
    residual = (1, 34, .1, 200000., .2, .02)
    frozen = dict(factors=(residual, primary), selected=residual, votes=[5, 1], passes=[])
    candidate = dict(factors=(primary,), selected=None, votes=[1], passes=[dict(skipped=1)])
    result = compare(frozen, candidate)
    assert result["lost_residual"] == 1 and result["lost_primary"] == 0
    assert result["selected_changed"] and result["votes_changed"]


def test_exact_factor_comparison_preserves_the_bit_pattern():
    primary = (0, 11, 0., -300000., .11, .03)
    signed_zero = (0, 11, -0., -300000., .11, .03)
    frozen = dict(factors=(primary,), selected=primary, votes=[3], passes=[])
    candidate = dict(factors=(signed_zero,), selected=signed_zero, votes=[3], passes=[])
    result = compare(frozen, candidate)
    assert result["changed_lanes"] and result["selected_changed"]


def test_linked_selection_loss_is_retained_against_a_published_continuation():
    study = import_module("reports.ALGO08.single-core-2x.receiver_covariance_confirmation")
    factor = (0, 27, .12, 100000., .2, .03)
    candidate = dict(zip((
        "candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
        "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score",
    ), factor, strict=True))
    rows = [dict(visit_index=i, receiver_id=0, channel=1, actual_rf_hz=12e9,
                 valid_start_counter=i * 2_000_000, candidates=[candidate]) for i in range(4)]
    group = {"rows": [dict(visit=3, lane=0, probe=dict(
        receiver_id=0, valid_start_counter=6_000_000, actual_rf_hz=12e9, channel=1,
    ), arms={arm: {"factors": () if arm == "primary" else (factor,)} for arm in study.ARMS})]}
    replay = study.link_publication(group, 3, {"rows": rows}, [rows[3]])
    assert replay["selected"] == {"frozen": 1, "control": 1, "primary": 0}
    assert replay["differences"] == [dict(
        arm="primary", visit=3, lane=0, publication=factor, trial=None,
    )]


@pytest.mark.hardware
def test_probe_keeps_frozen_factors_and_can_isolate_primary_from_residual(tmp_path):
    frozen, instrumented = tmp_path / "frozen.so", tmp_path / "probe.so"
    build(frozen, pack_stencil=True)
    build_probe(instrumented)
    edge = "lower"
    synthesis = qin_edge_pilot_frame(30_000_000, edge)
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    noise = np.random.default_rng(8005).integers(-100, 101, size=(200000, 2, 2), dtype=np.int16)
    first, _ = unit_wave(synthesis, 400, -308000, 143, False)
    second, _ = unit_wave(synthesis, 17000, 221000, 201, True)
    samples, clips = mix(noise, 1, [(first, -4), (second, -8)])
    assert clips == 0

    with ExitStack() as stack:
        oracle = Receiver(frozen, asset)
        probe = ProbeReceiver(instrumented, asset)
        stack.callback(oracle.close)
        stack.callback(probe.close)
        reference, *_ = oracle.timed(samples, 1, 0.)
        control, _, _, passes = probe.observe(samples, 1, 0.)
        assert {factor[0] for factor in reference} == {0, 1}
        assert control == reference and len(passes) == 2
        for row in passes:
            assert row["trace"] > 0
            assert 1 / 14 <= row["largest"] <= row["leading_pair"] <= 1
            assert row["prefix_ns"] >= row["covariance_ns"] > 0
        residual_only, _, _, residual_passes = probe.observe(samples, 1, 0., 2, (1., 1.))
        assert residual_only == tuple(factor for factor in reference if factor[0] == 0)
        assert [row["skipped"] for row in residual_passes] == [0, 1]
        none, _, _, primary_pass = probe.observe(samples, 1, 0., 1, (1., 1.))
        assert not none and [row["skipped"] for row in primary_pass] == [1]
        silence = np.zeros_like(samples)
        none, _, _, silent_pass = probe.observe(silence, 1, 0., 1, (1., 1.))
        assert not none and silent_pass[0]["trace"] == silent_pass[0]["skipped"] == 0
