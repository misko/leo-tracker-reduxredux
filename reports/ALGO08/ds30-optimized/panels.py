"""Nested DS30 panels, selected in the frozen prediction order before scoring."""

PANEL_SIZES = {"smoke": 4, "triage": 16, "expanded": 64, "full": 455}


def select_panel(predictions, panel):
    roster = [row for row in predictions if row["method"] == "compact_two_scan"]
    if len(roster) != 455 or len({row["case"] for row in roster}) != 455:
        raise ValueError("Expected the 455 distinct members of sealed DS30 revision 1")
    return roster[:PANEL_SIZES[panel]]
