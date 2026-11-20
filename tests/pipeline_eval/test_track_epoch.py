import math

import pytest

from tools.pipeline_eval.qualification import track_timing_trial as trial
from tools.pipeline_eval.variants import track_epoch
from tools.pipeline_eval.variants.coherent_peak_filter import Peak, wrapped

RATE = 10_000_000
RF = 11_250_000_000
PERIOD = RATE / 750


@pytest.mark.parametrize("slope", [5000.0, -5000.0])
def test_signed_doppler_and_integer_counter_phase(slope):
    start = 2**55 + 73
    intervals = (0, 5_000_001, 13_000_002)

    def plant(i):
        elapsed = intervals[i] / RATE
        phase = 13_331 + 145 * elapsed - RATE * slope * elapsed**2 / (2 * RF)
        local = (phase - track_epoch.counter_phase(intervals[i], RATE)) % PERIOD
        return Peak(i, start + intervals[i], local, 380_000 + slope * elapsed)

    a, b, target = map(plant, range(3))
    actual = track_epoch.predict(a, b, target.counter, RATE, RF)
    assert abs(wrapped(actual.doppler_samples - target.epoch, PERIOD)) < 1e-8
    assert abs(wrapped(actual.linear_samples - target.epoch, PERIOD)) > 1
    assert abs(actual.first_rate_ppm) < 50


def test_empty_or_unequally_spaced_history_and_bad_rf():
    a, b = Peak(1, 0, 20, 100), Peak(2, RATE, 30, 100)
    assert track_epoch.predict(a, b, b.counter, RATE, RF) is None
    assert track_epoch.predict(a, b, b.counter + RATE // 3, RATE, RF) is None
    with pytest.raises(ValueError, match="frequencies"):
        track_epoch.predict(a, b, 2 * RATE, RATE, math.nan)


def test_permutation_preserves_all_forecasts_and_rf_lanes():
    def row(i, channel, history):
        return dict(
            receiver=0,
            channel=channel,
            rf=RF,
            edge="upper",
            block=0,
            counter=i,
            target=str(i),
            observed_samples=10 * i,
            linear_samples=10 * i + 1,
            doppler_samples=10 * i,
            first_rate_ppm=history,
        )

    rows = [row(1, 1, 0), row(2, 1, 0), row(3, 1, 51), row(4, 2, 0)]
    trial.score(rows, RATE)
    assert [x["null_target"] for x in rows] == ["2", "3", "1", None]
    stats = trial.summarize(rows)
    assert (stats["history_pass"], stats["comparable"]) == (3, 2)
    assert stats["linear_within_1"] == stats["doppler_within_2"] == 2
    assert stats["shuffle_within_2"] == 0
    assert stats["admission_criterion"]


def test_history_gate_counts_misses_and_empty_common_panel():
    assert not trial.summarize([])["admission_criterion"]
    assert trial.summarize([])["shuffle_median_samples"] is None


def test_sealed_observations_are_never_overwritten(tmp_path):
    pin = tmp_path / "prediction-lock.json"
    pin.write_bytes(b"preserve these bytes")
    with pytest.raises(FileExistsError, match="already sealed"):
        trial.run(tmp_path, tmp_path / "absent-archive")
    assert pin.read_bytes() == b"preserve these bytes"


def test_native_receiver_ids_are_mapped_to_graph_lanes_and_clock_is_authenticated():
    sample = dict(
        candidate_rank=0,
        passed_fractional_margin_gate=True,
        fractional_margin=1.0,
        integer_epoch_sample=4,
        fractional_epoch_offset_samples=0.2,
        fractional_tracking_cfo_hz=600.0,
    )
    probe = dict(
        valid_start_counter=4000,
        receiver_id=11,
        channel="2",
        actual_rf_hz=RF,
        edge="lower",
        visit_index=0,
        candidates=[sample],
    )
    other = dict(probe, receiver_id=7, candidates=[])
    source = dict(session_id="one", sample_rate_hz=RATE, probe_ms=20, probes=[probe, other])
    doc = dict(source=source, clock_anchor={"sample_counter": 4000})
    track = dict(
        ids=[trial.observation_id("one", probe)],
        times_s=[0.01],
        graph_cfo_hz=[600.0],
        receiver=2,
        channel=2,
    )
    records, count = trial.opportunities(doc, {"tracks": [track]})
    assert records == [] and count["graph_owned"] == 1
    track["times_s"] = [0.04]
    with pytest.raises(ValueError, match="clock"):
        trial.opportunities(doc, {"tracks": [track]})
