"""Require real matched measurement fields on both archived routes."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from anchor_holds import history_rows
from continued_cfo_south import projection
from held_cycle_refined import CFO


def packet():
    rows = []
    for visit in range(9):
        for radio in (0, 1):
            frequency = 1000. + 120 * visit + 300 * radio
            rows.append(dict(visit_index=visit, receiver_id=radio, valid_start_counter=10_000_000 * visit,
                edge="lower", channel=1, actual_rf_hz=10_000_000,
                candidates=[{CFO: frequency, "candidate_rank": 0, "fractional_margin": .3,
                             "passed_fractional_margin_gate": True, "epoch": 21}]))
    return dict(source=dict(session_id="example", input_manifest_sha256="inventory",
                            raw_recording_authority_digest="authority", probes=rows),
                clock_anchor={}, delivery_clocks=[],
                provenance=dict(window_count=9, invalid_capture=0, processed_windows=9))


def edit_selected(native):
    for row in native["source"]["probes"]:
        if row["visit_index"] % 8 and row["candidates"]:
            row["candidates"][0][CFO] += 33.


def test_history_can_reuse_exact_archived_refinements_for_both_radios():
    original = packet()
    refined = deepcopy(original)
    refined["source"]["probes"] = history_rows(refined["source"]["probes"])
    edit_selected(refined)
    selected, _, count = projection(original, refined, {"route": "history"})
    assert selected == refined["source"]["probes"]
    assert [count[radio]["paid"] for radio in (0, 1)] == [5, 5]
    assert [count[radio]["retained_edits"] for radio in (0, 1)] == [5, 5]
    assert selected[16]["candidates"] == original["source"]["probes"][16]["candidates"]


def test_unfiltered_preserves_the_original_cfo_at_unpaid_positives():
    original = packet()
    refined = deepcopy(original)
    edit_selected(refined)
    selected, _, count = projection(original, refined, {"route": "unfiltered"})
    assert selected[2] == original["source"]["probes"][2]
    assert selected[6] == refined["source"]["probes"][6]
    assert count[0]["selected"] == 9 and count[0]["archived_selected_edits"] == 7


@pytest.mark.parametrize(("field", "pattern"), [("epoch", "only fixed-epoch CFO"),
                                                ("delivery", "identical signed opportunities"),
                                                ("omitted", "chosen support")])
def test_history_missing_or_changed_authentic_measurement_is_an_error(field, pattern):
    original = packet()
    refined = deepcopy(original)
    refined["source"]["probes"] = history_rows(refined["source"]["probes"])
    edit_selected(refined)
    lane = refined["source"]["probes"][6]
    if field == "epoch":
        lane["candidates"][0]["epoch"] += 1
    elif field == "omitted":
        lane["candidates"] = []
    else:
        refined["delivery_clocks"].append(1)
    with pytest.raises(ValueError, match=pattern):
        projection(original, refined, {"route": "history"})
