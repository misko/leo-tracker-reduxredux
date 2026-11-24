import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import ds30_relocation_coordinator as coordinator
from ds30_paired_inputs import write


def service(state="active"):
    return dict(LoadState="loaded", ActiveState=state, Result="exit-code" if state == "failed" else "success",
                ExecMainStatus="1" if state == "failed" else "0", MainPID="0" if state == "failed" else "123",
                InvocationID="a"*32, User="leo", Nice="15", IOSchedulingClass="3", CPUAffinity="2",
                ExecStart="{ argv[]=" + " ".join(coordinator.ORDINARY_ARGV) + " ; }")


def rejected(path):
    write(path / "pair.json", dict(state="invalid_original_input", verified_pair=False, reason=coordinator.PATH_ERROR))


def mock_paths(monkeypatch, root):
    monkeypatch.setattr(coordinator, "ROOT", root)
    monkeypatch.setattr(coordinator, "RECOVERY", root / "relocation")
    monkeypatch.setattr(coordinator, "STATE", root / "relocation/coordinator")


def test_literal_unit_and_exact_invocation_stage_guard():
    failed = service("failed")
    assert coordinator.literal_service(failed)
    assert not coordinator.literal_service(failed | {"ExecStart": failed["ExecStart"].replace("455", "3")})
    messages = [f'  File "{coordinator.ORDINARY_DRIVER}", line 289, in in_scope',
                "ValueError: Review repeated operational failures before scaling beyond 100 cases"]
    journal = [{"_SYSTEMD_UNIT": coordinator.ORDINARY, "_SYSTEMD_INVOCATION_ID": failed["InvocationID"], "MESSAGE": text}
               for text in messages]
    assert coordinator.exact_halt(failed, journal) == 100
    assert coordinator.exact_halt(failed | {"InvocationID": "b"*32}, journal) is None
    assert coordinator.exact_halt(failed | {"ExecMainStatus": "75"}, journal) is None
    assert coordinator.exact_halt(failed, journal[1:]) is None


def test_pending_ordinary_arm_prevents_concurrent_relocation(tmp_path):
    row = {"case": "DS30-0100"}
    attempt = tmp_path / "cases/DS30-0100/successor/attempt-000001/launch.json"
    write(attempt, {})
    assert coordinator.pending_arm(tmp_path, [row]) == row["case"]
    write(tmp_path / "cases/DS30-0100/pair.json", {"verified_pair": True})
    assert coordinator.pending_arm(tmp_path, [row]) is None


def test_eligibility_excludes_unencountered_unknown_and_already_sealed_cases(tmp_path, monkeypatch):
    mock_paths(monkeypatch, tmp_path)
    rejected(tmp_path / "cases/DS30-0451")
    rejected(tmp_path / "cases/DS30-0449")
    rejected(tmp_path / "cases/DS30-0100")
    write(tmp_path / "cases/DS30-0447/pair.json",
          {"state": "invalid_original_input", "verified_pair": False, "reason": "Unknown change"})
    write(tmp_path / "relocation/DS30-0449/overlay.json", {})
    planned = [{"case": case} for case in ("DS30-0450", "DS30-0449", "DS30-0451", "DS30-0100", "DS30-0447")]
    assert coordinator.eligible(planned) == ["DS30-0451"]


def test_migration_stage_intent_is_stable_and_preserves_old_pair(tmp_path, monkeypatch):
    mock_paths(monkeypatch, tmp_path)
    group = ["DS30-0452", "DS30-0451", "DS30-0100"]
    ordered = [{"case": case} for case in group]
    for case in group[:2]:
        rejected(tmp_path / "cases" / case)
    write(tmp_path / "cases/DS30-0100/pair.json", {"verified_pair": True})
    original = coordinator.resume_intent(3, "a"*32, ordered)
    assert list(original["rejections"]) == group[:2]
    for case in group[:2]:
        current = tmp_path / "cases" / case
        current.joinpath("pair.json").rename(current / "original-preflight.json")
        write(current / "pair.json", {"verified_pair": True})
        overlay = {"original_preflight_sha256": original["rejections"][case]}
        write(current / "relocation-overlay.json", overlay)
        write(tmp_path / "relocation" / case / "overlay.json", overlay)
    assert coordinator.resume_intent(3, "a"*32, ordered) == original
    coordinator.check_resume(original)
    with pytest.raises(ValueError, match="stop no longer corresponds"):
        coordinator.resume_intent(2, "a"*32, ordered)


def test_unrelated_operational_failure_prevents_stage_restart(tmp_path, monkeypatch):
    mock_paths(monkeypatch, tmp_path)
    for case in ("DS30-0452", "DS30-0451"):
        rejected(tmp_path / "cases" / case)
    write(tmp_path / "cases/DS30-0100/pair.json", {"state": "observed_pair", "verified_pair": False})
    with pytest.raises(ValueError, match="non-migration"):
        coordinator.resume_intent(3, "a"*32, [{"case": case} for case in ("DS30-0452", "DS30-0451", "DS30-0100")])


def test_active_0452_is_not_replaced(tmp_path, monkeypatch):
    mock_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(coordinator, "plan_document", lambda: {"cases": [{"case": "DS30-0452"}], "smoke": []})
    assert coordinator.step({"ordinary": service(), "owner": {"ActiveState": "activating"}, "halted_at": None})[0] == 75
    assert json.loads((tmp_path/"relocation/coordinator/status.json").read_bytes())["state"] == "existing_0452_owner"


def test_resume_uses_start_only_and_rechecks_the_exact_failed_invocation(monkeypatch):
    from types import SimpleNamespace

    old = {"ordinary": service("failed"), "halted_at": 100}
    request = {"state": "restart_proven_stage", "stage": 100, "invocation": "a"*32,
               "plan_sha256": coordinator.PLAN_PIN, "attached": ["DS30-0451", "DS30-0452"]}
    monkeypatch.setattr(coordinator, "run_as_leo", lambda *a: SimpleNamespace(stdout=json.dumps(request).encode(),
                                                                              returncode=42))
    calls = []
    monkeypatch.setattr(coordinator.subprocess, "run", lambda argv, **kwargs: calls.append(argv))
    views = iter((old, {"ordinary": service(), "halted_at": None}))
    monkeypatch.setattr(coordinator, "snapshot", lambda: next(views))
    with pytest.raises(ValueError, match="exact failed invocation"):
        coordinator.supervise()
    assert not calls
    monkeypatch.setattr(coordinator, "snapshot", lambda: old)
    assert coordinator.supervise() == 75
    assert calls == [["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", coordinator.ORDINARY]]
