"""Saved crossover switches operate independently on unchanged signed opportunities."""

from copy import deepcopy
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def crossover(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("eight_ms_crossover")


def packet(values):
    probes = []
    for index, factor in enumerate(values):
        visit, receiver = divmod(index, 2)
        candidates = [] if factor is None else [dict(candidate_rank=0, fractional_margin=.1,
                                                    passed_fractional_margin_gate=True, value=factor)]
        probes.append(dict(visit_index=visit, receiver_id=receiver, valid_start_counter=visit * 200000,
                           edge="lower", channel=4, actual_rf_hz=12e9, candidates=candidates))
    return dict(clock_anchor=dict(sample_counter=0), source=dict(session_id="sealed", probes=probes,
                raw_recording_authority_digest="raw", input_manifest_sha256="inventory"), provenance={})


@pytest.mark.parametrize("code", ["000", "111", "100", "010", "001", "110", "101", "011"])
def test_independent_signed_factor_switches(crossover, code):
    before = packet([91, None, 12, None, 122, None])
    after = packet([91, None, 8, 82, None, None])
    rows = crossover.strata(before, after)
    projected = crossover.projected(rows, code)
    expected = [91, None, 8 if code[0] == "1" else 12,
                82 if code[1] == "1" else None, None if code[2] == "1" else 122, None]
    assert projected == packet(expected)["source"]["probes"]
    assert before == packet([91, None, 12, None, 122, None])
    assert after == packet([91, None, 8, 82, None, None])


@pytest.mark.parametrize("change,match", [("anchor", "Full-anchor"), ("clock", "authorities"), ("lane", "lane")])
def test_crossovers_reject_different_acquisition_authority(crossover, change, match):
    before = packet([91, None, 12, None])
    after = deepcopy(before)
    if change == "anchor":
        after["source"]["probes"][0]["candidates"][0]["value"] = 92
    elif change == "clock":
        after["clock_anchor"]["sample_counter"] += 1
    else:
        after["source"]["probes"][-1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match=match):
        crossover.strata(before, after)


def test_graph_change_counts_use_shared_membership_instead_of_track_order(crossover):
    score = importlib.import_module("eight_ms_crossover_score")
    before = dict(graph_points=4, tracks=[dict(ids=["a", "b"], curved=False), dict(ids=["c", "d"], curved=True)])
    after = dict(graph_points=4, tracks=[dict(ids=["d", "e"], curved=True), dict(ids=["a", "b"], curved=True)])
    unchanged = score.graph_changes(before, after)
    assert (unchanged["shared_changed_group"], unchanged["shared_changed_curvature"]) == (0, 2)
    assert (unchanged["added"], unchanged["dropped"], unchanged["shared"]) == (1, 1, 3)
    after["tracks"] = [dict(ids=["a", "d"], curved=False), dict(ids=["b", "e"], curved=True)]
    assert score.graph_changes(before, after)["shared_changed_group"] == 3


def test_margin_guard_is_inclusive_current_visit_and_always_keeps_anchors(crossover):
    probes = packet([1, 2, 3, 4, None, 6, *([None] * 10), 17, None])
    rows = probes["source"]["probes"]
    rows[0]["candidates"][0]["fractional_margin"] = .025
    rows[2]["candidates"][0]["fractional_margin"] = crossover.MARGIN
    rows[3]["candidates"][0]["fractional_margin"] = crossover.MARGIN - .0001
    rows[5]["candidates"][0]["fractional_margin"] = .026
    rows[16]["candidates"][0]["fractional_margin"] = .025
    selected = crossover.guarded(probes)
    assert [i for i, row in enumerate(selected) if row["candidates"]] == [0, 1, 2, 16]
    assert [row["candidates"][0]["value"] for row in selected if row["candidates"]] == [1, 2, 3, 17]
