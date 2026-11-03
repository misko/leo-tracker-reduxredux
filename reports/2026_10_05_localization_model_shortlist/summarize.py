"""Summarize saved localization evidence only; no new model fitting."""
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BASE = ROOT / "reports/2026_10_04_t1_at_v1_replication"
SCANS = {f"N{i:02}" for i in range(1, 17)}
ARMS = ("fitted-c", "zero-c")


def read_csv(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def calculate():
    sources = {}
    rows = []

    def load(path):
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return read_csv(path)

    definitions = [
        ("C1-Q1", BASE / "position-visibility-study/polished/per-scan.csv",
         {"weighting": "ordinary", "gate": "Q1"}, "visibility study"),
        ("C1-TIME-Q1", BASE / "position-visibility-study/polished/per-scan.csv",
         {"weighting": "time-balanced", "gate": "Q1"}, "visibility study"),
        ("V16", BASE / "position-score-sweep/polished/per-scan.csv",
         {"mode": "V16"}, "hyperparameter study"),
        ("C1-sweep-control", BASE / "position-score-sweep/polished/per-scan.csv",
         {"mode": "C1"}, "hyperparameter study"),
        ("historical-satellite-drift", BASE / "satellite-drift-localization/polished/summary.csv",
         {"mode": "satellite-drift"}, "older fold-derived calibration"),
        ("historical-drift-control", BASE / "satellite-drift-localization/polished/summary.csv",
         {"mode": "control"}, "older fold-derived calibration"),
    ]
    for model, path, selector, study in definitions:
        chosen = [r for r in load(path) if all(r[k] == v for k, v in selector.items())]
        assert len(chosen) == 32, (model, len(chosen))
        for arm in ARMS:
            assert {r["scan"] for r in chosen if r["arm"] == arm} == SCANS
        for r in chosen:
            rms_key = "posterior_weighted_residual_rms_hz"
            if rms_key not in r:
                rms_key = "posterior_weighted_rms_hz"
            rows.append(dict(model=model, study=study, scan=r["scan"], arm=r["arm"],
                distance_m=float(r["distance_m"]), windows=int(r["windows"]),
                converged=r["converged"] == "True", boundary=r["boundary"] == "True",
                posterior_rms_hz=float(r[rms_key]), source=str(path.relative_to(ROOT))))

    aggregates = []
    for model, _, _, study in definitions:
        for arm in ARMS:
            group = [r for r in rows if r["model"] == model and r["arm"] == arm]
            errors = [r["distance_m"] for r in group]
            aggregates.append(dict(model=model, study=study, arm=arm, scans=len(group),
                median_m=statistics.median(errors), mean_m=statistics.mean(errors),
                p90_m=percentile(errors, .9), below_1km=sum(e < 1000 for e in errors),
                converged=sum(r["converged"] for r in group),
                boundary=sum(r["boundary"] for r in group),
                median_posterior_rms_hz=statistics.median(r["posterior_rms_hz"] for r in group),
                total_position_windows=sum(r["windows"] for r in group)))

    # Do not claim matched banks from counts; this verifies counts only.
    for scan in SCANS:
        for model, _, _, _ in definitions:
            same_model = [r for r in rows if r["model"] == model and r["scan"] == scan]
            assert same_model[0]["windows"] == same_model[1]["windows"]
        current = [r for r in rows if r["model"] in {"C1-Q1", "C1-TIME-Q1", "V16", "C1-sweep-control"}
                   and r["scan"] == scan]
        assert len({r["windows"] for r in current}) == 1

    ab = [r for r in load(ROOT / "reports/2026_10_05_ab_ambiguity_prototypes/results.csv")
          if r["mode"] == "baseline"]
    assert len(ab) == 4
    ab = [dict(scan=r["scan"], arm=r["arm"], distance_m=float(r["position_error_m"]),
               windows=int(r["retained_windows"]), converged=r["converged"] == "True",
               roof_gradient_norm_per_100m=float(r["roof_gradient_norm_per_100m"])) for r in ab]
    ab_coverage = [r for r in load(BASE / "cohort-coverage.csv")
                   if r["scan"] in {"A", "B"} and r["arm"] == "fitted-c"]
    historical = load(BASE / "convergence-retry/position-results.csv")
    historical_baseline = []
    for arm in ARMS:
        group = [r for r in historical if r["scan"] in SCANS and
                 r["arm"] == arm and r["case"] == "all-100"]
        assert len(group) == 16 and {r["scan"] for r in group} == SCANS
        values = [float(r["distance_m"]) for r in group]
        historical_baseline.append(dict(model="T1-AT v1 historical baseline", arm=arm,
            scans=len(group), median_m=statistics.median(values), mean_m=statistics.mean(values),
            search_radius_m=2000, boundary=sum(r["boundary"] == "True" for r in group),
            converged=sum(r["converged"] == "True" for r in group)))
    association = load(BASE / "full-scan-seed-restart/association-summary.csv")
    coverage = []
    for arm in ARMS:
        group = [r for r in association if r["variant"] == "restarted-full-scan" and r["arm"] == arm]
        assert {r["scan"] for r in group} == SCANS
        assigned = sum(int(r["assigned"]) for r in group)
        total = sum(int(r["denominator"]) for r in group)
        coverage.append(dict(arm=arm, assigned=assigned, total=total, percent=100 * assigned / total))

    pairs = []
    for control, variant in [("C1-sweep-control", "V16"), ("C1-Q1", "C1-TIME-Q1")]:
        for arm in ARMS:
            a = {r["scan"]: r for r in rows if r["model"] == control and r["arm"] == arm}
            b = {r["scan"]: r for r in rows if r["model"] == variant and r["arm"] == arm}
            changes = [b[s]["distance_m"] - a[s]["distance_m"] for s in sorted(SCANS)]
            pairs.append(dict(control=control, variant=variant, arm=arm,
                improved_by_more_than_1m=sum(x < -1 for x in changes),
                worsened_by_more_than_1m=sum(x > 1 for x in changes),
                median_paired_change_m=statistics.median(changes)))

    audits = {}
    for path in [BASE / "position-score-sweep/polished/audit.json",
                 BASE / "position-visibility-study/polished/audit.json",
                 BASE / "satellite-drift-localization/polished/audit.json"]:
        receipt = json.loads(path.read_text())
        assert receipt["status"] == "passed"
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        audits[str(path.relative_to(ROOT))] = dict(status=receipt["status"], cases=receipt["cases"])

    latest_path = ROOT / "reports/2026_10_05_n16_glrt_refinement_ablation/comparison/summary.json"
    latest = json.loads(latest_path.read_text())
    sources[str(latest_path.relative_to(ROOT))] = hashlib.sha256(latest_path.read_bytes()).hexdigest()

    return dict(scope="Saved-result summary, not a fresh matched 18-scan tournament.",
                aggregates=aggregates, paired_comparisons=pairs, ab_historical_baseline=ab,
                ab_coverage=ab_coverage, full_data_coverage=coverage, source_audits=audits,
                historical_t1_at_v1_baseline=historical_baseline,
                latest_refinement_comparison=latest["summary"],
                source_sha256=sources), rows


if __name__ == "__main__":
    summary, rows = calculate()
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    with (HERE / "per-scan.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary["aggregates"], indent=2))
    for scan in sorted(SCANS):
        values = []
        for model in ["C1-Q1", "V16", "C1-TIME-Q1"]:
            for arm in ARMS:
                r = next(r for r in rows if (r["scan"], r["model"], r["arm"]) == (scan, model, arm))
                values.append(f'{r["distance_m"]:.0f}' + ('†' if not r['converged'] else '') + ('‡' if r['boundary'] else ''))
        print('| ' + scan + ' | ' + ' | '.join(values) + ' |')
