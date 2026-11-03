import hashlib
import json
import math
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def distance(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat1 - lat2) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon1 - lon2) / 2) ** 2
    )
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def main():
    reference_path = HERE.parent / "2026_09_29_unassociated_trend/summary.json"
    reference = json.loads(reference_path.read_text())["reference"]
    receipts = json.loads((HERE / "receipts.json").read_text())
    assert len(receipts) == 9
    rows = []
    hashes = {}
    for receipt in receipts:
        key = receipt["panel"]
        p = HERE / f"{key}.json"
        if receipt["exit_code"] != 0 or not p.exists():
            rows.append(dict(panel=key, status="execution_failed"))
            continue
        doc = json.loads(p.read_text())
        for name, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        arms = {k: v["selected"] for k, v in doc["arms"].items()}
        if any(v is None or not v["audit_passed"] for v in arms.values()):
            rows.append(dict(panel=key, status="fit_unqualified"))
            continue
        a, b = arms["cached"], arms["corrected"]
        previous_path = HERE.parent / "2026_09_29_sparse_waveform_position" / f"{key}.json"
        previous = json.loads(previous_path.read_text())["arms"]["corrected"]["selected"]
        assert previous["audit_passed"]
        hashes[str(previous_path.relative_to(ROOT))] = hashlib.sha256(
            previous_path.read_bytes()
        ).hexdigest()
        actual_vector = (np.array(b["x"][:2]) - a["x"][:2]) * 1000
        predicted_vector = np.array(doc["predicted_movement_m"])
        rows.append(
            dict(
                panel=key,
                status="ok",
                cached_m=distance(a["estimate_deg"], reference),
                earlier_m=distance(previous["estimate_deg"], reference),
                corrected_m=distance(b["estimate_deg"], reference),
                predicted_movement_m=float(np.linalg.norm(predicted_vector)),
                linearization_error_m=float(np.linalg.norm(actual_vector - predicted_vector)),
                movement_m=distance(a["estimate_deg"], b["estimate_deg"]),
                held_gain=b["held_score"] - a["held_score"],
                common_model_held_gain=b["common_model_held_score"] - a["common_model_held_score"],
                tracks=doc["tracks"],
                observations=doc["observations"],
                training_observations=doc["training_observations"],
                corrected_observations=len(doc["applied"]),
                max_gradient_error=max(v["audit_max_difference"] for v in arms.values()),
            )
        )
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        valid = [
            r for r in rows if r["status"] == "ok" and (ds == "all" or r["panel"].startswith(ds))
        ]
        summary[ds] = dict(
            returned=len(valid),
            improved=sum(r["corrected_m"] < r["cached_m"] for r in valid),
            cached_median_m=median(r["cached_m"] for r in valid) if valid else None,
            earlier_median_m=median(r["earlier_m"] for r in valid) if valid else None,
            corrected_median_m=median(r["corrected_m"] for r in valid) if valid else None,
            held_improved=sum(r["held_gain"] > 0 for r in valid),
            cached_subkm=sum(r["cached_m"] < 1000 for r in valid),
            corrected_subkm=sum(r["corrected_m"] < 1000 for r in valid),
        )
    for p in (reference_path, HERE / "receipts.json", HERE / "summarize.py"):
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "summary.json").write_text(
        json.dumps(dict(reference=reference, hashes=hashes, rows=rows, summary=summary), indent=2)
        + "\n"
    )
    lines = [
        "| Panel | Cached error m | Earlier budget error m | Ranked error m | Movement m | "
        "Held log-score gain | Common-model held gain |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    valid = []
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"| {r['panel']} ({r['status']}) | — | — | — | — | — | — |")
            continue
        valid.append(r)
        lines.append(
            f"| {r['panel']} | {r['cached_m']:.2f} | {r['earlier_m']:.2f} | "
            f"{r['corrected_m']:.2f} | {r['movement_m']:.2f} | "
            f"{r['held_gain']:.3f} | {r['common_model_held_gain']:.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(valid))
    for arm, offset in (("cached", -0.24), ("earlier", 0), ("corrected", 0.24)):
        ax.barh(y + offset, [r[f"{arm}_m"] for r in valid], height=0.22, label=arm)
    ax.set_yticks(y, [r["panel"] for r in valid])
    ax.axvline(1000, color="black", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Error to exposed, unsurveyed reference (m)")
    ax.set_title("Eight corrections per panel: earlier versus ranked budget")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
