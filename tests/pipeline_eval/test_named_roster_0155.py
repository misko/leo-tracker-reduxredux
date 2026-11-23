from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from named_roster_0155 import Ledger, Profile, profile_receipt, same_science, seal_results


def test_ledger_charges_children_once_and_restores_ports():
    stamps = iter((10, 20, 32, 51, 70, 75))
    ledger = Ledger(lambda: next(stamps))
    port = SimpleNamespace(first=lambda: port.second(7), second=lambda arg: arg * 2)
    original = port.second
    with ledger.measure(port, "first", "parent"), ledger.measure(port, "second", "child"):
        assert port.first() == 14
        assert port.second(1) == 2
    assert port.second is original
    assert dict(ledger.amounts) == {
        "parent": dict(calls=1, inclusive_cpu_ns=41, exclusive_cpu_ns=29),
        "child": dict(calls=2, inclusive_cpu_ns=17, exclusive_cpu_ns=17),
    }


def test_ledger_does_not_suppress_errors_or_keep_failed_stack():
    stamps = iter((100, 105))
    ledger = Ledger(lambda: next(stamps))
    with pytest.raises(RuntimeError, match="unrelated"):
        with ledger.scope("original"):
            raise RuntimeError("unrelated")
    assert ledger.stack == []
    assert ledger.amounts["original"]["exclusive_cpu_ns"] == 5


def test_profile_preserves_exclusive_and_inclusive_fields():
    def child():
        return sum((1, 2, 3))

    def parent():
        return child() + child()

    profile = Profile()
    assert profile.runcall(parent) == 12
    rows = {row["function"]: row for row in profile_receipt(profile)["rows"]}
    assert rows["child"]["calls"] == 2
    assert rows["child"]["callers"][0]["function"] == "parent"
    assert rows["parent"]["inclusive_wall_s"] >= rows["child"]["exclusive_wall_s"]


def test_accounting_is_sealed_when_single_route_science_comparison_fails(tmp_path):
    def write(path, data):
        with path.open("x") as stream:
            stream.write(str(data))

    def compare():
        same_science({"arms": {"c0": [1, 2]}}, {"arms": {"c0": [2, 1]}})

    with pytest.raises(ValueError, match="changed at arms"):
        seal_results(write, tmp_path, {"cpu": 17}, compare)
    assert (tmp_path / "roster.json").read_text() == "{'cpu': 17}"
    assert not (tmp_path / "science.json").exists()


def test_single_route_science_compares_json_values_without_a_cumulative_arm(tmp_path):
    def write(path, data):
        path.write_text(str(data))

    def compare():
        same_science({"phase": {123: 0.5}}, {"phase": {"123": 0.5}, "unread_archived_field": None})
        return {"verified": True}

    seal_results(write, tmp_path, {"cpu": 17}, compare)
    assert (tmp_path / "science.json").read_text() == "{'verified': True}"
