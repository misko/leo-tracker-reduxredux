"""Summarize frozen rejection reasons, resources, and the support behind each trial."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from score import distribution


def summarize(root, panel):
    scores = root / "results" / panel
    with (scores / "per_query.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    pred = json.loads((root / "predictions" / (panel + ".json")).read_bytes())["cases"]
    pred = {p["id"]: p for p in pred}
    if len(pred) != len(rows):
        raise ValueError("unmatched queries")
    out = {}
    for condition in ("present", "missing"):
        group = [r for r in rows if r["condition"] == condition]
        pp = [pred[r["id"]] for r in group]
        diag = [p["diagnostics"] for p in pp]
        stages = Counter(p["reason"] for p in pp)
        gates = Counter(d["region_result"]["reason"] for d in diag)
        support = [d["track_counts"] for d in diag]
        work = [d["work"] for d in diag]
        out[condition] = {
            "n": len(group), "reason": dict(stages), "regional_reason": dict(gates),
            "at_least_four_whole_tracks_each_half": sum(min(s["early"], s["late"]) >= 4
                                                        for s in support),
            "ran_all_19_schedules": sum(w["null_schedules"] == 19 for w in work),
            "compared_independent_position_fits": sum("position_evidence" in d for d in diag),
            "median_and_tail_forced_score": distribution(d["held_evidence"]["score"]
                                                        for d in diag if "held_evidence" in d),
            "split_distance_km_on_region_accept": distribution(
                d["position_evidence"]["early_late_km"] for d in diag
                if "early_late_km" in d.get("position_evidence", {})),
            "wall_s": distribution(p["wall_s"] for p in pp),
            "process_wall_s": distribution(p["process_wall_s"] for p in pp),
            "process_cpu_s": distribution(p["process_cpu_s"] for p in pp),
            "peak_rss_mib": distribution(p["peak_rss_kib"] / 1024 for p in pp),
        }
    out["all"] = {
        "peak_rss_mib": distribution(p["peak_rss_kib"] / 1024 for p in pred.values()),
        "process_wall_s": distribution(p["process_wall_s"] for p in pred.values()),
        "process_cpu_s": distribution(p["process_cpu_s"] for p in pred.values()),
    }
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panels", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not (root / "locks" / "prediction-lock.json").is_file():
        raise RuntimeError("missing global prediction commitment")
    output = {p: summarize(root, p) for p in args.panels}
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
