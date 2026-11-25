import json

import pytest

from reports.ALGO08.v3 import profiled_grid_south as south


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
