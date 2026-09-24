from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_summary_is_complete_and_uses_surveyed_reference() -> None:
    body = json.loads((HERE / "summary.json").read_text())
    assert body["headline"]["ds2_sessions"] == 20
    assert body["headline"]["ds2_best_error_km"] < 2.0
    assert body["reference_coordinate"]["latitude_deg"] == 37.84903264307456
    assert len(body["comparison_rows"]) == 8
