"""Describe saved input/ranking differences; no new detector or RF collection."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    result = {
        "scope": "saved_visit_input_comparison",
        "new_rf_samples": 0,
        "ground_truth_labels": False,
        "acceptance_gates_changed": False,
        "cases": {},
    }
    paths = {
        "ch3": BASE / "two-frequency-visits60-v3/visit-0",
        "ch4": BASE / "two-frequency-visits60-v3/visit-1",
        "positive": BASE / "paced-live-observer-arm-v1-results/positive",
        "control": BASE / "paced-live-observer-arm-v1-results/control",
    }
    for name, root in paths.items():
        rows = [json.loads(x) for x in (root / "worker.jsonl").read_text().splitlines()]
        powers = [r["single_pilot_power"] for r in rows if r["kind"] == "candidate_order"]
        if not powers:
            powers = [[p[3] for p in rows[0]["peaks"]]]
        powers = np.asarray(powers)
        past = [r for r in rows if r["kind"] == 3]
        p = (
            root / "iq.ci16"
            if name.startswith("ch")
            else BASE / f"paced-original-seed-input-v1/{name}.ci16"
        )
        iq = np.memmap(p, mode="r", dtype="<i2").reshape(-1, 2)
        block_rms = []
        clipped = zero = 0
        mean = np.zeros(2)
        energy = 0
        for at in range(0, len(iq), 16384):
            x = iq[at : at + 16384].astype(np.int64)
            total = int(np.sum(x * x))
            energy += total
            mean += x.sum(axis=0)
            block_rms.append(float(np.sqrt(total / len(x))))
            clipped += int(np.sum(np.any((x == -32768) | (x == 32767), axis=1)))
            zero += int(np.sum(np.all(x == 0, axis=1)))
        result["cases"][name] = {
            "iq_path": str(p),
            "iq_sha256": digest(p),
            "complex_samples": len(iq),
            "complex_rms": float(np.sqrt(energy / len(iq))),
            "iq_mean": (mean / len(iq)).tolist(),
            "block_rms_quantiles": np.quantile(block_rms, [0, 0.5, 1]).tolist(),
            "rail_pairs": clipped,
            "zero_pairs": zero,
            "maximum_single_pilot_rank_power": float(powers.max()),
            "per_scan_maximum_rank_power": powers.max(axis=1).tolist(),
            "maximum_startup_coherence": max(r["coherence"] for r in past),
            "accepted_startup": sum(r["accepted"] for r in past),
            "startup_measurements": len(past),
            "worker_journal_sha256": digest(root / "worker.jsonl"),
        }
    result["status"] = "complete_descriptive_only"
    with (BASE / "recent-visit-input-comparison-v1.json").open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
