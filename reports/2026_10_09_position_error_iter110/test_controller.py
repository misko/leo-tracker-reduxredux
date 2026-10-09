"""Synthetic process invocation only; no selection, corpus or optimizer."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "controller110", Path(__file__).with_name("controller.py")
)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def fixture(tmp_path):
    members = [dict(member=dict(inventory_label=f"synthetic-{i}")) for i in range(12)]
    (tmp_path / "protocol.json").write_text(json.dumps(dict(members=members)))
    (tmp_path / "results").mkdir()
    digest = hashlib.sha256((tmp_path / "protocol.json").read_bytes()).hexdigest()
    return members, digest


def test_bounded_shards_terminal_failures_and_resume(tmp_path):
    members, digest = fixture(tmp_path)
    calls = []

    def invoke(command, **kwargs):
        label = command[-1]
        member = next(b["member"] for b in members if b["member"]["inventory_label"] == label)
        assert (tmp_path / "controller-claims" / f"{label}.json").exists()
        calls.append(label)
        (tmp_path / "results" / f"{label}.json").write_text(
            json.dumps(
                dict(
                    member=member,
                    protocol_sha256=digest,
                    status="failed" if len(calls) == 1 else "complete",
                )
            )
        )
        return SimpleNamespace(returncode=0)

    result = controller.launch(0, 2, here=tmp_path, invoke=invoke)
    assert calls == ["synthetic-0", "synthetic-2"] and result["launched"] == 2
    assert [r["status"] for r in result["coverage"]].count("unlaunched") == 10
    controller.launch(0, 6, here=tmp_path, invoke=invoke)
    assert len(calls) == 6
    controller.launch(1, 6, here=tmp_path, invoke=invoke)
    assert len(calls) == 12
    assert controller.launch(0, here=tmp_path, invoke=invoke)["launched"] == 0


def test_claimed_crash_never_retries(tmp_path):
    fixture(tmp_path)
    with pytest.raises(RuntimeError, match="missing terminal"):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **kw: SimpleNamespace(returncode=0))
    with pytest.raises(FileExistsError):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **kw: pytest.fail("No retry"))
    members, digest = controller.authority(tmp_path)
    assert controller.coverage(tmp_path, members, digest)[0]["status"] == "claimed-without-terminal"


def test_nonzero_exit_and_launch_error_preserved(tmp_path):
    fixture(tmp_path)
    with pytest.raises(RuntimeError, match="exited7"):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **kw: SimpleNamespace(returncode=7))
    row = json.loads((tmp_path / "controller-claims/synthetic-0.exit.json").read_text())
    assert row["returncode"] == 7

    def fail(*a, **kw):
        raise OSError("synthetic failure")

    with pytest.raises(OSError):
        controller.launch(1, here=tmp_path, invoke=fail)
    row = json.loads((tmp_path / "controller-claims/synthetic-1.exit.json").read_text())
    assert row["status"] == "launch-error"


def test_stale_terminal_and_invalid_limits_rejected(tmp_path):
    members, digest = fixture(tmp_path)
    (tmp_path / "results/synthetic-0.json").write_text(
        json.dumps(dict(member=members[0]["member"], protocol_sha256="stale", status="complete"))
    )
    with pytest.raises(ValueError, match="does not match"):
        controller.launch(0, here=tmp_path, invoke=lambda *a, **kw: pytest.fail("No fit"))
    with pytest.raises(ValueError):
        controller.launch(0, 7, here=tmp_path)
