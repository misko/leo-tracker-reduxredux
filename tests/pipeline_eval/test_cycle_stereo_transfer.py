from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from cycle_stereo_transfer import compare_rows


def test_differentiate_direct_and_downstream_losses():
    rows = [dict(visit_index=i, receiver_id=0, candidates=[i]) for i in range(3)]
    subset = [rows[0], dict(rows[1], candidates=[]), dict(rows[2], candidates=[])]
    assert compare_rows(rows, subset, {1}) == dict(common=1, lost=2, added=0, lost_on_paid=1)
    with pytest.raises(ValueError, match="Unpaid"):
        compare_rows(rows, subset, {0})
