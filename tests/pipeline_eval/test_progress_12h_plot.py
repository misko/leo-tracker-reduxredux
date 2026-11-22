import runpy
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
PLOT = runpy.run_path(str(REPORT / "progress_12h_plot.py"))


def test_archived_groups_keep_matched_counts_and_two_distinct_simulations():
    physical, simulations = PLOT["load_groups"]()
    assert [group.coverage for group in physical] == [
        "4/4 paired", "4/4 paired", "2/4 paired", "1/4 paired", "1/4 paired",
    ]
    assert [group.pairs[0].label for group in simulations] == [
        "North simulation", "South simulation",
    ]
    assert simulations[0].digest == simulations[1].digest
    assert physical[-1].pairs[0].label == "DS30-0374"
    assert physical[-1].pairs[0].errors["baseline"] == physical[-1].pairs[0].errors["candidate"]


def test_cumulative_error_keeps_withheld_recording_in_matched_denominator():
    Pair, Group = PLOT["Pair"], PLOT["Group"]
    fix = Pair("fixed", {}, {}, {"candidate": {"c0": 0.3}})
    withheld = Pair("withheld", {}, {}, {"candidate": {"c0": None}})
    group = Group("partial stage", "test", 4, (fix, withheld))
    assert group.coverage == "2/4 paired"
    assert PLOT["ecdf"](group, "candidate", "c0", 2.) == ([0., 0.3, 2.], [0., 0.5, 0.5])


def test_mismatched_inventory_coverage_is_rejected():
    stage = {"assigned": 1, "cases": [{"case": "A", "state": "missing"}],
             "coverage": {"verified": ["A"]}}
    with pytest.raises(ValueError, match="verified recording count"):
        PLOT["physical_group"]("test", stage, {})


def test_1611_snapshot_pairs_same_roof_ids_and_separates_public_signals():
    physical, (public,) = PLOT["november_22_1611_groups"]()
    assert len(physical) == 3
    for group in physical:
        assert [pair.label for pair in group.pairs] == [
            "DS30-0374", "DS30-0008", "DS30-0155", "DS30-0001",
        ]
    assert [pair.label for pair in public.pairs] == ["North simulation", "South simulation"]
    assert physical[-1].digest != public.digest
    for pair in (*physical[-1].pairs, *public.pairs):
        assert pair.errors["baseline"] == pair.errors["candidate"]
