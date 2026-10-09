import runpy
from pathlib import Path

import pytest

build_plan = runpy.run_path(str(Path(__file__).with_name("freeze.py")))["build_plan"]


def synthetic():
    members, selected, ranks = [], [], []
    for dataset, count in (("DS16", 63), ("DS17", 51), ("DS18", 34)):
        for i in range(count):
            label = f"{dataset}-{i}"
            binding = dict(member=dict(dataset=dataset, inventory_label=label, session_id=label))
            members.append(binding)
            ranks.append(dict(label=label, selected=i < 4))
            if i < 4:
                selected.append(binding)
    return dict(members=members), selected, ranks


def test_full_authority_and_literal_gates_without_draw():
    authority, selected, ranks = synthetic()
    plan = build_plan(authority, selected, ranks, {}, "synthetic")
    assert plan["potential_members"] == authority["members"]
    assert plan["raw_attempts_expected"] == 48
    assert plan["maximum_iterations"] == 600 and plan["maximum_seconds"] == 90
    assert plan["rhos"] == [0, 0.5]
    assert "runtime_ratio" not in plan["progression_gates"]


def test_reject_duplicate_and_rank_disagreement():
    authority, selected, ranks = synthetic()
    selected[0] = selected[1]
    with pytest.raises(AssertionError):
        build_plan(authority, selected, ranks, {}, "synthetic")
    authority, selected, ranks = synthetic()
    ranks[0]["selected"] = False
    with pytest.raises(AssertionError):
        build_plan(authority, selected, ranks, {}, "synthetic")
