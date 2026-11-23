import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("held_anchor_stationarity")


def packet(anchor_cfo):
    rows = []
    for visit in range(11):
        frequency = anchor_cfo if visit % 8 == 0 else 30_000 + 100 * visit
        for receiver in (0, 1):
            rows.append(dict(visit_index=visit, receiver_id=receiver, channel=2, edge="lower",
                             valid_start_counter=visit * 10_000_000, actual_rf_hz=10_000_000_000.,
                             candidates=[dict(fractional_tracking_cfo_hz=float(frequency), fractional_margin=.09,
                                              candidate_rank=0, passed_fractional_margin_gate=True)]))
    return dict(source=dict(probes=rows, raw_recording_authority_digest="radio"), provenance=dict(
        processed_windows=11, invalid_capture=0, window_count=11))


def test_hidden_anchor_content_cannot_affect_training_or_later_history(audit):
    a, b = packet(5000), packet(55_000)
    b["source"]["probes"][16]["candidates"] = []
    masked, held = audit.erase(a)
    second, same_held = audit.erase(b)
    assert masked == second
    assert held == same_held == [0, 1, 16, 17]
    probes = masked["source"]["probes"]
    assert all(probes[i]["candidates"] == [] for i in held)
    assert len(probes) == 22
    assert audit.history_only(masked) == audit.history_only(second)


def test_track_prediction_requires_bracketing_on_one_piece_and_signed_branch_agreement(audit):
    track = dict(times=np.array([0., 2., 4., 7.]), values=np.array([30., 32., 34., 37.]), pieces=[
        dict(start_s=0., end_s=4., reference_time_s=0., time_scale_s=1., coefficients_hz=(30., 1.)),
        dict(start_s=7., end_s=7., reference_time_s=0., time_scale_s=1., coefficients_hz=(30., 1.))])
    assert audit.nominate(track, [20., 22., 24., 27.], 3., 10., 8.) == (33., 23.)
    assert audit.nominate(track, [20., 22., 14., 27.], 3., 10., 8.) == (33., None)
    assert audit.nominate(track, [20., 22., 24., 27.], 5., 10., 8.) is None
    assert audit.nominate(track, [20., 22., 24., 27.], 3., 10., .25) is None
