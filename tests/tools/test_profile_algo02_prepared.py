"""Prepared replay excludes archived answers and requires complete read ancestry."""

import json

import profile_algo02_prepared as replay
import pytest


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def exported(tmp_path):
    root = tmp_path / "export"
    names = (*replay.INPUTS, "SCAN/result.json", "SCAN/fit_radio_noise.json",
             "SCAN/algo02_result.json", "family_cavity/position/SCAN.json")
    files = {}
    for name in names:
        p = root / "inference" / name
        write(p, {"marker": name})
        files[name] = "sha256:" + replay.PROFILE.digest(p)
    write(root / "descriptor.json", dict(files=files, terminal={"state": "complete"}))
    return root


def test_copy_excludes_all_fitted_answers(tmp_path):
    source, target = exported(tmp_path), tmp_path / "private"
    replay.copy_inputs(source, target)
    assert not (target / "SCAN/result.json").exists()
    assert not (target / "SCAN/fit_radio_noise.json").exists()
    assert not (target / "SCAN/algo02_result.json").exists()
    assert not (target / "family_cavity").exists()
    for name in ("SCAN/observations.json", "SCAN/tracking.json",
                 "causal_phase_history/SCAN.json", "causal_prior/SCAN/previous.tle"):
        assert (target / name).read_bytes() == (source / "inference" / name).read_bytes()


def test_changed_prepared_evidence_rejected(tmp_path):
    source = exported(tmp_path)
    (source / "inference/SCAN/observations.json").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        replay.copy_inputs(source, tmp_path / "private")


def test_read_audit_accounts_for_every_stage_and_child(tmp_path):
    for pid in range(10, 12):
        write(tmp_path / "read_receipts" / f"{pid}.json", dict(
            pid=pid, parent_pid=1, python_spawns=["python"] if pid == 10 else [],
            denied_paths=[]))
    assert not replay.audit(tmp_path, 1)["verified"]
    write(tmp_path / "read_receipts/14.json", dict(pid=14, parent_pid=10,
        python_spawns=[], denied_paths=[]))
    assert replay.audit(tmp_path, 1)["verified"]
    write(tmp_path / "read_receipts/14.json", dict(pid=14, parent_pid=10,
        python_spawns=[], denied_paths=["archived-answer.json"]))
    assert not replay.audit(tmp_path, 1)["verified"]
