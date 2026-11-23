import importlib
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def cycle(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("anchor_cycle_route")


def signed_packet(anchor_positive):
    rows = []
    for visit in range(26):
        channel = 2 + visit % 2
        slot = visit // 2 % 8
        for receiver in (0, 1):
            measured = slot == 0 and anchor_positive or 1 <= slot <= (3 if receiver == 0 else 7)
            factor = dict(fractional_tracking_cfo_hz=20000. + visit, fractional_margin=.16,
                          candidate_rank=0, passed_fractional_margin_gate=True)
            rows.append(dict(visit_index=visit, receiver_id=receiver, channel=channel, edge="lower",
                             valid_start_counter=visit * 5_000_000, actual_rf_hz=10e9 + channel * 250e6,
                             candidates=[factor] if measured else []))
    return dict(source=dict(probes=rows, raw_recording_authority_digest="radio"), provenance=dict(
        processed_windows=26, invalid_capture=0, window_count=26))


def masked_packet(cycle, document):
    rows, held = cycle.erased_rows(document)
    return dict(document, source=dict(document["source"], probes=rows)), held


def test_fixed_smoothing_and_incomplete_rf_cycles(cycle):
    document = signed_packet(True)
    masked, held = masked_packet(cycle, document)
    history = cycle.history_rows(masked["source"]["probes"])
    predictions, skipped = cycle.predict(masked, history)
    assert len(held) == 8
    assert skipped == {0: 2, 1: 2}
    assert len(predictions) == 4
    assert all(row["n"] == 7 for row in predictions)
    assert {row["probabilities"]["unfiltered"] for row in predictions if row["radio"] == 0} == {3.5 / 8}
    assert {row["probabilities"]["unfiltered"] for row in predictions if row["radio"] == 1} == {7.5 / 8}


def test_held_anchor_positives_are_scored_only_after_history_and_predictions(cycle):
    first, second = signed_packet(True), signed_packet(False)
    a, _ = masked_packet(cycle, first)
    b, _ = masked_packet(cycle, second)
    assert a == b
    pa, _ = cycle.predict(a, cycle.history_rows(a["source"]["probes"]))
    pb, _ = cycle.predict(b, cycle.history_rows(b["source"]["probes"]))
    assert pa == pb
    assert all(row["outcome"] == 1 for row in cycle.score(pa, first["source"]["probes"]))
    assert all(row["outcome"] == 0 for row in cycle.score(pb, second["source"]["probes"]))


def test_no_complete_cycle_defaults_to_unfiltered(cycle):
    document = signed_packet(True)
    document["source"]["probes"] = document["source"]["probes"][:12]
    document["provenance"].update(window_count=6, processed_windows=6)
    assert cycle.select_route(document) == {"route": "unfiltered", "log_score_gain_by_radio": {0: 0, 1: 0}}


def test_receiver_first_path_does_not_import_solver_dependencies(cycle):
    command = f"""
import sys
sys.path.insert(0, {str(Path(cycle.__file__).parent)!r})
from anchor_cycle_route import select_route
assert select_route({signed_packet(True)!r})['route'] in ('unfiltered', 'history')
assert not any(name.split('.')[0] in ('numpy', 'scipy', 'matplotlib') or 'v5_core' in name for name in sys.modules)
"""
    subprocess.run([sys.executable, "-Bc", command], check=True)


@pytest.mark.parametrize("first, second, expected", [(1., 1., "history"), (1., 0., "unfiltered"),
                                                     (1., -.1, "unfiltered"), (-.1, 1., "unfiltered")])
def test_history_must_win_strictly_on_both_radios(cycle, first, second, expected):
    assert cycle.route({0: {"delta_log_score": first}, 1: {"delta_log_score": second}}) == expected
