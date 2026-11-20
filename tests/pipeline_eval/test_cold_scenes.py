from datetime import UTC, datetime

import numpy as np
import pytest
from sgp4.api import Satrec

from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import cold_scenes as scenes
from tools.pipeline_eval.variants.folded_doppler import observations


def test_retarded_range_rate_agrees_with_light_time_derivative():
    satellite = Satrec.twoline2rv(
        "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991",
        "2 25544  51.6445 211.2001 0007413  17.6667  85.6398 15.50103472202482",
    )
    stamp = scenes._stamp(datetime(2019, 12, 9, 18, tzinfo=UTC))
    observer = geodetic_to_ecef_km(30.0, 25.0, 0.0)
    delay, rate = scenes._signal(satellite, stamp, np.array([15.05, 15.1, 15.15]), observer)
    derivative = (delay[2] - delay[0]) * scenes.LIGHT_KM_S / 0.1
    assert derivative == pytest.approx(rate[1], abs=0.001)
    assert np.all(delay > 0)


def test_delaying_a_frame_increases_its_epoch_modulo_the_nominal_period():
    offset = 0.002
    delay = np.array([0.00193, 0.001931])
    clock = scenes.RATE * (1 + 2.0e-7)
    code = scenes._relative_epoch(delay, 0.000058, offset, clock, 1_000_000, 0.114)
    period = scenes.RATE / scenes.FRAME_HZ
    delta = (code[1] - code[0] + period / 2) % period - period / 2
    assert delta == pytest.approx(clock * 1e-6, abs=0.003)
    peak = scenes._peak(1, 0.75 * scenes.CFO_ALIAS_HZ, code[0], 0.32)
    assert peak["fractional_tracking_cfo_hz"] == pytest.approx(-0.25 * scenes.CFO_ALIAS_HZ)
    assert peak["integer_epoch_sample"] + peak["fractional_epoch_offset_samples"] == code[0]


def test_control_shuffles_only_within_an_occupied_receiver_band():
    probes = [
        dict(
            receiver_id=i % 2,
            channel=1 + (i % 3),
            probe_index=i,
            candidates=[i] if i % 7 else [],
        )
        for i in range(40)
    ]
    shuffled = scenes._shuffled(probes, np.random.default_rng(7757))
    assert any(a["candidates"] != b["candidates"] for a, b in zip(probes, shuffled, strict=True))
    for original, output in zip(probes, shuffled, strict=True):
        assert original["probe_index"] == output["probe_index"]
        assert bool(original["candidates"]) == bool(output["candidates"])
        for origin in output["candidates"]:
            assert probes[origin]["receiver_id"] == output["receiver_id"]
            assert probes[origin]["channel"] == output["channel"]


def test_public_probe_times_use_counter_within_authorized_capture():
    rate = scenes.RATE
    first = 1024
    slots = range(0, scenes.SECONDS * 1000 - scenes.PROBE_MS + 1, scenes.SLOT_MS)
    probes = [
        scenes._probe_row(index, rx, index % 8, first + ms * rate // 1000, [])
        for index, ms in enumerate(slots)
        for rx in range(2)
    ]
    for p in (probes[0], probes[-1]):
        p["candidates"] = [scenes._peak(1, 1050, 30.1, 0.3)]
    duration = float(scenes.SECONDS)
    probe_ms = scenes.PROBE_MS
    scenes._check_probe_times(probes, first, rate, probe_ms, duration)
    capture = scenes.NativeCapture(
        "unscored-preflight", probes, rate, probe_ms, first, 0, 0, 0, duration, b"", "", ""
    )
    points, _ = observations(capture)
    assert points.points["t"].tolist() == pytest.approx([0.010, 299.986])
    probes[-1]["probe_start_ms"] = slots[-1]
    with pytest.raises(ValueError, match="outside"):
        scenes._check_probe_times(probes, first, rate, probe_ms, duration)
    with pytest.raises(ValueError, match="outside"):
        observations(capture)
