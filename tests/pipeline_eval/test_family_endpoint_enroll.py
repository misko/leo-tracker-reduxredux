from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from family_endpoint_enroll import priority


def test_issued_count_selection_and_tie_break_use_only_schedule_metadata():
    band, fallback = priority({"DS30-0402": 3750, "DS30-0015": 3800, "DS30-0014": 3700,
                               "DS30-0360": 1500, "DS30-0200": 6000, "DS30-0050": 400, "DS30-0049": 560})
    assert band == ["DS30-0014", "DS30-0015", "DS30-0200", "DS30-0360"]
    assert fallback == ["DS30-0050", "DS30-0049"]
