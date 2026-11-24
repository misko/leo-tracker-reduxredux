from pathlib import Path
import sys

import pytest


REPORT = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"


def scheduler(monkeypatch):
    monkeypatch.syspath_prepend(str(REPORT))
    from live_stereo_blocks import WholeStereoSchedule

    return WholeStereoSchedule()


def test_whole_blocks_count_short_residues_across_anchors_and_streams(monkeypatch):
    schedule = scheduler(monkeypatch)
    expected = ["full", "short_primary", "short_primary", "skip", "short_primary", "short_primary", "skip", "short_primary",
                "full", "short_primary", "skip", "short_primary", "short_primary", "skip", "short_primary", "short_primary"]
    for index, mode in enumerate(expected):
        # The signed scanner advances only when it presents an admitted window.
        counters = dict(sample_start=index * 100+7, actual_if_center_hz=65.)
        for edge, channel in (("upper", 2), ("lower", 2), ("lower", 4)):
            target = dict(edge=edge, channel=channel, lnb_lo_hz=1e9)
            assert schedule.visit(edge, target, counters) == (index, mode)
    other_rf = dict(sample_start=7, actual_if_center_hz=66.)
    assert schedule.visit("lower", dict(edge="lower", channel=4, lnb_lo_hz=1e9), other_rf) == (0, "full")


def test_whole_blocks_retain_original_order_validation(monkeypatch):
    schedule = scheduler(monkeypatch)
    target = dict(edge="lower", channel=2, lnb_lo_hz=1e9)
    counter = dict(sample_start=2, actual_if_center_hz=65.)
    assert schedule.visit("lower", target, counter) == (0, "full")
    with pytest.raises(ValueError, match="Chronological"):
        schedule.visit("lower", target, counter)
    with pytest.raises(ValueError, match="wrong pilot"):
        schedule.visit("upper", target, dict(counter, sample_start=3))


def test_opt_in_rejects_a_refined_subclass(monkeypatch):
    scheduler(monkeypatch)
    from live_stereo_blocks import bind
    from mixed_aperture_receiver import MixedApertureDetector

    class Wrapped(MixedApertureDetector):
        pass

    with pytest.raises(ValueError, match="unrefined"):
        bind(Wrapped("short.so", "digest"), "sha256:" + "0"*64)
