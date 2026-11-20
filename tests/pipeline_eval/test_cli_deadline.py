import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import deadline_benchmark as receiver


def result(status, reason=None, elapsed=0):
    return dict(
        status=status,
        reason=reason,
        boundary="solver",
        metrics={"candidate_s": elapsed},
        arms={arm: dict(latlon=None, forced_latlon=[37.95, -122.5]) for arm in cli.ARMS},
    )


def test_compact_exception_detection_requires_authenticated_started_inference():
    messages = [prefix + " numerical exception" for prefix in receiver.SOLVER_EXCEPTIONS]
    for message in [*messages, "AssertionError"]:
        failure = result("unavailable", message, 0.5)
        for binding, elapsed, expected in (
            ({}, 0.5, "failed"),
            (None, 0.5, "unavailable"),
            ({}, 0, "unavailable"),
        ):
            raw = dict(failure, metrics={"candidate_s": elapsed})
            assert (
                receiver.solver_result(receiver.COMPACT, {"result": raw}, binding)["status"]
                == expected
            )
    for message in ("Native input missing", "AssertionError handling configuration missing"):
        terminal = result("unavailable", message, 0.5)
        assert receiver.solver_result(receiver.COMPACT, {"result": terminal}, {}) is terminal


@pytest.mark.parametrize("legacy_exception", (False, True))
def test_deadline_fallback_passes_exact_time_and_keeps_forced_status(
    tmp_path, monkeypatch, legacy_exception
):
    current = [100.0]
    call_log = []
    binding = {key: key for key in receiver.SHARED}
    case = dict(id="roof", compact={"id": "roof"}, smooth={"id": "roof"}, binding=binding)

    def worker(method, packet, work, allowed, affinity, output, *, supervised):
        assert work == tmp_path and affinity == 7 and supervised
        call_log.append((method, allowed))
        if method == receiver.COMPACT and legacy_exception:
            current[0] += 5
            returned = result("unavailable", "ValueError: orbit support", 3)
        elif method == receiver.COMPACT:
            current[0] += allowed
            returned = result("timed_out", "compact worker elapsed")
        else:
            assert packet["timeout"] == allowed
            current[0] += 4
            returned = result("withheld", "insufficient held evidence")
        return dict(result=returned, worker_wall_s=allowed, input_binding=binding)

    monkeypatch.setattr(cli, "run_one", worker)
    monkeypatch.setattr(cli, "implementation_digest", lambda *a: "source")
    row = receiver.run("deadline_30s", case, tmp_path, 800, 7, now=lambda: current[0])
    assert call_log == [(receiver.COMPACT, 15), (receiver.SMOOTH, 25 if legacy_exception else 15)]
    assert row["result"]["status"] == "withheld"
    assert row["result"]["arms"]["fitted_c"]["forced_latlon"] == [37.95, -122.5]
    deadline = row["result"]["metrics"]["deadline"]
    assert deadline["selected"] == "smooth"
    first = deadline["attempts"][0]
    if legacy_exception:
        assert (first["raw_status"], first["status"], first["raw_reason"]) == (
            "unavailable",
            "failed",
            "ValueError: orbit support",
        )
    assert row["input_binding"] == binding


def test_outer_timeout_leaves_no_budget_for_second_worker(tmp_path, monkeypatch):
    current = [100.0]
    calls = []
    case = dict(id="roof", compact={"id": "roof"}, smooth={"id": "roof"}, binding={})

    def worker(method, _packet, _work, budget, _affinity, _output, *, supervised):
        assert supervised
        calls.append((method, budget))
        current[0] += budget
        return dict(result=result("timed_out", "deadline"), worker_wall_s=budget)

    monkeypatch.setattr(cli, "run_one", worker)
    monkeypatch.setattr(cli, "implementation_digest", lambda *a: "source")
    row = receiver.run("deadline_180s", case, tmp_path, 2, None, now=lambda: current[0])
    assert calls == [(receiver.COMPACT, 2)]
    assert row["result"]["status"] == "timed_out"
    deadline = row["result"]["metrics"]["deadline"]
    assert deadline["selected"] == "none"
    assert [call["launched"] for call in deadline["calls"]] == [True, False]


def test_causal_catalogue_latest_and_future_or_ambiguous_rejection():
    first, last = "1" * 64, "2" * 64
    items = {f"20-{first}.tle": first, f"25-{last}.tle": "sha256:" + last}
    assert receiver.nominal_catalogue({"causal_snapshots": items}, 30) == (
        25,
        last,
        f"25-{last}.tle",
    )
    with pytest.raises(ValueError, match="future catalogue"):
        receiver.nominal_catalogue({"causal_snapshots": items}, 24)
    with pytest.raises(ValueError, match="ambiguous"):
        receiver.nominal_catalogue({"causal_snapshots": items | {f"25-{first}.tle": first}}, 30)


def test_normal_deadline_entry_reports_unavailable_and_draws_both_arms(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "missing"))
    monkeypatch.setenv("PIPELINE_EVAL_BLIND_ROOT", str(tmp_path / "missing"))

    def wrong_adapter(*args):
        pytest.fail("deadline cannot resolve historical Graph/position inputs")

    monkeypatch.setattr(cli, "public_cases", wrong_adapter)
    assert (
        cli.main(
            [
                "run",
                "--panel",
                "smoke",
                "--case",
                "DS26-0036",
                "--variant",
                "deadline_30s",
                "--timeout",
                "1",
                "--out",
                str(tmp_path / "runs"),
                "--cache",
                str(tmp_path / "cache"),
            ]
        )
        == 0
    )
    run = next((tmp_path / "runs" / "smoke" / "deadline_30s").rglob("current")).resolve()
    row = json.loads((run / "predictions.jsonl").read_bytes())
    summary = json.loads((run / "summary.json").read_bytes())
    assert row["result"]["status"] == "unavailable" and row["input_binding"] is None
    assert row["result"]["metrics"]["deadline"]["total_s"] == 30
    assert row["result"]["metrics"]["deadline"]["attempts"] == []
    assert row["implementation_sha256"] == summary["run"]["implementation_sha256"]
    assert summary["run"]["deadline_total_s"] == 30
    for arm in cli.ARMS:
        assert (run / f"position-errors-{arm}.png").read_bytes().startswith(b"\x89PNG")


def test_default_all_does_not_start_extra_deadline_policies(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "VARIANTS", {receiver.COMPACT: "compact", "deadline_30s": "deadline"})
    monkeypatch.setattr(cli, "public_cases", lambda *a: [{"id": "DS26-0036"}])

    def unused(*args):
        pytest.fail("deadline policies require explicit opt-in")

    def normal(method, case, *args):
        assert method == receiver.COMPACT
        return dict(id=case["id"], worker_wall_s=0, result=result("unavailable", "fixture"))

    monkeypatch.setattr(receiver, "cases", unused)
    monkeypatch.setattr(cli, "run_one", normal)
    assert (
        cli.main(
            [
                "run",
                "--panel",
                "smoke",
                "--case",
                "DS26-0036",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert not (tmp_path / "smoke" / "deadline_30s").exists()


def wait_for_pid(path, seconds=8):
    stop = time.monotonic() + seconds
    while time.monotonic() < stop:
        if path.is_file() and (pid := path.read_text()):
            return int(pid)
        time.sleep(0.02)
    pytest.fail("test grandchild did not start")


def wait_for_exit(pid):
    path = Path(f"/proc/{pid}/stat")
    stop = time.monotonic() + 5
    while time.monotonic() < stop:
        try:
            if path.read_text().rsplit(") ", 1)[1][0] == "Z":
                return
        except (FileNotFoundError, ProcessLookupError):
            return
        time.sleep(0.02)
    pytest.fail("numerical descendant survived its supervisor")


def backend(path):
    code = (
        "import subprocess, sys, time; from pathlib import Path; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
    )
    return [sys.executable, "-c", code, str(path)]


@pytest.mark.skipif(sys.platform != "linux", reason="deadline worker containment uses Linux")
def test_deadline_group_is_killed_after_timeout(tmp_path, monkeypatch):
    pid_path = tmp_path / "pid"
    original = subprocess.Popen

    def spawn(_command, **kwargs):
        return original(receiver.watched_command(backend(pid_path), os.getpid()), **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spawn)
    row = cli.run_one(receiver.COMPACT, {"id": "roof"}, tmp_path, 2, None, supervised=True)
    assert row["result"]["status"] == "timed_out"
    wait_for_exit(wait_for_pid(pid_path))


@pytest.mark.skipif(sys.platform != "linux", reason="deadline worker containment uses Linux")
def test_deadline_group_is_killed_when_outer_launcher_is_killed(tmp_path):
    pid_path = tmp_path / "pid"
    parent_code = (
        "from tools.pipeline_eval.qualification.deadline_benchmark import watched_command; "
        "import os, subprocess, sys, time; "
        "subprocess.Popen(watched_command(sys.argv[1:], os.getpid()), start_new_session=True); "
        "time.sleep(60)"
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code, *backend(pid_path)], cwd=cli.ROOT)
    try:
        pid = wait_for_pid(pid_path)
    finally:
        parent.kill()
        parent.wait(timeout=5)
    wait_for_exit(pid)
