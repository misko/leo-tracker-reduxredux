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
    table = [
        "| Panel | Train RX | SD Hz/s | Qualified | Error m | Source held gain "
        "| Opposite-RX full-track gain |",
        "|---|---:|---:|:---:|---:|---:|---:|",
    ]
    for ds in (7, 8, 9):
        for part in ("early", "middle", "late"):
            key = f"DS{ds}_{part}_8"
            for receiver in (0, 1):
                path = HERE / f"{key}_rx{receiver}.json"
                if not path.exists():
                    missing.append(dict(unit=key, receiver=receiver))
                    continue
                result = json.loads(path.read_text())
                for name, digest in result["hashes"].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
                if not result["arms"]:
                    missing.append(
                        dict(unit=key, receiver=receiver, reason="no qualified baseline")
                    )
                    continue
                base = result["arms"][0]
                for arm in result["arms"]:
                    r = dict(
                        arm,
                        unit=key,
                        source_receiver=receiver,
                        error_m=distance(arm["estimate_deg"], reference),
                        baseline_error_m=distance(base["estimate_deg"], reference),
                        source_held_gain=arm["source_held_score"] - base["source_held_score"],
                        target_gain=arm["target_full_score"] - base["target_full_score"],
                    )
                    rows.append(r)
                    table.append(
                        f"| {key} | {receiver} | {r['sigma']:g} "
                        f"| {'yes' if r['qualified'] else 'NO'} | {r['error_m']:.2f} "
                        f"| {r['source_held_gain']:+.3f} | {r['target_gain']:+.3f} |"
                    )
    aggregates = []
    for sigma in (0.0, 0.5, 2.0):
        s = [r for r in rows if r["sigma"] == sigma and r["qualified"]]
        aggregates.append(
            dict(
                sigma=sigma,
                qualified=len(s),
                source_held_wins=sum(r["source_held_gain"] > 0 for r in s),
                target_wins=sum(r["target_gain"] > 0 for r in s),
                geographic_wins=sum(r["error_m"] < r["baseline_error_m"] for r in s),
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
