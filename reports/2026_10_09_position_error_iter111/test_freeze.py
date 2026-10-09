import runpy
from pathlib import Path

import pytest

build = runpy.run_path(str(Path(__file__).with_name("freeze.py")))["plan_from_pilot"]


def test_exact_pilot_authority_and_limits():
    potential = [dict(member=dict(session_id=str(i), dataset="DS16")) for i in range(148)]
    selected = potential[:12]
    for i, row in enumerate(selected):
        row["member"]["dataset"] = ("DS16", "DS17", "DS18")[i // 4]
    pilot = dict(members=selected, potential_members=potential)
    plan = build(pilot, {"synthetic": "hash"}, "pilot-hash")
    assert plan["pilot_protocol_sha256"] == "pilot-hash"
    assert plan["members"] == selected
    assert plan["optimizer_calls"] == 0 and plan["design_budget_bytes"] == 512 * 1024**2
    assert plan["chunk_rows"] == 4096
    assert plan["observed_schur_complement"] is None
    selected[0] = selected[1]
    with pytest.raises(AssertionError):
        build(pilot, {}, "pilot-hash")
