"""Independent pre-launch census and cached-result/receipt compatibility check."""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    plan_path = HERE / "plan.json"
    plan = json.loads(plan_path.read_text())
    jobs = plan["jobs"]
    assert len(jobs) == len({(j["index"], j["family"], j["norad"]) for j in jobs}) == 56
    assert Counter(j["family"] for j in jobs) == Counter({f: 14 for f in plan["family_order"]})
    assert sum(j["cache"] is not None for j in jobs) == 32
    assert sum(j["cache"] is None for j in jobs) == 24
    for family in plan["family_order"]:
        assert [j["norad"] for j in jobs if j["family"] == family] == plan["norad_order"]
    for path, expected in plan["sources"].items():
        assert digest(path) == expected, path
    iid_path = next(Path(j["cache"]["path"]) for j in jobs if j["family"] == "iid_t4_scale100")
    iid = json.loads(iid_path.read_text())
    coverage = {f["norad"]: (f["track_ids"], f["held_observation_count"]) for f in iid["folds"]}
    checked = []
    for job in jobs:
        if not job["cache"]:
            continue
        path = Path(job["cache"]["path"])
        receipt_path = path.with_suffix(".receipt.json")
        assert str(path) in plan["sources"] and str(receipt_path) in plan["sources"]
        record = json.loads(path.read_text())
        receipt = json.loads(receipt_path.read_text())
        assert record["index"] == receipt["index"] == 0
        assert record["family"] == receipt["family"] == job["family"]
        assert receipt["exit_code"] == 0
        assert record["full_endpoint_x"] == job["full_endpoint_x"]
        if job["cache"]["kind"] == "family":
            assert receipt["run_sha256"] == digest(HERE.parent / "run.py")
            assert receipt["protocol_sha256"] == digest(HERE.parent / "PROTOCOL.md")
            assert len(record["folds"]) == 14
            matching = [f for f in record["folds"] if f["norad"] == job["norad"]]
            assert len(matching) == 1
            fold = matching[0]
            assert fold["optimizer"]["qualified"]
            actual = (fold["track_ids"], fold["held_observation_count"])
        else:
            assert job["cache"]["kind"] == "audit"
            assert record["norad"] == receipt["norad"] == job["norad"]
            old = HERE.parent.parent / "source_loo"
            assert receipt["exact_audit_sha256"] == digest(old / "exact_audit.py")
            assert receipt["exact_protocol_sha256"] == digest(old / "EXACT_PROTOCOL.md")
            assert record["optimizer"]["qualified"]
            actual = (record["source_track_ids"], record["exact_common_held"]["held_observation_count"])
        assert actual == coverage[job["norad"]]
        assert actual[0] == job["source_track_ids"]
        checked.append([job["family"], job["norad"]])
    report = dict(schema="ds11-source-loo-atomic-plan-verification/v1", verified=True,
                  planned_jobs=56, verified_cached_jobs=len(checked), pending_jobs=24,
                  checked=checked, plan_sha256=digest(plan_path),
                  verifier_sha256=digest(__file__), reference_used=False)
    with (HERE / "plan-verification.json").open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "checked"}))


if __name__ == "__main__":
    main()
