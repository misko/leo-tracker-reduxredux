from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def trial(monkeypatch):
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(reports))
    return import_module("residual_prefix_trial")


def test_prefix_includes_exclusions_in_the_scheduled_boundary(trial, monkeypatch):
    requested = []
    samples = np.zeros((200_000, 2, 2), dtype="<i2")
    target = dict(channel=4, edge="upper", rf_center_hz=990_000_010, lnb_lo_hz=0)

    class Source:
        receiver_ids = (0, 1)
        reader = SimpleNamespace(manifest=SimpleNamespace(sample_rate_hz=10_000_000))

        def __init__(self, segment, *, stop_sequence):
            self.stop = stop_sequence
            requested.append((segment, stop_sequence))

        def windows(self):
            for i in range(self.stop):
                yield SimpleNamespace(
                    acquisition=dict(global_visit=i, sample_start=i * 5_000_000,
                                     actual_if_center_hz=990_000_000),
                    target=target, iq_sha256=f"test-{i}", samples=samples,
                    sample_rate_hz=10_000_000,
                )

    monkeypatch.setattr(trial, "FastSegmentSource", Source)
    monkeypatch.setattr(
        trial, "valid_window_support", lambda acq, *_: acq["global_visit"] not in (0, 191),
    )
    segment = {"manifest_digest": "a sealed segment"}
    rows, excluded, source_sha = trial.sealed_prefix(segment)
    assert requested == [(segment, 192)]
    assert excluded == [0, 191]
    assert len(rows) == 380
    assert [(row["visit_index"], row["receiver_id"]) for row, _, _ in rows] == [
        (visit, lane) for visit in range(1, 191) for lane in (0, 1)
    ]
    assert all(center == 10 and iq is samples for _, center, iq in rows)
    assert source_sha == trial.canonical_digest([(i, f"test-{i}") for i in range(192)])


@pytest.mark.parametrize("error", [None, "order", "rank_zero"])
def test_both_native_entries_are_validated_in_original_factor_order(trial, monkeypatch, error):
    raw = (0, 200, .3, -8000., .4, .1)
    residual = (1, 180, .1, 22000., .7, .1)
    full = residual, raw

    class Receiver:
        def __init__(self, *_):
            pass

        def timed(self, *_):
            return full, 0, 0

        def close(self):
            pass

    class Scheduled(Receiver):
        def timed(self, *_):
            return (full[::-1] if error == "order" else full), 0, 0

        def timed_primary(self, *_):
            return (() if error == "rank_zero" else (raw,)), 0, 0

    monkeypatch.setattr(trial, "Receiver", Receiver)
    monkeypatch.setattr(trial, "ScheduledReceiver", Scheduled)
    inputs = [({"receiver_id": 0}, 0., None)]
    if error:
        with pytest.raises(ValueError, match="entry changed"):
            trial.observe(None, None, None, inputs)
    else:
        assert trial.observe(None, None, None, inputs) == [(*inputs[0], full)]
