import json
from pathlib import Path

import pytest

from reports.ALGO08.v3.installed_receiver_field_budget import gates, rate_threshold
from reports.ALGO08.v3.prefetch_snapshots import AlternatingSnapshots


def test_both_speed_gates_bind_separately():
    records = [{"installed_s": 100}, {"installed_s": 20}]
    fixed, raw = [20, 0], [40, 20]
    threshold = rate_threshold(records, fixed, raw)
    assert threshold == pytest.approx(4 / 7)
    floor = [cost + stock * threshold for cost, stock in zip(fixed, raw, strict=True)]
    assert gates(records, floor)["median"] == pytest.approx(.5)
    assert gates(records, floor)["summed"] < .5
    assert rate_threshold(records, [70, 15], raw) is None


@pytest.mark.parametrize("case", ("DS30-0016", "DS30-0049", "DS30-0178", "DS30-0019"))
def test_reserved_slots_avoid_all_growth_on_archived_original_sizes(case):
    root = Path(__file__).resolve().parents[2]
    artifact = root / "reports/ALGO08/v3/measurements/installed-receiver-field-budget.json"
    saved = json.loads(artifact.read_bytes())
    sizes = (saved["weak"]["resident_prefetch_sizes"] if case == "DS30-0016" else
             next(row["speculative_member_bytes"] for row in saved["cases"] if row["case"] == case))
    ordinary, reserved = AlternatingSnapshots(), AlternatingSnapshots(reserve=max(sizes))
    for size in sizes:
        original, received = ordinary.borrow(size), reserved.borrow(size)
        assert original.size == received.size == size
        # Check the exact view/ownership boundary without touching I/Q bytes.
        received[-1] = 1
        assert received[-1] == 1
        del original, received
    initial = ordinary.counts()
    final = reserved.counts()
    assert sum(row.get("allocations", 0) for row in initial) > 2
    assert all(row["allocations"] == 1 and row["peak_bytes"] == max(sizes) for row in final)
    assert sum(row["reuses"] for row in final) == len(sizes) - 2
    ordinary.close()
    reserved.close()
