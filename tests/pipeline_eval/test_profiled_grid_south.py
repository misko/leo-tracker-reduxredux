import json

import pytest

from reports.ALGO08.v3 import profiled_grid_south as south
from reports.ALGO08.v3.profiled_grid_south_score import worst_nodes


@pytest.mark.parametrize("state", ["verified", "running", "deferred_storage_busy"])
def test_priority_announcement_disables_south(tmp_path, monkeypatch, state):
    monkeypatch.setattr(south, "CAMPAIGN", tmp_path)
    case = {"case": "DS30-0218", "verified_pair": False}
    rows = [dict(case, admission_state="pending"), dict(case, admission_state=state)]
    (tmp_path / "rows.jsonl").write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError, match="priority"):
        south.primary_pending()


def test_south_never_locks_on_a_priority_deferral():
    with pytest.raises(ValueError, match="priority field case"):
        south.admit("containing", 0, None, {"case": "DS30-0218"})


def test_worst_node_records_absolute_scores_and_relative_loss_in_both_arms():
    def grid(scores):
        return {"points": [{"east_km": i, "north_km": 0,
                            "scores": dict(zip(("c0", "fitted_c"), v, strict=True))}
                           for i, v in enumerate(scores)]}

    nodes = worst_nodes(grid([(None, 1.), (2., 3.), (7., 6.)]),
                        grid([(None, 1.), (2.001, 3.01), (7.02, 6.)]))
    assert nodes["c0"]["ordinary"] == 7.
    assert nodes["c0"]["checked"] == 7.02
    assert nodes["c0"]["ordinary_relative_loss"] == 5.
    assert nodes["c0"]["finite_pairs"] == 2
    assert nodes["fitted_c"]["node_index"] == 1
    assert nodes["c0"]["over_0_005"] == nodes["fitted_c"]["over_0_005"] == 1
