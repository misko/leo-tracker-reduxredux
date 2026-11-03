import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def distance(point, reference):
    p, q = np.radians(point), np.radians(reference)
    a = (
        np.sin((p[0] - q[0]) / 2) ** 2
        + np.cos(p[0]) * np.cos(q[0]) * np.sin((p[1] - q[1]) / 2) ** 2
    )
    return float(2 * 6371008.8 * np.arcsin(np.sqrt(a)))


def main():
    reference = json.loads(
        (HERE.parent / "2026_09_29_unassociated_trend/summary.json").read_text()
    )["reference"]
    rows, missing = [], []
    refinement_path = HERE / "refinement.json"
    refinements = {}
    if refinement_path.exists():
        refinement = json.loads(refinement_path.read_text())
        for name, digest in refinement["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        refinements = {
            (r["unit"], r["direction"], r["sigma"], r["session_id"]): r for r in refinement["rows"]
        }
    table = [
        "| Panel | Train half | Pair qualified | Baseline error m | Shared slope error m "
        "| Source held gain | Whole-scan marginal gain |",
        "|---|---|:---:|---:|---:|---:|---:|",
    ]
    for ds in (7, 8, 9):
        for part in ("early", "middle", "late"):
            key = f"DS{ds}_{part}_8"
            for direction in (0, 1):
                path = HERE / f"{key}_d{direction}.json"
                if not path.exists():
                    missing.append(dict(unit=key, direction=direction, reason="missing output"))
                    continue
                result = json.loads(path.read_text())
                for name, digest in result["hashes"].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
                if not result["arms"]:
                    missing.append(
                        dict(unit=key, direction=direction, reason="no qualified baseline")
                    )
                    continue
                for arm in result["arms"]:
                    replaced = False
                    for scan in arm["target_scans"]:
                        replacement = refinements.get(
                            (key, direction, arm["sigma"], scan["session_id"])
                        )
                        if replacement is not None:
                            scan.update(
                                log_score=replacement["log_score"],
                                qualified=replacement["qualified"],
                            )
                            replaced = True
                    if replaced:
                        arm["target_log_score"] = sum(s["log_score"] for s in arm["target_scans"])
                        arm["qualified"] = bool(
                            arm["success"]
                            and not arm["boundary"]
                            and arm["projected_gradient"] <= 0.01
                            and arm["gradient_audit"] <= 0.02
                            and max(arm.get("quadrature_audit", {"none": 0.0}).values()) <= 0.01
                            and all(s["qualified"] for s in arm["target_scans"])
                        )
                base, arm = result["arms"]
                row = dict(
                    unit=key,
                    direction=direction,
                    qualified=base["qualified"] and arm["qualified"],
                    baseline_error_m=distance(base["estimate_deg"], reference),
                    error_m=distance(arm["estimate_deg"], reference),
                    source_held_gain=arm["source_held_score"] - base["source_held_score"],
                    target_gain=arm["target_log_score"] - base["target_log_score"],
                )
                rows.append(row)
                table.append(
                    f"| {key} | {'first' if direction == 0 else 'last'} "
                    f"| {'yes' if row['qualified'] else 'NO'} | {row['baseline_error_m']:.2f} "
                    f"| {row['error_m']:.2f} | {row['source_held_gain']:+.3f} "
                    f"| {row['target_gain']:+.3f} |"
                )
    aggregates = []
    for ds in (7, 8, 9):
        s = [r for r in rows if r["qualified"] and r["unit"].startswith(f"DS{ds}_")]
        aggregates.append(
            dict(
                dataset=f"DS{ds}",
                qualified=len(s),
                baseline_median_m=float(np.median([r["baseline_error_m"] for r in s]))
                if s
                else None,
                median_m=float(np.median([r["error_m"] for r in s])) if s else None,
                source_held_wins=sum(r["source_held_gain"] > 0 for r in s),
                target_wins=sum(r["target_gain"] > 0 for r in s),
                geographic_wins=sum(r["error_m"] < r["baseline_error_m"] for r in s),
                baseline_subkm=sum(r["baseline_error_m"] < 1000 for r in s),
                subkm=sum(r["error_m"] < 1000 for r in s),
                target_gain_sum=sum(r["target_gain"] for r in s),
            )
        )
    (HERE / "TABLE.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(
            dict(reference=reference, rows=rows, missing=missing, aggregates=aggregates), indent=2
        )
        + "\n"
    )
    print(json.dumps(dict(missing=missing, aggregates=aggregates), indent=2))


if __name__ == "__main__":
    main()
