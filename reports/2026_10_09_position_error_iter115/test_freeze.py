import runpy
from pathlib import Path

import pytest

build = runpy.run_path(str(Path(__file__).with_name("freeze.py")))["build_plan"]


def test_original_member_states_and_source_closure_required():
    member = dict(member=dict(inventory_label="DS17-033"))
    upstream = dict(members=[member], source_sha256={"native": "hash"})
    chosen = [(str(i), [0], 1) for i in range(6)]
    plan = build(upstream, member, chosen, {"native": "hash"}, "protocol")
    assert plan["optimizer_calls"] == 0 and plan["maximum_full_objective_calls"] == 6
    with pytest.raises(AssertionError):
        build(upstream, member, chosen, {"native": "wrong"}, "protocol")
    with pytest.raises(AssertionError):
        build(upstream, member, chosen[:5], {"native": "hash"}, "protocol")
