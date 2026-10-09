import runpy
from pathlib import Path

import pytest

module = runpy.run_path(str(Path(__file__).with_name("report_completed.py")))


def test_scope_keeps63_and_all193():
    members = [
        dict(member=dict(inventory_label=f"DS16-{i:03d}", dataset="DS16")) for i in range(1, 64)
    ]
    members += [
        dict(member=dict(inventory_label=f"Other-{i}", dataset="Other")) for i in range(130)
    ]
    plan = dict(members=members)
    assert len(module["members_for"](plan, "DS16")) == 63
    assert len(module["members_for"](plan, "Full193")) == 193
    members.append(members[0])
    with pytest.raises(AssertionError):
        module["members_for"](plan, "Full193")


def test_full_preflight_blocks_reference_reads_if_last_member_pending():
    members = [
        dict(member=dict(inventory_label=f"DS16-{i:03d}", dataset="DS16")) for i in range(1, 64)
    ]
    calls = []

    def loader(member):
        status = "missing" if member is members[-1] else "complete"
        return dict(baseline=dict(status="complete"), candidate=dict(status=status)), {}

    def reference(member):
        calls.append(member)
        raise AssertionError("reference must not be read")

    with pytest.raises(ValueError, match="not terminal"):
        module["build"](
            dict(members=members),
            "DS16",
            "synthetic",
            phase_loader=loader,
            document_loader=reference,
        )
    assert calls == []


def test_terminal_failures_are_preserved_not_replaced():
    members = [dict(member=dict(inventory_label="synthetic"))]

    def loader(_):
        return dict(
            baseline=dict(status="failed"), candidate=dict(status="not-run-baseline-failed")
        ), {}

    module["require_terminal"](members, loader)
