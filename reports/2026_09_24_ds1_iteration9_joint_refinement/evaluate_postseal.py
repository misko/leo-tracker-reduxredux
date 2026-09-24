#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REF = (37.84903264307456, -122.4856541910174)


def dist(a, b):
    x = map(math.radians, (*a, *b))
    la, lo, lb, loo = x
    h = math.sin((lb - la) / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin((loo - lo) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inference", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    d = json.loads(a.inference.read_text())
    if d.get("reference_used_for_fit") is not False:
        raise ValueError("unsealed inference")
    w = d["winner"]
    r = {
        "latitude_deg": w["latitude_deg"],
        "longitude_deg": w["longitude_deg"],
        "east_km_from_iteration8": w["east_km_from_iteration8"],
        "north_km_from_iteration8": w["north_km_from_iteration8"],
        "balanced_exact_capped_loss": w["balanced_exact_capped_loss"],
        "postseal_error_km": dist((w["latitude_deg"], w["longitude_deg"]), REF),
        "group_00_tau_s": w["best_exact_by_group"]["20260921_00"]["tau_s"],
        "group_16_tau_s": w["best_exact_by_group"]["20260921_16"]["tau_s"],
        "reference_role": "post-seal only",
    }
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir / "iteration9-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration9-postseal/v1",
                "reference_role": "post-seal only",
                "rows": [r],
            },
            indent=2,
        )
        + "\n"
    )
    with (a.output_dir / "iteration9-postseal.csv").open("w", newline="") as h:
        q = csv.DictWriter(h, fieldnames=list(r))
        q.writeheader()
        q.writerow(r)
    fig, ax = plt.subplots(figsize=(4, 3), constrained_layout=True)
    ax.bar(["joint refinement"], [r["postseal_error_km"]])
    ax.set_ylabel("post-seal error (km)")
    fig.savefig(a.output_dir / "iteration9-postseal.png", dpi=160)
    print(json.dumps(r, sort_keys=True))


if __name__ == "__main__":
    main()
