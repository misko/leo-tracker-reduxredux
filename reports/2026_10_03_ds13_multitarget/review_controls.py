"""Audit all controls and matched-edge RF comparisons on the same fixed site."""
import csv
import json
from common import ROOT, SESSIONS, load_scan, baseline, digest
from review import read_records, validate_and_score
import numpy as np


def files(method, arm):
    if method == "Activity":
        return [ROOT/"activity"/f"rf-{arm}"/"assignments.csv"]
    if method == "History":
        return [ROOT/"history/results"/f"rf-{arm}"/f"{sid}-assignments.csv" for sid in SESSIONS.values()]
    return [ROOT/"tracklet"/f"rf-{arm}"/"outputs/assignments.csv"]


def main():
    summary = {"scope": "Matched fixed-reference-position RF ablation, timing/RX refitted in both arms; not position accuracy or held-out evidence",
               "rf_comparisons": [], "controls": [], "source_hashes": {}}
    for label, session in SESSIONS.items():
        data = {arm:load_scan(label, rf_variant=arm) for arm in ("fitted-c", "zero-c")}
        for method in ("Baseline", "Activity", "History", "Tracklet"):
            records, metrics = {}, {}
            for arm, d in data.items():
                if method == "Baseline":
                    records[arm], _ = baseline(d)
                else:
                    paths = files(method, arm)
                    records[arm] = [r for r in read_records(paths) if r["scan"] == label]
                    summary["source_hashes"].update({str(p):digest(p) for p in paths})
                metrics[arm] = validate_and_score(d, records[arm])
            common = set((r["row_index"], r["catalog_number"]) for r in records["fitted-c"]) & set(
                (r["row_index"], r["catalog_number"]) for r in records["zero-c"])
            rms = {}
            for arm, d in data.items():
                lookup = {int(n):i for i,n in enumerate(d["arrays"]["catalog_numbers"])}
                vals = [d["arrays"]["residual_hz"][row, lookup[number]] for row,number in sorted(common)]
                rms[arm] = float(np.sqrt(np.mean(np.square(vals)))) if vals else None
            summary["rf_comparisons"].append(dict(scan=label, method=method, matched_edges=len(common),
                assigned_fitted_c=metrics["fitted-c"]["assigned_peaks"],
                assigned_zero_c=metrics["zero-c"]["assigned_peaks"],
                matched_rms_fitted_c_hz=rms["fitted-c"], matched_rms_zero_c_hz=rms["zero-c"]))
        sealed = load_scan(label, rf_variant="sealed")
        variants = {
            "Activity-independent": [ROOT/"activity/assignments-persistence-disabled.csv"],
            "History-state-off": [ROOT/"history/results/beam32-state-off"/f"{session}-assignments.csv"],
            "History-beam8": [ROOT/"history/results/beam8-state"/f"{session}-assignments.csv"],
            "Tracklet-no-continuity": [ROOT/"tracklet/outputs/assignments-no-continuity.csv"],
        }
        for name, paths in variants.items():
            if not all(p.exists() for p in paths):
                raise FileNotFoundError(str(paths))
            records = [r for r in read_records(paths) if r["scan"] == label]
            metrics = validate_and_score(sealed, records)
            summary["controls"].append(dict(scan=label, method=name, **metrics))
            summary["source_hashes"].update({str(p):digest(p) for p in paths})
    (ROOT/"controls.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    with (ROOT/"rf-comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary["rf_comparisons"][0]))
        writer.writeheader(); writer.writerows(summary["rf_comparisons"])
    print(json.dumps(summary["rf_comparisons"], indent=2))


if __name__ == "__main__": main()
