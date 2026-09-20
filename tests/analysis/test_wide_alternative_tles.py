from pathlib import Path

import pytest


def test_alternative_orbits_must_bind_same_order_and_identities(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from replay_wide_alternative_tles import validate_assignment_order

    rows = [dict(session_id="scan", episode_id=str(i), norad=i) for i in [1, 2]]
    validate_assignment_order(rows, [dict(r) for r in rows])
    for invalid in [list(reversed(rows)), rows[:1], [dict(rows[0], norad=3), rows[1]]]:
        with pytest.raises(ValueError, match="order or identity"):
            validate_assignment_order(rows, invalid)
