"""DS22 transfer preserves physical probe ownership and native alias geometry."""

import importlib
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("evaluate_ds22_merged_tracks")


def document():
    candidate = dict(
        candidate_rank=0,
        fractional_tracking_cfo_hz=100.0,
        fractional_margin=0.3,
        integer_epoch_sample=10,
        fractional_epoch_offset_samples=0.1,
        passed_fractional_margin_gate=True,
    )
    probe = dict(
        receiver_id=0,
        channel=1,
        valid_start_counter=100000,
        actual_rf_hz=11e9,
        candidates=[candidate],
    )
    return dict(
        source=dict(session_id="test", probes=[probe], sample_rate_hz=2500000, probe_ms=20),
        clock_anchor=dict(
            sample_counter=0,
            before=dict(realtime_ns=1000000000, monotonic_ns=0),
            after=dict(realtime_ns=1200000000, monotonic_ns=200000000),
        ),
        delivery_clocks=[],
        last_sample_counter=150000,
        provenance={},
    )


def test_multiple_peaks_contribute_only_one_winning_probe(experiment):
    doc = document()
    peak = dict(
        doc["source"]["probes"][0]["candidates"][0],
        candidate_rank=1,
        fractional_margin=0.5,
        fractional_tracking_cfo_hz=900.0,
    )
    doc["source"]["probes"][0]["candidates"].append(peak)
    rows, receipt = experiment.winners(doc)
    assert len(rows) == 1 and rows[0]["measured_cfo_hz"] == 900.0
    assert rows[0]["time_s"] == pytest.approx(0.05)
    assert receipt["anchor_utc_ns"] == 1100000000
    peak["passed_fractional_margin_gate"] = False
    rows, _ = experiment.winners(doc)
    assert len(rows) == 1 and rows[0]["measured_cfo_hz"] == 100.0


def test_probe_identity_does_not_depend_on_winner_or_mark(experiment):
    doc = document()
    first, _ = experiment.winners(doc)
    doc["source"]["probes"][0]["candidates"][0]["fractional_tracking_cfo_hz"] += 500
    second, _ = experiment.winners(doc)
    assert first[0]["observation_id"] == second[0]["observation_id"]
    doc["source"]["probes"][0]["candidates"][0]["passed_fractional_margin_gate"] = False
    assert experiment.winners(doc)[0] == []


def test_duplicate_probe_evidence_fails_closed(experiment):
    doc = document()
    doc["source"]["probes"].append(deepcopy(doc["source"]["probes"][0]))
    with pytest.raises(ValueError):
        experiment.winners(doc)


def test_graph_port_preserves_aliases_and_each_point_once(experiment):
    config = experiment.TrackConfig(max_slope_hz_s=8000)
    rng = np.random.default_rng(13)
    t = np.linspace(0.0, 60.0, 121)
    period = config.alias_spacing_hz
    y = (125000.0 - 1500 * t + rng.normal(0.0, 50.0, len(t)) + period / 2) % period - period / 2
    rows = [
        dict(
            observation_id=str(i),
            receiver=1,
            channel=1,
            time_s=float(t[i]),
            measured_cfo_hz=float(y[i]),
            actual_rf_hz=11e9,
        )
        for i in range(len(t))
    ]
    tracks, assigned = experiment.graph_tracks(rows, "test", config)
    assert assigned / len(rows) > 0.9
    ids = [oid for tr in tracks for oid in tr["observation_ids"]]
    assert len(ids) == len(set(ids)) == assigned
    for track in tracks:
        for oid, value in zip(track["observation_ids"], track["values"], strict=True):
            assert (value - y[int(oid)]) / period == pytest.approx(
                round((value - y[int(oid)]) / period)
            )
    assert all(
        track["quality_status"]
        in ("structure_flagged", "insufficient_support", "no_structure_detected")
        for track in tracks
    )
