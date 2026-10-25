"""Independent saved-table checks; no estimator imports or propagation."""
from pathlib import Path
import csv
import hashlib
import json
import math
import statistics

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    checks = []

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})
        if not value:
            raise AssertionError(name)

    rf_path = ROOT / "validation/RF_seal02.json"
    rf = json.loads(rf_path.read_text())
    for key in ("all_selected_terminal", "protocol_immutable",
                "original_gates_replayed", "bindings_audited"):
        check(key, rf[key] is True)
    for path, digest in rf["files"].items():
        check("RF binding: " + path, sha(path) == digest)
    report_path = ROOT / "validation/report/seal.json"
    report = json.loads(report_path.read_text())
    check("report RF binding", report["RF_seal_sha256"] == sha(rf_path))
    for path, digest in report["files"].items():
        check("report binding: " + path, sha(path) == digest)
    summary = json.loads((ROOT / "validation/report/summary.json").read_text())
    rows = list(csv.DictReader((ROOT / "validation/report/positions.csv").open()))
    check("64 complete rows", len(rows) == 64)
    cases = ["RX1V-%04d" % i for i in range(1, 9)]
    keys = {(r["case"], r["arm"], r["variant"]) for r in rows}
    check("exact eight cases", sorted({r["case"] for r in rows}) == cases)
    check("no duplicate rows", len(keys) == len(rows))
    indexed = {(r["case"], r["arm"], r["variant"]): r for r in rows}
    summaries = []
    for arm in ("c0", "fitted_c"):
        for case in cases:
            base = indexed[case, arm, "baseline"]
            cold = indexed[case, arm, "matched_cold_baseline"]
            raw = indexed[case, arm, "raw_candidate"]
            policy = indexed[case, arm, "primary_policy"]
            check(case + arm + " baseline qualified", base["qualified"] == "True")
            for field in ("lat", "lon", "RMS_hz", "negative_twice_ELBO", "error_km"):
                check(case + arm + " cold equality " + field, base[field] == cold[field])
            source = raw if raw["qualified"] == "True" else base
            for field in ("lat", "lon", "RMS_hz", "negative_twice_ELBO", "error_km"):
                check(case + arm + " frozen policy " + field, policy[field] == source[field])
            for variant in ("primary_policy", "matched_cold_baseline", "raw_candidate"):
                row = indexed[case, arm, variant]
                check(case + arm + variant + " likelihood ownership",
                      row["likelihood_union_ids_sha256"] == base["likelihood_union_ids_sha256"])
            check(case + arm + " primary preserves accepted IDs",
                  policy["lost_baseline_postfit_count"] == "0")
        for variant in ("baseline", "primary_policy", "matched_cold_baseline", "raw_candidate"):
            group = [indexed[c, arm, variant] for c in cases]
            errors = sorted(float(r["error_km"]) for r in group)
            h = .95 * (len(errors) - 1)
            lo = math.floor(h)
            metrics = {"n_available": len(errors), "mean": statistics.mean(errors),
                       "median": statistics.median(errors),
                       "p95": errors[lo] + (h - lo) * (errors[lo + 1] - errors[lo]),
                       "maximum": max(errors)}
            saved = next(s for s in summary["summaries"]
                         if s["arm"] == arm and s["variant"] == variant)
            for key, value in metrics.items():
                check(arm + variant + " metric " + key,
                      abs(value - saved["errors_km"][key]) < 1e-12)
            deltas = [float(r["error_change_km"]) for r in group]
            signs = {"improved": sum(d < -1e-12 for d in deltas),
                     "worsened": sum(d > 1e-12 for d in deltas),
                     "tied": sum(abs(d) <= 1e-12 for d in deltas)}
            for key, value in signs.items():
                check(arm + variant + " signs " + key, value == saved[key])
            summaries.append({"arm": arm, "variant": variant, **metrics, **signs,
                              "mean_RMS_change_hz": statistics.mean(float(r["RMS_change_hz"]) for r in group),
                              "mean_objective_change": statistics.mean(float(r["objective_change"]) for r in group)})
    for case in cases:
        check(case + " matched c ownership",
              indexed[case, "c0", "baseline"]["likelihood_union_ids_sha256"] ==
              indexed[case, "fitted_c", "baseline"]["likelihood_union_ids_sha256"])
    out = {"all_passed": all(c["passed"] for c in checks), "checks": checks,
           "summaries": summaries, "RF_seal02_sha256": sha(rf_path),
           "report_seal_sha256": sha(report_path), "source_sha256": sha(__file__),
           "new_fits": 0, "propagation_calls": 0,
           "geography_read_only_after_root_authorized_sealed_report": True}
    path = ROOT / "audit/evaluation_readback.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"all_passed": out["all_passed"], "checks": len(checks), "path": str(path)}))


if __name__ == "__main__":
    main()
