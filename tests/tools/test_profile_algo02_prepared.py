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


def fitted(root, seconds):
    arms = {a: dict(endpoint_latlon=[37.8, -122.4], owners=["native-point-1"],
                   norads=[12345], objective=100., gate=True)
            for a in ("c0", "fitted_c")}
    write(root / "SCAN/fit_radio_noise.json", dict(seconds=seconds,
        physical_prior_previous_tle_path=str(root / "SCAN/previous.tle"),
        input_read_paths=[str(root / "SCAN/tracking.json")], source_sha256="code"))
    write(root / "SCAN/progress_radio_noise.json", dict(choices=[]))
    write(root / "SCAN/result.json", dict(seconds=seconds, arms=arms))
    write(root / "SCAN/algo02_result.json", dict(seconds=seconds, policy_arms=arms,
        baseline_sha256=replay.PROFILE.digest(root / "SCAN/result.json")))
    write(root / "family_cavity/SCAN_nominations.json", dict(seconds=seconds, families=[]))
    write(root / "family_cavity/position/SCAN.json", dict(seconds=seconds, policy_arms=arms,
        nomination_sha256=replay.PROFILE.digest(root / "family_cavity/SCAN_nominations.json")))


def test_checked_runtime_and_path_accounting_preserves_exact_science(tmp_path):
    left, right = tmp_path / "reference", tmp_path / "candidate"
    fitted(left, 10.)
    fitted(right, 5.)
    assert replay.compare_results(left, right)["exact"]


@pytest.mark.parametrize("field,value", [("objective", 100.0000000001), ("norads", [12346]),
    ("owners", ["native-point-2"]), ("gate", False), ("endpoint_latlon", [37.80001, -122.4])])
def test_every_scientific_field_compared_exactly(tmp_path, field, value):
    left, right = tmp_path / "reference", tmp_path / "candidate"
    fitted(left, 10.)
    fitted(right, 5.)
    path = right / "family_cavity/position/SCAN.json"
    data = replay.read(path)
    data["policy_arms"]["c0"][field] = value
    write(path, data)
    assert not replay.compare_results(left, right)["exact"]


def test_forged_hash_link_cannot_be_normalized(tmp_path):
    left, right = tmp_path / "reference", tmp_path / "candidate"
    fitted(left, 10.)
    fitted(right, 5.)
    path = right / "SCAN/algo02_result.json"
    data = replay.read(path)
    data["baseline_sha256"] = "forged"
    write(path, data)
    with pytest.raises(ValueError, match="hash link"):
        replay.compare_results(left, right)


def test_extra_scientific_output_cannot_be_ignored(tmp_path):
    left, right = tmp_path / "reference", tmp_path / "candidate"
    fitted(left, 10.)
    fitted(right, 5.)
    write(right / "SCAN/extra-fit.json", dict(position=[0., 0.]))
    with pytest.raises(ValueError, match="inventory"):
        replay.compare_results(left, right)


@pytest.mark.parametrize("mismatch", [None, "cprofile_enabled", "thread_settings", "executable"])
def test_pair_does_not_claim_speedup_for_unmatched_measurements(tmp_path, mismatch):
    roots = [tmp_path / "baseline", tmp_path / "candidate"]
    for side, root in enumerate(roots):
        for stage in ("algo02", "family"):
            launch = dict(executable="python", python="3.12", host="host", cpu_count=24,
                          thread_settings={"OMP_NUM_THREADS": "1"},
                          cprofile_enabled=False, script_sha256="script")
            if side and mismatch:
                launch[mismatch] = "different"
            write(root / stage / "launch.json", launch)
            write(root / stage / "timing.json", dict(wall_seconds=10. if side else 20.,
                  user_cpu_seconds=8., system_cpu_seconds=1.))
    result = replay.paired_timing(*roots, True)
    assert result["matched_timing_configuration"] == (mismatch is None)
    assert result["wall_speedup"] == (2. if mismatch is None else None)
    assert replay.paired_timing(*roots, False)["wall_speedup"] is None
