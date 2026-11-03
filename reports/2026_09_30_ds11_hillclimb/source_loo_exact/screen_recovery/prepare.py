"""Reuse the frozen scientific plan and verified successful numerical evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "screen"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    sources = {}
    def bind(path, expected=None):
        path = Path(path).resolve()
        actual = digest(path)
        assert expected is None or expected == actual, path
        assert str(path) not in sources or sources[str(path)] == actual
        sources[str(path)] = actual
        return path
    def read(path):
        return json.loads(bind(path).read_text())
    def verify(record):
        for path, expected in record["sources"].items():
            bind(path, expected)

    spec = importlib.util.spec_from_file_location("recovery_plan_assess", HERE / "assess.py")
    assess = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(assess)
    original = read(OLD / "plan.json")
    verify(original)
    plan = copy.deepcopy(original)
    selected0 = read(OLD / "selections" / "00.json")
    selected4 = read(OLD / "selections" / "04.json")
    for selected in (selected0, selected4): verify(selected)
    assert selected0["selectable"] and not selected4["selectable"]
    assert selected4["planned_folds"] == 44 and selected4["qualified_folds"] == 43
    status = {r["job_key"]: r for r in selected4["folds"]}
    recovery_path = HERE.parent / "recovery" / "result.json"
    recovery = read(recovery_path)
    verify(recovery)
    recovery_receipt = read(recovery_path.with_name("receipt.json"))
    verify(recovery_receipt)
    precision = read(HERE.parent / "precision" / "result.json")
    verify(precision)
    precision_receipt = read(HERE.parent / "precision" / "receipt.json")
    verify(precision_receipt)
    assert recovery_receipt["exit_code"] == precision_receipt["exit_code"] == 0
    n = precision["numerical"]
    assert precision["finite_checks_passed"] and n["stable_by_established_limits"]
    assert n["newton_en_displacement_m"] <= .01 and abs(n["newton_time_displacement_s"]) <= 1e-5
    assert precision["job_key"] == recovery["job_key"]
    new_receipts = [str(recovery_path.with_name("receipt.json").resolve()),
                    str((HERE.parent / "precision" / "receipt.json").resolve())]
    for job in plan["jobs"]:
        if job["index"] != 4: continue
        key = f"{job['index']:02d}_{job['family']}_{job['norad']}"
        path = OLD / "runs" / f"{key}.json"
        record = read(path)
        verify(record)
        receipt = read(path.with_suffix(".receipt.json"))
        new_receipts.append(str(path.with_suffix(".receipt.json").resolve()))
        assert receipt["exit_code"] == 0 and receipt["job_key"] == key
        assert receipt["run_sha256"] == digest(OLD / "run.py")
        assert receipt["plan_sha256"] == digest(OLD / "plan.json")
        assert receipt["protocol_sha256"] == digest(OLD / "PROTOCOL.md")
        assert record["job_key"] == key and record["reference_used"] is False
        assert record["full_endpoint_x"] == job["full_endpoint_x"]
        assert record["fold"]["track_ids"] == job["source_track_ids"]
        if assess.qualifies(record["fold"]):
            assert status[key]["qualified"]
            job["cache"] = dict(kind="screen", path=str(path.resolve()))
        else:
            assert key == recovery["job_key"] and not status[key]["qualified"]
            assert recovery["original_failed_result"] == record
            assess.normalize_recovery(recovery, job)
            assert receipt["wall_s"] + precision_receipt["wall_s"] + recovery_receipt["wall_s"] < 90
            job["cache"] = dict(kind="recovery", path=str(recovery_path.resolve()))
    for name in ("run.py", "assess.py", "prepare.py", "fit_policy.py", "PROTOCOL.md",
                 "test_run.py", "test_assess.py", "test_fit_policy.py"):
        bind(HERE / name)
    assert len(plan["jobs"]) == 448
    assert sum(j["cache"] is not None for j in plan["jobs"]) == 108
    assert sum(j["cache"] is None for j in plan["jobs"]) == 340
    assert sum(j["cache"] and j["cache"]["kind"] == "recovery" for j in plan["jobs"] if j["cache"]) == 1
    plan.update(schema="ds11-source-loo-recovery-screen-plan/v1",
                cached_job_count=108, pending_job_count=340,
                parent_plan=str((OLD / "plan.json").resolve()),
                validated_cache_receipts=sorted(set(plan["validated_cache_receipts"] + new_receipts)),
                execution={**plan["execution"], "within_job_retries": 0,
                           "conditional_slsqp_continuations": 1,
                           "cap_includes_precision_and_continuation": True},
                sources=dict(sorted(sources.items())))
    for scan in plan["scans"]:
        scan["cached_job_count"] = sum(j["cache"] is not None for j in plan["jobs"] if j["index"] == scan["index"])
    plan.pop("preparation_elapsed_s", None)
    with (HERE / "plan.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(jobs=448, cached=108, pending=340, sources=len(sources))))


if __name__ == "__main__":
    main()
