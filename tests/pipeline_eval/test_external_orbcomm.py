"""Component contracts for attributed VHF replay and frequency identifiability."""

import numpy as np
import pytest

from tools.pipeline_eval.qualification import external_orbcomm_availability as availability
from tools.pipeline_eval.qualification import external_orbcomm_clock_trial as replay
from tools.pipeline_eval.qualification import external_orbcomm_trial as trial
from tools.pipeline_eval.variants import external_orbcomm as base
from tools.pipeline_eval.variants import external_orbcomm_clock as clock


def test_causal_contract_requires_earlier_epoch_use_and_archive_collection():
    start = trial.date_ns("07-04-2026 00:00:00.000000")
    cutoff = start - trial.OLD_NS
    safe = dict(norad=12, epoch_ns=cutoff - 5, first_used_ns=cutoff - 1, tle=["old", "orbit"])
    seen_late = dict(safe, epoch_ns=cutoff - 2, first_used_ns=cutoff + 1, tle=["new", "orbit"])
    future = dict(safe, epoch_ns=cutoff + 1, tle=["future", "orbit"])
    history = dict(older=safe, seen_late=seen_late, future=future)
    assert trial.earlier(history, start, 12) == "older"
    packet = dict(
        satellite_id=12,
        data_source="celestrak",
        tle_line1="old",
        tle_line2="orbit",
        date_collected="2026-04-06 16:01:10 UTC",
    )
    assert availability.confirmed([packet], safe, cutoff)["available_before_cutoff"]
    assert replay.causal_bank(history, {"12": [packet]}, cutoff) == {12: "older"}
    assert (
        replay.causal_bank(
            history, {"12": [dict(packet, date_collected="2026-04-06 18:01:10 UTC")]}, cutoff
        )
        == {}
    )


def test_trace_thinning_retains_exact_native_values_and_reports_duplicate_time():
    times = (np.arange(81) * 2 * 10**9).tolist()
    records = [(t, i * 2.0, "original") for i, t in enumerate(times)]
    [(trace, coincide, count)] = trial.passes(records, "older", 12, 137e6)
    assert count == 81 and coincide == 0 and len(trace["cfo_hz"]) == 40
    assert trace["times_ns"][0] == times[0] and trace["times_ns"][-1] == times[-1]
    assert all(y == float(t) / 1e9 for t, y in zip(trace["times_ns"], trace["cfo_hz"], strict=True))
    with pytest.raises(ValueError, match="duplicated"):
        trial.passes([*records, records[0]], "older", 12, 137e6)


def artificial(point, slope, common, *, offset):
    rng = np.random.default_rng(offset)
    n, count = 20, 6
    groups = np.repeat(np.arange(count), n)
    rf = np.repeat(137.5e6 + np.linspace(-220_000, 280_000, count), n)
    sat = base.geodetic_to_ecef_km(*point, 0.0)
    base_rays = np.column_stack(
        (np.full(count, 700), rng.normal(0, 200, count), rng.normal(0, 120, count))
    )
    velocities = rng.normal(0, 4, size=(count, 3))
    times = np.tile(np.linspace(-90, 90, n), count)
    v = velocities[groups]
    relative = base_rays[groups] + times[:, None] * v
    y = -rf / base.LIGHT_KM_S * np.sum(relative * v, axis=1) / np.linalg.norm(relative, axis=1)
    y += common + slope * (rf - 137.5e6) / 1e6
    reversed_y = y.reshape(count, n)[:, ::-1].ravel()
    return base.Observations(relative + sat, v, rf, y, groups, reversed_y, count, (12, 13, 14))


def test_shared_offset_captures_cross_pass_rf_column_accepted_by_design():
    point = [40.0, 2.0]
    panel = artificial(point, 20, 17, offset=932)
    assert max(abs(panel.project(panel.rf_hz - 137.5e6))) == 0.0
    assert np.linalg.norm(clock.anchored(panel, point, c=20.0)) < 1e-8
    assert np.linalg.norm(clock.anchored(panel, point, c=0.0)) > 1
    assert clock.relative_leverage(panel, point) > clock.MIN_RF_RELATIVE_NORM


def test_held_model_transfers_training_slope_instead_of_refitting_it():
    point = [40.0, 2.0]
    center = base.geographic(point, [6.4, 0])
    train, held = artificial(point, 20, 17, offset=932), artificial(point, -6, -8, offset=344)
    model = clock.shared_fit(train, held, center, estimate=True)
    assert model["c_hz_per_mhz"] == pytest.approx(20, abs=1e-6)
    assert model["receiver_offset_hz"] == pytest.approx(17, abs=1e-6)
    assert model["forced_latlon"] == pytest.approx(point, abs=1e-7)
    assert model["held_rms_hz"] > 3
