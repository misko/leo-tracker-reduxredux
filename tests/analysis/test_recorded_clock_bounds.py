import json
from pathlib import Path

import numpy as np
import pytest


def test_bounds_use_recording_identity_and_exact_reference(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from replay_wide_session_clocks import recorded_clock_bounds

    directory = tmp_path / "evidence"
    directory.mkdir()
    rows = []
    for sid, width in [("scan-b", 100), ("scan-a", 200)]:
        (directory / (sid + ".json")).write_text(
            json.dumps({"inventory": {"reference_utc_ns": 1000000000}})
        )
        rows.append(
            dict(
                session_id=sid,
                timing=dict(
                    first_sample_estimate_utc_ns=1000000000,
                    first_sample_earliest_utc_ns=1000000000 - width * 1000000,
                    first_sample_latest_utc_ns=1000000000 + width * 1000000,
                ),
            )
        )
    assignments = [dict(session_id="scan-a"), dict(session_id="scan-b")]
    data = dict(session=np.array([9, 9, 3, 3]), episode=np.array([0, 0, 1, 1]))
    assert recorded_clock_bounds(data, assignments, rows, tmp_path) == {
        9: (-0.2, 0.2),
        3: (-0.1, 0.1),
    }
    rows[0]["timing"]["first_sample_estimate_utc_ns"] += 1
    with pytest.raises(ValueError, match="reference differs"):
        recorded_clock_bounds(data, assignments, rows, tmp_path)
