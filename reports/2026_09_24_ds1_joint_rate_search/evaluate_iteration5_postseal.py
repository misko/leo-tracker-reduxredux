#!/usr/bin/env python3
"""External post-seal evaluator for iteration-5 timing refinement."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
I4 = HERE / "iteration4-postseal/iteration4-postseal.json"
REF = (37.84903264307456, -122.4856541910174)


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    la, lo, lb, loo = map(math.radians, (*a, *b))
    x = math.sin((lb - la) / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin((loo - lo) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(x))


def bad(v: Any) -> bool:
    keys = {"reference", "reference_coordinate", "reference_error_km", "truth"}
    return (
        bool(keys & v.keys())
        or any(bad(x) for x in v.values() if isinstance(x, dict))
        or any(bad(x) for x in v if isinstance(v, list))
        if isinstance(v, (dict, list))
        else False
    )


def evaluate(i5: dict[str, Any], i4: dict[str, Any]) -> list[dict[str, Any]]:
    if i5.get("reference_used_for_fit") is not False or bad(i5):
        raise ValueError("reference present in inference")
    prior = {r["group_id"]: r["iteration4_exact_selected_error_km"] for r in i4["rows"]}
    out = []
    for r in i5["results"]:
        w = r["winner"]
        gate = w["exact_comparison"]["exact_sgp4_gate"]
        if not gate["passed"]:
            raise ValueError("failed exact gate")
        err = distance((w["latitude_deg"], w["longitude_deg"]), REF)
        out.append(
            {
                "group_id": r["group_id"],
                "iteration4_error_km": prior[r["group_id"]],
                "iteration5_error_km": err,
                "delta_km": err - prior[r["group_id"]],
                "exact_capped_loss": w["exact_comparison"]["exact_full_observation_capped_loss"],
                "tau_s": w["tau_s"],
                "shortlist_count": len(r["shortlist"]),
            }
        )
    return sorted(out, key=lambda x: x["group_id"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inference", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    rows = evaluate(json.loads(a.inference.read_text()), json.loads(I4.read_text()))
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir / "iteration5-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration5-postseal/v1",
                "reference_role": "post-seal only",
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    with (a.output_dir / "iteration5-postseal.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    fig, ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
    x = range(len(rows))
    ax.bar(
        [v - 0.18 for v in x], [r["iteration4_error_km"] for r in rows], 0.36, label="iteration 4"
    )
    ax.bar(
        [v + 0.18 for v in x], [r["iteration5_error_km"] for r in rows], 0.36, label="iteration 5"
    )
    ax.set_xticks(list(x), [r["group_id"][-2:] for r in rows])
    ax.set_ylabel("post-seal error (km)")
    ax.legend()
    fig.savefig(a.output_dir / "iteration5-postseal.png", dpi=160)
    print(json.dumps({"rows": len(rows)}))


if __name__ == "__main__":
    main()
