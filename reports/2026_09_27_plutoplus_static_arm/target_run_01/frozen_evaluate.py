"""Shared strict assessment for host correctness and physical ARM timings."""
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ASSESS = HERE.parent / "2026_09_27_ds5_cached_tracking/review/arm_probe/assess.py"
spec = importlib.util.spec_from_file_location("static_arm_prior_assess", ASSESS)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def validate(result, case, method):
    for key, expected in (("case_id", case["case_id"]), ("rate_hz", case["rate_hz"]),
                          ("edge", case["edge"]), ("method", method), ("warmups", 1)):
        if result.get(key) != expected:
            raise ValueError(f"result identity mismatch: {key}")
    reps = result["repetitions"]
    if len(reps) != 5 or [r["index"] for r in reps] != list(range(5)):
        raise ValueError("incomplete repetitions")
    signatures = [tuple(prior.science(rx) for rx in r["receivers"]) for r in reps]
    if any(s != signatures[0] for s in signatures):
        raise ValueError("nondeterministic scientific observations")
    costs = [prior.repetition_cost(r) for r in reps]
    medians = {k: statistics.median(c[k] for c in costs) for k in costs[0]}
    medians.update({k: prior.finite(result[k], name=k) for k in
                   ("io_cpu_ms", "io_wall_ms", "initialization_cpu_ms", "initialization_wall_ms")})
    return {"science": signatures[0], "cost": medians}


def compare_case(case, results):
    rows = {(case["case_id"], m): validate(r, case, m) for m, r in results.items()}
    if set(results) != set("ABCD"):
        raise ValueError("missing method")
    identity = {m: prior.identity(rows, {case["case_id"]: case}, {case["case_id"]}, "A", m)
                for m in "BCD"}
    truth = []
    if case["split"] == "control":
        for m in "ABCD":
            for rx, obs in enumerate(rows[case["case_id"], m]["science"]):
                expected = case["truth"]["kind"] == "pilot"
                passed = obs["positive"] == expected
                dt = df = None
                if expected and obs["positive"]:
                    target = case["truth"]["receivers"][rx]
                    epoch = target["epoch_samples"] + target["fractional_delay_samples"]
                    dt = abs(prior.circular_samples(obs["epoch_samples"]-epoch, case["rate_hz"]))/case["rate_hz"]*1e6
                    df = abs(obs["tracking_cfo_hz"]-target["cfo_hz"])
                    passed &= dt <= 2 and df <= 8000 and obs["selected_window"] == target["window"]
                truth.append({"method": m, "receiver": rx, "passed": bool(passed),
                              "timing_error_us": dt, "cfo_error_hz": df})
    return {"case_id": case["case_id"], "rate_hz": case["rate_hz"], "split": case["split"],
            "methods": {m: rows[case["case_id"], m] for m in "ABCD"},
            "identity": identity, "truth": truth,
            "passed": all(x["all_identity_gates_pass"] for x in identity.values()) and all(x["passed"] for x in truth)}


def summarize(assessments):
    summary = []
    for split in ("control", "dev"):
        for rate in (2500000, 5000000, 7500000, 10000000):
            cohort = [a for a in assessments if a["split"] == split and a["rate_hz"] == rate]
            if not cohort:
                continue
            methods = {}
            for m in "ABCD":
                costs = [a["methods"][m]["cost"] for a in cohort]
                total = sum(c["total_cpu_ms"] for c in costs)
                wall = sorted(c["total_wall_ms"] for c in costs)
                methods[m] = {"cpu_total_ms": total, "cpu_mean_ms": total/len(costs),
                    "cpu_median_ms": statistics.median(c["total_cpu_ms"] for c in costs),
                    "wall_max_ms": max(wall), "wall_over_120ms": sum(t>120 for t in wall),
                    "reference_positive_receivers": sum(s["positive"] for a in cohort for s in a["methods"][m]["science"]),
                    "stage_mean_ms": {k: sum(c[k] for c in costs)/len(costs) for k in costs[0]}}
            for m in "ABCD":
                methods[m]["speedup_vs_A"] = methods["A"]["cpu_total_ms"]/methods[m]["cpu_total_ms"]
            summary.append({"split": split, "rate_hz": rate, "cases": len(cohort),
                            "passed": all(a["passed"] for a in cohort), "methods": methods})
    return summary


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    print(json.dumps(summarize(data), indent=2))
