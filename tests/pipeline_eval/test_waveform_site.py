"""Verify the simulated Qin samples and blind qualification's scientific joins."""

import numpy as np
import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import waveform_site_interior as interior
from tools.pipeline_eval.qualification import waveform_site_model as model
from tools.pipeline_eval.qualification import waveform_site_results as scores
from tools.pipeline_eval.qualification import waveform_site_trial as trial
from tools.pipeline_eval.variants.compact_tile_interior import guard


def planted():
    return dict(
        epoch=3.25,
        period=13333.28,
        amplitude=1100,
        norad=123,
        actual_cfo_hz=23_000,
        cfo_model_hz=23_000,
        slope_hz_s=-109.0,
        catalogue_mismatch_hz=-30.5,
    )


def test_waveform_reproducible_dual_ci16_and_emission_is_lane_local():
    visits = model.schedule()
    assert len(visits) == 1200
    assert {x["channel"] for x in visits[:8]} == set(range(1, 9))
    assert {x["edge"] for x in visits[:8]} == {"lower", "upper"}
    assert all(
        right["relative_counter"] - left["relative_counter"] >= model.SAMPLES
        for left, right in zip(visits, visits[1:], strict=False)
    )
    assert visits[-1]["relative_counter"] + model.SAMPLES < 300 * model.RATE
    frame = model.pulse_bank()["lower"]
    info = dict(tone_hz=56_000.0, tone_amplitude=90.0, sample_seed=42)
    profile = dict(sample_rate_truth_hz=model.RATE)
    sig = model.iq(dict(info, planted=[None, planted()]), profile, frame)
    identical = model.iq(dict(info, planted=[None, planted()]), profile, frame)
    null = model.iq(dict(info, planted=[None, None]), profile, frame)
    assert sig.shape == (200_000, 2, 2) and sig.dtype == np.dtype("<i2")
    np.testing.assert_array_equal(sig, identical)
    np.testing.assert_array_equal(sig[:, 0], null[:, 0])
    assert np.count_nonzero(sig[:, 1] != null[:, 1]) > 1000


def test_planted_hit_tracks_stock_winner_and_modulo_alias():
    plant = planted()
    candidate = dict(
        candidate_rank=1,
        integer_epoch_sample=13337,
        fractional_epoch_offset_samples=-0.45,
        fractional_tracking_cfo_hz=plant["cfo_model_hz"] - scores.ALIAS_HZ + 9,
        fractional_margin=0.4,
        passed_fractional_margin_gate=True,
    )
    assert scores.residual(candidate, plant) == pytest.approx((0.02, 9))
    bad = dict(candidate, candidate_rank=0, fractional_tracking_cfo_hz=68_000)
    p = dict(visit_index=0, channel=1, actual_rf_hz=11e9, candidates=[bad, candidate])
    v = dict(visit=0, channel=1, rf_hz=11e9, planted=[plant, None])
    record = dict(
        visit=0,
        nbytes=1_600_000,
        probes=[dict(p, receiver_id=0), dict(p, receiver_id=1)],
        generation_cpu_s=0.01,
        detector_cpu_s=0.04,
    )
    result, rows = scores.detection_score([record], [v])
    assert result["counts"]["winner_hits"] == 0
    assert result["counts"]["any_candidate_hits"] == 1
    assert result["counts"]["no_emission_gate_positives"] == 1
    assert rows[0]["winner_hit"] is False
    with pytest.raises(ValueError, match="duplicate visit"):
        scores.detection_score([record, record], [v])


def test_scoring_retains_timeout_and_does_not_accept_changed_input_digest():
    containing, omitted = [9.0, 76.0], [9 + 14 / 111, 76.0]
    priv = dict(
        scene=dict(
            coordinate=containing,
            offers={"containing": containing, "omitted": omitted},
            conditions={"first": "containing", "second": "omitted"},
        )
    )
    requests = [
        dict(id=ident, tile=xy, native_sha256="a" * 64, catalog_sha256="b" * 64)
        for ident, xy in (("first", containing), ("second", omitted))
    ]
    predictions = [
        dict(
            id=r["id"],
            method=trial.METHOD,
            result=trial.no_estimate("timed_out", "test timeout"),
            input_sha256=trial.raw_digest(encoded(r)),
            native_sha256=r["native_sha256"],
            catalogue_sha256=r["catalog_sha256"],
            worker_wall_s=225.0,
            worker_cpu_s=None,
            peak_rss_kib=None,
        )
        for r in requests
    ]
    rows, queries = scores.position_rows(predictions, requests, priv)
    assert len(rows) == 4 and len(queries) == 2
    assert {r["arm"] for r in rows} == {"c0", "fitted_c"}
    assert all(r["position_error_km"] is None and r["status"] == "timed_out" for r in rows)
    predictions[1]["input_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="scientific request"):
        scores.position_rows(predictions, requests, priv)


def test_interior_replay_compares_both_forced_endpoints_and_frequency():
    center = [10.0, 77.0]
    marginless = [10 + 12.5 / 111, 77.0]
    raw = dict(
        status="ok",
        boundary="installed receiver",
        metrics=dict(stage_s={"initial": 2.0}, tracks=12),
        arms={
            "c0": dict(latlon=marginless, rf_rms_hz=10.0),
            "fitted_c": dict(latlon=center, rf_rms_hz=9.0),
        },
    )
    installed = guard(raw, dict(center=center, width_km=25))
    installed["metrics"]["stage_s"] = {"initial": 3.0}
    assert installed["status"] == "withheld"
    assert interior.exact_parity(installed, raw, {"tile": center}) is True
    installed["arms"]["fitted_c"]["rf_rms_hz"] = 9.2
    assert interior.exact_parity(installed, raw, {"tile": center}) is False
