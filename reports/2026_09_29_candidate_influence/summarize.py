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
    rows = []
    table = [
        "| Panel | Candidate | Tracks/scans | Qualified | Baseline m | Half-weight m "
        "| Held gain, selected | Held gain, remaining |",
        "|---|---:|---:|:---:|---:|---:|---:|---:|",
    ]
    for ds in (7, 8, 9):
        for part in ("early", "middle", "late"):
            key = f"DS{ds}_{part}_8"
            result = json.loads((HERE / f"{key}.json").read_text())
            for name, digest in result["hashes"].items():
                assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
            fit = result["fits"][-1]
            group = result["ranked"][0]
            row = dict(
                unit=key,
                number=group["number"],
                tracks=len(group["members"]),
                scans=len(group["scans"]),
                cross_scan_groups=result["cross_scan_groups"],
                qualified=fit["qualified"] and result["response_audit_passed"],
                baseline_error_m=distance(result["baseline_estimate_deg"], reference),
                error_m=distance(fit["estimate_deg"], reference),
                held_gains=fit["held_gains"],
                response_relative_error=result["response_audit_relative"],
            )
            rows.append(row)
            table.append(
                f"| {key} | {row['number']} | {row['tracks']}/{row['scans']} "
                f"| {'yes' if row['qualified'] else 'NO'} | {row['baseline_error_m']:.2f} "
                f"| {row['error_m']:.2f} | {row['held_gains']['selected']:+.3f} "
                f"| {row['held_gains']['remaining']:+.3f} |"
            )
    (HERE / "TABLE.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(dict(reference=reference, rows=rows), indent=2) + "\n"
    )
    print("\n".join(table))


if __name__ == "__main__":
    main()
