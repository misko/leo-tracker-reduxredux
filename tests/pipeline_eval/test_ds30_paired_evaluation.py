from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import ds30_paired_evaluation as study
import ds30_paired_inputs as custody
import ds30_paired_worker as worker


def test_roster_order_is_deterministic_and_balanced():
    units = dict(manifest_sha256=custody.MANIFEST, dataset_labels=["DS30-0107", "DS30-0049"], case_ids=["a", "b"])
    members = [
        dict(case_id=key, dataset_label=label, window_count=i, recording_state="incomplete",
             raw_authority_digest=f"authority-{i}", raw_recording=dict(root=f"/r/{key}", identity_sha256=f"hash-{i}"))
        for i, (label, key) in enumerate(zip(units["dataset_labels"], units["case_ids"], strict=True), start=1)
    ]
    earlier = {"DS30-0049"}
    scheduled = custody.assignments(members, units, earlier)
    assert scheduled == custody.assignments(list(reversed(members)), units, earlier)
    assert [r["order"] for r in scheduled] == [["installed", "successor"], ["successor", "installed"]]
    assert [r["case"] for r in scheduled if r["historical_first100"]] == ["DS30-0049"]
    with pytest.raises(ValueError, match="signed units"):
        custody.assignments(members[:1], units, earlier)


def test_event_and_attempt_are_immutable_and_resume_does_not_overwrite(tmp_path):
    path = tmp_path / "binding.json"
    custody.write(path, {"value": 1})
    custody.write(path, {"value": 1})
    with pytest.raises(ValueError, match="Immutable"):
        custody.write(path, {"value": 2})
    first = study.next_attempt(tmp_path, "installed")
    first.mkdir()
    custody.write(first / "process.json", {"elapsed_s": .4})
    assert study.next_attempt(tmp_path, "installed").name == "attempt-000002"
    assert custody.read(first / "interrupted.json") == {"status": "interrupted", "preserved_clock": True}
    study.next_attempt(tmp_path, "installed")


def test_pending_and_failed_rows_keep_both_calibrations(tmp_path):
    plan = dict(cases=[dict(case="DS30-0107", order=["successor", "installed"])],
                stock={"frozen_specification": "stock"}, candidate={"sha256": "new"})
    result = tmp_path / "cases/DS30-0107/installed/attempt-000001/result.json"
    custody.write(result, dict(outcome="worker_failed", reason="nonzero_exit", elapsed_s=.5, cpu_s=.4,
                               timing_scope="raw_launch_to_exit", process={"elapsed_s": .5, "cpu_s": .4},
                               validation={"elapsed_s": .1, "cpu_s": .09}))
    current, pending = study.rows(tmp_path, plan)
    assert [current["algorithm"], pending["algorithm"]] == ["installed", "successor"]
    assert current["first"] == "successor"
    assert current["child_cpu_s"] == .4
    assert current["validator_cpu_s"] == .09
    assert pending["outcome"] == "pending" and pending["elapsed_s"] is None
    assert current["arms"] == pending["arms"] == {a: {"latlon": None, "rf_rms_hz": None} for a in custody.CALIBRATIONS}


def test_real_subprocess_clock_records_timeout_and_logs(tmp_path):
    for name in ("tmp", "fonts"):
        (tmp_path / name).mkdir()
    with (tmp_path / "lease").open("a+b") as lease:
        result = worker.child([sys.executable, "-c", "import os,sys,time; print(os.environ['OMP_NUM_THREADS'], flush=True); time.sleep(10)"],
                              tmp_path, .2, lease.fileno())
    assert result["timed_out"] and result["exit_code"] == -15
    assert result["cpu_s"] > 0 and result["elapsed_s"] >= .2
    assert (tmp_path / "stdout.log").read_text().strip() == "1"


def test_ordinary_and_successor_invocations_match_original_paths(tmp_path):
    build = {"entry": "/new/tool", "manifest": "/new/build", "sha256": "frozen"}
    inputs = {"authority": {"recording": "/original/x"}, "archive": "/original/tle", "authority_sha256": "case"}
    stock, candidate = [worker.invocation(build, inputs, tmp_path/"r", tmp_path/"a", tmp_path/"out", label) for label in custody.ARMS]
    for flag in ("--recording", "--archive", "--region", "--bulk-root"):
        assert stock[stock.index(flag)+1] == candidate[candidate.index(flag)+1]
    assert candidate[candidate.index("--authority-sha256")+1] == "case"
    assert "--authority-sha256" not in stock


def test_only_chronologically_matched_same_generation_pairs_qualify(tmp_path):
    authority = {"session_id": "expected"}
    inputs = dict(authority=authority, authority_sha256="signed")
    for label, start in (("installed", 1), ("successor", 10)):
        custody.write(tmp_path / label / "attempt-000001/result.json", dict(
            outcome="withheld", raw_identity=authority, generation=1, lease_id=label,
            process={"started_unix_ns": start, "finished_unix_ns": start + 1}))
    study.seal_pair(tmp_path, inputs, ["installed", "successor"])
    good = study.summary(tmp_path)
    assert good["verified_pair"] and good["chronological"] and not good["same_lease"]
    study.seal_pair(tmp_path, inputs, ["successor", "installed"])
    bad = study.summary(tmp_path)
    assert not bad["verified_pair"] and not bad["chronological"]
    custody.write(tmp_path / "successor/attempt-000002/result.json", dict(
        outcome="withheld", raw_identity=authority, generation=2, lease_id="second",
        process={"started_unix_ns": 20, "finished_unix_ns": 21}))
    study.seal_pair(tmp_path, inputs, ["installed", "successor"])
    assert not study.summary(tmp_path)["verified_pair"]
