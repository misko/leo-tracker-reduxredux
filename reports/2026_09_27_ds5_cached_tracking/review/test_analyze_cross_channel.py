import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "cross_channel", Path(__file__).with_name("analyze_cross_channel.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(visit, channel, *, positive=True, epoch=10.0, cfo=1000.0):
    return {
        "session_id": "s", "visit_index": visit, "rx": 0, "rate_hz": 2_500_000,
        "edge": "lower", "channel": channel, "start_counter": visit * 300_000,
        "reference_positive": positive,
        "reference": {"window": 0, "epoch_samples": epoch, "cfo_hz": cfo},
    }


def test_cross_channel_prior_requires_timing_and_cfo_compatibility():
    result = m.audit([
        row(0, 1),
        row(1, 2),
        row(2, 3, cfo=20_000),
        row(3, 4, epoch=30.0),
    ])
    counts = result["counts"]
    assert counts["reference_positives"] == 4
    assert counts["with_cross_channel_timing_prior"] == 2
    assert counts["with_cross_channel_timing_and_cfo_prior"] == 1


def test_expired_and_negative_rows_never_enter_bank():
    result = m.audit([
        row(0, 1),
        row(1, 2, positive=False),
        row(20, 3),
    ], max_age_seconds=.5)
    assert result["counts"].get("with_any_prior_positive", 0) == 0
