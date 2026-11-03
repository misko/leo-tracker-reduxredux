"""Full native parity must include unpublished candidates and invalid windows."""

import json

import compare_full_glrt_replays as check
import pytest


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def replay_pair(tmp_path):
    snapshot = tmp_path / "snapshot"
    source = tmp_path / "runtime"
    (source / "src").mkdir(parents=True)
    (source / "src/worker.py").write_text("# frozen runtime\n")
    doc = dict(inventory={"segments": [{"windows": 2}]},
               expected_probes=[{"visit_index": 0}])
    write(snapshot / "input.json", doc)
    write(snapshot / "spec.json", dict(files=[dict(path=str(p)) for p in
          (snapshot / "input.json", source / "src/worker.py")]))
    check.full.PROFILE.freeze(snapshot / "spec.json", snapshot / "frozen.json")
    digest = check.full.PROFILE.digest(snapshot / "frozen.json")
    for label in ("baseline", "candidate"):
        root = snapshot / label
        write(root / "launch.json", dict(
            manifest_sha256=digest, command=["python", "execute", "--input",
            str(snapshot / "input.json"), "--output", str(root), "--source-root", str(source),
            "--workers", "2"], executable="python", python="3.12", host="test",
            thread_settings={"OMP_NUM_THREADS": "1"}, cprofile_enabled=False,
            script_sha256="same-script"))
        write(root / "timing.json", dict(successful_execution=True, exit_code=0,
            timed_out=False, manifest_unchanged=True, reference_after={"verified": True},
            wall_seconds=10 if label == "baseline" else 5))
        write(root / "result.json", dict(exact=True, workers=2, windows=2, expected_windows=2,
            processed=1, expected_processed=1, ranges=[dict(path="visits-000000.json")]))
        task = next(check.full.spans(doc["inventory"]))
        write(root / "windows/visits-000000.json", dict(task=task,
            windows=[dict(visit=0, published_candidates_exact=True, result=dict(
                visit=0, status="processed", receivers=[dict(receiver_id=0,
                    candidates=[dict(passed_margin_gate=False, exact_score=.1)])])),
                dict(visit=1, published_candidates_exact=True, result=dict(
                    visit=1, status="invalid", reason="gap", receivers=[]))]))
    return snapshot, snapshot / "baseline", snapshot / "candidate"


def change(root, relative, update):
    path = root / relative
    value = check.read(path)
    update(value)
    write(path, value)


def test_complete_exact_pair(replay_pair):
    result = check.compare(*replay_pair)
    assert result["exact"] and result["wall_speedup"] == 2
    assert result["windows"] == 2 and result["all_candidates"] == 1
    assert not result["localization_replayed"]


def test_unpublished_hypothesis_difference(replay_pair):
    change(replay_pair[2], "windows/visits-000000.json", lambda x:
           x["windows"][0]["result"]["receivers"][0]["candidates"][0].update(exact_score=.1000000001))
    result = check.compare(*replay_pair)
    assert not result["exact"] and result["wall_speedup"] is None
    assert result["first_mismatches"] == ["/0/receivers/0/candidates/0/exact_score"]


def test_invalid_window_is_scientific_evidence(replay_pair):
    change(replay_pair[2], "windows/visits-000000.json", lambda x:
           x["windows"][1]["result"].update(reason="different"))
    assert not check.compare(*replay_pair)["exact"]


@pytest.mark.parametrize("mutation", ["missing", "duplicated", "timeout", "runtime"])
def test_reject_incomplete_or_unbound_evidence(replay_pair, mutation):
    root = replay_pair[2]
    if mutation == "missing":
        change(root, "windows/visits-000000.json", lambda x: x["windows"].pop())
    elif mutation == "duplicated":
        change(root, "result.json", lambda x: x["ranges"].append(x["ranges"][0]))
    elif mutation == "timeout":
        change(root, "timing.json", lambda x: x.update(timed_out=True))
    else:
        source = replay_pair[0].parent / "runtime/src"
        (source / "extra.py").write_text("# unbound implementation\n")
    with pytest.raises(ValueError):
        check.compare(*replay_pair)


def test_different_workers_do_not_establish_speedup(replay_pair):
    change(replay_pair[2], "result.json", lambda x: x.update(workers=4))
    change(replay_pair[2], "launch.json", lambda x: x["command"].__setitem__(-1, "4"))
    result = check.compare(*replay_pair)
    assert result["exact"] and not result["matched_timing_configuration"]
    assert result["wall_speedup"] is None


def test_nonfinite_equal_values_fail():
    assert list(check.differences(float("inf"), float("inf"))) == [""]


def relocated_candidate(replay_pair):
    old, baseline, candidate = replay_pair
    other = old.parent / "new-snapshot"
    write(other / "input.json", check.read(old / "input.json"))
    spec = check.read(old / "spec.json")
    spec["files"][0]["path"] = str(other / "input.json")
    write(other / "spec.json", spec)
    check.full.PROFILE.freeze(other / "spec.json", other / "frozen.json")
    change(candidate, "launch.json", lambda x: x.update(
        manifest_sha256=check.full.PROFILE.digest(other / "frozen.json")))
    change(candidate, "launch.json", lambda x:
           x["command"].__setitem__(3, str(other / "input.json")))
    return other, baseline, candidate


def test_separate_frozen_baseline_is_parity_only(replay_pair):
    result = check.compare(*relocated_candidate(replay_pair), baseline_snapshot=replay_pair[0])
    assert result["exact"] and result["reused_baseline_snapshot"]
    assert result["baseline_frozen_verification"]["verified"]
    assert not result["matched_timing_configuration"] and result["wall_speedup"] is None


def test_reused_baseline_does_not_allow_changed_inputs(replay_pair):
    args = relocated_candidate(replay_pair)
    change(args[0], "input.json", lambda x: x.update(changed=True))
    # Re-freezing changed inputs does not make them equivalent to the baseline.
    (args[0] / "frozen.json").unlink()
    check.full.PROFILE.freeze(args[0] / "spec.json", args[0] / "frozen.json")
    with pytest.raises(ValueError, match="input documents differ"):
        check.compare(*args, baseline_snapshot=replay_pair[0])


def test_reused_baseline_reverifies_original_files(replay_pair):
    args = relocated_candidate(replay_pair)
    change(replay_pair[0], "input.json", lambda x: x.update(corrupt=True))
    with pytest.raises(ValueError, match="baseline evidence changed"):
        check.compare(*args, baseline_snapshot=replay_pair[0])
