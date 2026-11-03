"""Descriptive, score-only incumbent retention audit; no new model fitting."""

import hashlib
import json
from pathlib import Path
from statistics import mean, median


HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE.parent / "2026_10_07_recent_filter_review" / "snapshot.json"


def summarize(errors):
    return {
        "n": len(errors),
        "median_error_m": median(errors),
        "mean_error_m": mean(errors),
        "maximum_error_m": max(errors),
        "over_10km": sum(e > 10000 for e in errors),
        "over_50km": sum(e > 50000 for e in errors),
    }


def audit(captures, method_name):
    rows = []
    for capture in captures:
        document = capture.get("regional_document")
        if not document:
            continue
        method = next(m for m in document["methods"] if m["name"] == method_name)
        arms = {a["name"]: a["selected"] for a in method["arms"]}
        fitted, zero = arms["fitted-c"], arms["zero-c"]
        # Truth and convergence flags play no role in this declared selection.
        use_zero = zero["selection_score"] < fitted["selection_score"]
        selected = zero if use_zero else fitted
        assert selected["selection_score"] <= fitted["selection_score"]
        rows.append({
            "session_id": capture["session_id"],
            "capture_start_utc": capture["capture_start_utc"],
            "retained_arm": "zero-c" if use_zero else "fitted-c",
            "score_improvement": fitted["selection_score"] - selected["selection_score"],
            "original_error_m": fitted["horizontal_error_m"],
            "envelope_error_m": selected["horizontal_error_m"],
            "original_converged": fitted["converged"],
            "selected_arm_converged": selected["converged"],
            "selected_boundary": selected["boundary"],
            "free_c_stationarity": None if use_zero else fitted["stationarity"],
            "free_c_converged": None if use_zero else fitted["converged"],
        })
    changed = [r for r in rows if r["retained_arm"] == "zero-c"]
    return {
        "original": summarize([r["original_error_m"] for r in rows]),
        "envelope": summarize([r["envelope_error_m"] for r in rows]),
        "switches": len(changed),
        "switches_improving_position": sum(r["envelope_error_m"] < r["original_error_m"] for r in changed),
        "switches_worsening_position": sum(r["envelope_error_m"] > r["original_error_m"] for r in changed),
        "rows": rows,
    }


def main():
    raw = SNAPSHOT.read_bytes()
    snapshot = json.loads(raw)
    result = {
        "snapshot_utc": snapshot["snapshot_utc"],
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "procedure": "Retain the lower selection_score of the two original published arm incumbents, ties fitted-c; no reoptimization or gating.",
        "limitations": [
            "Retrospective descriptive audit on the original 17 paired captures, not independent validation.",
            "A zero-c candidate is feasible in the free-c model; fixed-c stationarity does not establish free-c convergence.",
            "Nested candidate retention repairs score dominance, not necessarily location accuracy.",
            "This does not evaluate the agents' shared-start reoptimization across the cohort.",
        ],
        "methods": {name: audit(snapshot["captures"], name) for name in ("T1AT", "V16")},
    }
    (HERE / "incumbent_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({name: {k: v for k, v in item.items() if k != "rows"}
                      for name, item in result["methods"].items()}, indent=2))


if __name__ == "__main__":
    main()
